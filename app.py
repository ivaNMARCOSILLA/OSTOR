# -*- coding: utf-8 -*-
"""MAGGY PRO 8.4.1 — API musical y distribución web.

Proyecto y edición: Iván Marcos Illa.
El código de servicios externos y sus marcas pertenece a sus titulares.
Firma de edición: MAGGY / Iván Marcos Illa / 2026-10-24.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import logging
import os
import re
import threading
import time
import unicodedata
from collections import OrderedDict, deque
from urllib.parse import quote, urljoin, urlparse

import requests
from flask import Flask, Response, jsonify, request, redirect, send_from_directory, stream_with_context
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(ROOT, "assets"), static_url_path="/assets")
# Un solo salto de proxy controlado por Vercel. No se aceptan cabeceras CORS globales.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
app.logger.setLevel(logging.INFO)

VERSION = "8.4.1"
AUDIUS_APP_NAME = os.getenv("AUDIUS_APP_NAME", "electronicama")
SEARCH_CACHE_SECONDS = max(15, min(int(os.getenv("SEARCH_CACHE_SECONDS", "300")), 3600))
ARCHIVE_CACHE_SECONDS = max(60, min(int(os.getenv("ARCHIVE_CACHE_SECONDS", "3600")), 86400))
REQUEST_TIMEOUT = (2.5, 6)
MAX_PROXY_BYTES = 32 * 1024 * 1024
MAX_SEARCH_LENGTH = 90

# Cachés pequeñas, con bloqueo. En Vercel son por instancia: no persistentes ni compartidas.
_cache_lock = threading.RLock()
_search_cache: OrderedDict[tuple, tuple[float, list]] = OrderedDict()
_archive_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_rate_lock = threading.Lock()
_request_buckets: dict[tuple[str, str], deque] = {}


def cached_get(store: OrderedDict, key, ttl):
    with _cache_lock:
        value = store.get(key)
        if value is None:
            return None
        created, payload = value
        if time.monotonic() - created > ttl:
            store.pop(key, None)
            return None
        store.move_to_end(key)
        return payload


def cached_put(store: OrderedDict, key, payload):
    with _cache_lock:
        store[key] = (time.monotonic(), payload)
        store.move_to_end(key)
        while len(store) > 128:
            store.popitem(last=False)


def rate_allowed(kind: str, limit: int, window: int = 60) -> bool:
    # Límite de mejor esfuerzo por instancia, no protección distribuida.
    key = (kind, request.remote_addr or "unknown")
    now = time.monotonic()
    with _rate_lock:
        bucket = _request_buckets.setdefault(key, deque())
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        if len(_request_buckets) > 1000:
            for old in list(_request_buckets)[:200]:
                if not _request_buckets[old] or now - _request_buckets[old][-1] > window:
                    del _request_buckets[old]
        return True


def sanitize_query(value: str) -> str:
    value = " ".join((value or "").split())
    return value[:MAX_SEARCH_LENGTH]


def normalize(value) -> str:
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


# Palabras de intención frecuentes: no son parte del título ni del artista.
# Se eliminan solo cuando la búsqueda conserva al menos una palabra útil.
_SEARCH_FILLERS = frozenset({
    "cancion", "canciones", "musica", "music", "video", "videos",
    "escuchar", "busca", "buscar", "quiero", "dame", "listen",
    "oficiales", "oficial", "official", "de", "del", "la", "el",
    "las", "los", "the", "por", "para", "un", "una",
})


def provider_query(query: str) -> str:
    """Retira palabras genéricas para que el ranking halle al artista."""
    words = str(query or "").split()
    useful = [word for word in words if normalize(word) not in _SEARCH_FILLERS]
    return " ".join(useful or words)[:MAX_SEARCH_LENGTH]


def relevance(item: dict, query: str) -> float:
    words = [w for w in normalize(query).split() if len(w) > 1]
    if not words:
        return 0.0
    title = normalize(item.get("title"))
    artist = normalize(item.get("channel"))
    text = f"{title} {artist}"
    hits = sum(1 for w in words if w in text.split() or any(p.startswith(w) for p in text.split()))
    coverage = hits / len(words)
    if coverage < 0.5:
        return -1.0
    score = coverage * 10
    q = normalize(query)
    if q == title:
        score += 5
    elif q in title:
        score += 3
    if q in artist:
        score += 2
    if "official" in title or "oficial" in title:
        score += 0.4
    if "karaoke" in title or "reaction" in title:
        score -= 2
    return score


def fetch_json(url, params=None, timeout=REQUEST_TIMEOUT):
    response = requests.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()


def archive_stream_url(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", identifier):
        raise ValueError("Identificador no válido")
    cached = cached_get(_archive_cache, identifier, ARCHIVE_CACHE_SECONDS)
    if cached:
        return cached
    data = fetch_json(f"https://archive.org/metadata/{quote(identifier, safe='')}")
    metadata = data.get("metadata") or {}
    if data.get("is_dark") or str(metadata.get("access-restricted-item", "")).lower() == "true":
        raise LookupError("Este elemento requiere acceso en Archive")
    # Prefer Safari-compatible derivatives, never the largest Ogg/album by default.
    extensions = (".mp3", ".m4a", ".aac")
    files = [f for f in data.get("files", []) if
             str(f.get("name", "")).lower().endswith(extensions)
             and str(f.get("private", "")).lower() not in {"true", "1"}
             and not any(x in str(f.get("name", "")).lower() for x in ("spectrogram", "waveform"))]
    files.sort(key=lambda f: (next(i for i, ext in enumerate(extensions) if f["name"].lower().endswith(ext)), f["name"].casefold()))
    if not files:
        raise LookupError("No contiene audio compatible")
    url = f"https://archive.org/download/{quote(identifier, safe='')}/{quote(files[0]['name'], safe='/')}"
    cached_put(_archive_cache, identifier, url)
    return url


def search_archive(query: str, limit: int = 8, page: int = 1) -> list:
    try:
        # Escapar caracteres especiales de la sintaxis Lucene.
        safe = re.sub(r'[^\w\s\-áéíóúüñÁÉÍÓÚÜÑ]', ' ', query)
        params = {"q": f'({" ".join(safe.split())}) AND mediatype:audio AND (format:"VBR MP3" OR format:MP3 OR format:MPEG4) AND NOT access-restricted-item:true',
                  "fl[]": ["identifier", "title", "creator", "access-restricted-item"], "sort[]": "downloads desc",
                  "rows": min(40, limit * 3), "page": page, "output": "json"}
        docs = fetch_json("https://archive.org/advancedsearch.php", params).get("response", {}).get("docs", [])
        results = []
        for d in docs:
            ident = str(d.get("identifier", ""))
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", ident) or str(d.get("access-restricted-item", "")).lower() == "true":
                continue
            title = d.get("title") or "Sin título"
            creator = d.get("creator") or "Internet Archive"
            if isinstance(title, list): title = title[0] if title else "Sin título"
            if isinstance(creator, list): creator = creator[0] if creator else "Internet Archive"
            if relevance({"title": title, "channel": creator}, provider_query(query)) < 0:
                continue
            results.append({"id": f"archive_{ident}", "title": str(title)[:140],
                            "channel": str(creator)[:90], "description": "",
                            "thumbnail": f"https://archive.org/services/img/{quote(ident)}",
                            "url": f"https://archive.org/details/{quote(ident)}", "source": "ARCHIVE"})
            if len(results) >= limit: break
        # Resolve only the selected item. Searching no longer downloads 8–15 metadata documents.
        return results
    except (requests.RequestException, ValueError, TypeError) as exc:
        app.logger.warning("Archive search failed: %s", type(exc).__name__)
        return []


AUDIUS_ENDPOINTS = (
    "https://api.audius.co/v1/tracks/search",
    "https://discoveryprovider2.audius.co/v1/tracks/search",
)


def search_audius(query: str, limit: int = 10) -> list:
    for endpoint in AUDIUS_ENDPOINTS:
        try:
            tracks = fetch_json(endpoint, {"query": query, "app_name": AUDIUS_APP_NAME, "limit": limit * 2}, timeout=(2, 3)).get("data", [])
            if not tracks:
                continue
            results = []
            for track in tracks[:limit * 2]:
                ident = str(track.get("id", ""))
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident):
                    continue
                if (track.get("is_streamable") is False or track.get("is_available") is False
                        or track.get("is_stream_gated") or (track.get("access") or {}).get("stream") is False):
                    continue
                artist = (track.get("user") or {}).get("name") or "Audius"
                art = track.get("artwork") or {}
                track_url = track.get("permalink") or ""
                results.append({"id": f"audius_{ident}", "title": str(track.get("title") or "Pista")[:140],
                                "channel": str(artist)[:90], "description": str(track.get("description") or "")[:300],
                                "thumbnail": art.get("480x480") or art.get("1000x1000") or art.get("150x150") or "",
                                "url": f"https://audius.co{track_url}" if str(track_url).startswith("/") else "https://audius.co",
                                "stream_url": f"https://api.audius.co/v1/tracks/{quote(ident)}/stream?app_name={quote(AUDIUS_APP_NAME)}",
                                "source": "AUDIUS"})
            return results[:limit]
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            continue
    return []










def multi_search(query: str, page: int = 1, source: str = "ALL") -> list:
    cache_key = (normalize(query), page, source)
    ranking_query = provider_query(query)
    hit = cached_get(_search_cache, cache_key, SEARCH_CACHE_SECONDS)
    if hit is not None:
        return hit
    if source == "AUDIUS":
        candidates = search_audius(query, limit=10) if page == 1 else []
    elif source == "ARCHIVE" or page > 1:
        candidates = search_archive(query, limit=15, page=page)
    else:
        workers = [(search_archive, 8), (search_audius, 10)]
        candidates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as pool:
            futures = [pool.submit(fn, query, n) for fn, n in workers]
            for future in concurrent.futures.as_completed(futures):
                try:
                    candidates.extend(future.result() or [])
                except Exception:
                    app.logger.exception("A provider failed")
    seen = set()
    scored = []
    for item in candidates:
        if item.get("source") not in {"ARCHIVE", "AUDIUS"}:
            continue
        ident = (item.get("source"), item.get("id"))
        score = relevance(item, ranking_query)
        if score < 0 or ident in seen:
            continue
        seen.add(ident)
        scored.append((score, item))
    scored.sort(key=lambda x: (-x[0], x[1].get("title", "").casefold()))
    result = [item for _, item in scored]
    if result: cached_put(_search_cache, cache_key, result)
    return result


@app.after_request
def response_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    if request.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif request.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def homepage():
    return send_from_directory(ROOT, "index.html")


@app.get("/legal/<path:filename>")
def legal_pages(filename):
    # No se permite navegación arbitraria por directorios desde la ruta legal.
    if filename not in {"cookies.html", "privacidad.html", "aviso-legal.html"}:
        return jsonify({"error": "Documento no encontrado"}), 404
    return send_from_directory(os.path.join(ROOT, "legal"), filename)


@app.get("/manifest.webmanifest")
def pwa_manifest():
    return send_from_directory(ROOT, "manifest.webmanifest", mimetype="application/manifest+json")


@app.get("/sw.js")
def pwa_service_worker():
    response = send_from_directory(ROOT, "sw.js", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.get("/health")
def health():
    return jsonify({"status": "ok", "version": VERSION,
                    "providers": ["ARCHIVE", "AUDIUS"],
                    "search_cache": "instance-local"})






def catalogue_response(tracks):
    from membership import get_user, user_public
    user = get_user()
    if user and user_public(user)["active"]:
        return tracks
    # A whitelist prevents cached/upstream playback links leaking into previews.
    fields = {"id", "title", "channel", "source", "thumbnail"}
    return [{key: value for key, value in track.items() if key in fields} | {"locked": True} for track in tracks]


@app.get("/api/search")
def api_search():
    query = sanitize_query(request.args.get("q", ""))
    if not query:
        return jsonify([])
    if not rate_allowed("search", 70):
        return jsonify({"error": "Demasiadas búsquedas. Inténtalo en un minuto."}), 429
    try:
        page = max(1, min(int(request.args.get("page", "1")), 10))
    except ValueError:
        page = 1
    source = request.args.get("source", "ALL").upper()
    if source not in {"ALL", "ARCHIVE", "AUDIUS"}:
        return jsonify({"error": "Plataforma no válida"}), 400
    tracks = multi_search(query, page=page) if source == "ALL" else multi_search(query, page=page, source=source)
    return jsonify(catalogue_response(tracks))


@app.get("/api/trending")
def api_trending():
    if not rate_allowed("trending", 15):
        return jsonify({"error": "Límite temporal de consultas"}), 429
    return jsonify(catalogue_response(multi_search("electronic techno house trance")))


@app.get("/api/resolve/<path:item_id>")
def api_resolve(item_id):
    if not rate_allowed("resolve", 30):
        return jsonify({"error": "Límite temporal de consultas"}), 429
    if item_id.startswith("audius_"):
        ident = item_id[7:]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident):
            return jsonify({"error": "Identificador no válido"}), 400
        return jsonify({"id": item_id, "source": "AUDIUS", "stream_url": f"https://api.audius.co/v1/tracks/{quote(ident)}/stream?app_name={quote(AUDIUS_APP_NAME)}"})
    if not item_id.startswith("archive_"):
        return jsonify({"id": item_id, "stream_url": ""})
    try:
        return jsonify({"id": item_id, "stream_url": archive_stream_url(item_id[8:]), "source": "ARCHIVE"})
    except (requests.RequestException, ValueError, LookupError):
        return jsonify({"error": "Audio no disponible"}), 404


@app.get("/api/play/<path:item_id>")
def api_play(item_id):
    """One paid request from the native audio element; Range stays with the origin."""
    if not rate_allowed("play", 90):
        return jsonify({"error": "Límite temporal de reproducción"}), 429
    if item_id.startswith("audius_"):
        ident = item_id[7:]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident):
            return jsonify({"error": "Identificador no válido"}), 400
        host = "discoveryprovider2.audius.co" if request.args.get("retry") == "1" else "api.audius.co"
        return redirect(f"https://{host}/v1/tracks/{quote(ident)}/stream?app_name={quote(AUDIUS_APP_NAME)}", code=302)
    if item_id.startswith("archive_"):
        try:
            ident = item_id[8:]
            if request.args.get("retry") == "1":
                with _cache_lock: _archive_cache.pop(ident, None)
            return redirect(archive_stream_url(ident), code=302)
        except ValueError:
            return jsonify({"error": "Identificador no válido"}), 400
        except (requests.RequestException, LookupError, TypeError):
            return jsonify({"error": "Esta pista no ofrece audio público compatible"}), 404
    return jsonify({"error": "Fuente no disponible"}), 404


# El proxy mantiene la compatibilidad con el proyecto previo. Nunca sigue
# redirecciones automáticamente; cada destino se valida nuevamente.
def allowed_stream_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        return (host == "archive.org" or host.endswith(".archive.org")
                or host == "audius.co" or host.endswith(".audius.co"))
    except ValueError:
        return False


def _safe_upstream(url: str, headers: dict):
    for _ in range(4):
        if not allowed_stream_url(url):
            raise ValueError("Destino no permitido")
        response = requests.get(url, headers=headers, stream=True,
                                allow_redirects=False, timeout=REQUEST_TIMEOUT)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        next_url = urljoin(url, response.headers.get("Location", ""))
        response.close()
        url = next_url
    raise ValueError("Demasiadas redirecciones")


@app.get("/api/proxy")
def api_proxy():
    if not rate_allowed("proxy", 12):
        return jsonify({"error": "Límite temporal de reproducción"}), 429
    url = request.args.get("url", "")
    if not allowed_stream_url(url):
        return jsonify({"error": "Origen no permitido"}), 403
    headers = {"User-Agent": "MAGGY/7.0", "Accept": "audio/*,*/*;q=0.8"}
    requested_range = request.headers.get("Range", "")
    if requested_range:
        if not re.fullmatch(r"bytes=\d{0,12}-\d{0,12}", requested_range):
            return jsonify({"error": "Rango no válido"}), 416
        headers["Range"] = requested_range
    try:
        upstream = _safe_upstream(url, headers)
        if upstream.status_code not in (200, 206):
            upstream.close()
            return jsonify({"error": "El origen no respondió correctamente"}), 502
        size = int(upstream.headers.get("Content-Length", "0") or 0)
        if size > MAX_PROXY_BYTES:
            upstream.close()
            return jsonify({"error": "Audio demasiado grande para el proxy"}), 413
        content_type = upstream.headers.get("Content-Type", "application/octet-stream")
        if not (content_type.startswith("audio/") or content_type.startswith("application/octet-stream")):
            upstream.close()
            return jsonify({"error": "El origen no proporcionó audio"}), 502
        forward_headers = {k: v for k in ("Content-Type", "Content-Range", "Accept-Ranges")
                           if (v := upstream.headers.get(k))}
        # No se anuncia Content-Length: el máximo también se aplica durante streaming.
        def chunks():
            sent = 0
            try:
                for piece in upstream.iter_content(chunk_size=64 * 1024):
                    if not piece:
                        continue
                    if sent + len(piece) > MAX_PROXY_BYTES:
                        break
                    sent += len(piece)
                    yield piece
            finally:
                upstream.close()
        return Response(stream_with_context(chunks()),
                        status=upstream.status_code, headers=forward_headers)
    except (requests.RequestException, ValueError, OSError) as exc:
        app.logger.warning("Audio proxy failed: %s", type(exc).__name__)
        return jsonify({"error": "No se pudo reproducir este audio"}), 502


from membership import install as install_membership
install_membership(app)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8080")), debug=False)
