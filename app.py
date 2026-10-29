# -*- coding: utf-8 -*-
"""MAGGY PRO 8.8.0 — API musical y distribución web.

Proyecto y edición: Iván Marcos Illa.
El código de servicios externos y sus marcas pertenece a sus titulares.
Firma de edición: MAGGY / Iván Marcos Illa / 2026-10-24.
"""

from __future__ import annotations

import concurrent.futures
import ipaddress
import html
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

VERSION = "9.13.5"
AUDIUS_APP_NAME = os.getenv("AUDIUS_APP_NAME", "electronicama")
SEARCH_CACHE_SECONDS = max(15, min(int(os.getenv("SEARCH_CACHE_SECONDS", "300")), 3600))
ARCHIVE_CACHE_SECONDS = max(60, min(int(os.getenv("ARCHIVE_CACHE_SECONDS", "3600")), 86400))
REQUEST_TIMEOUT = (2.5, 6)
MAX_PROXY_BYTES = 32 * 1024 * 1024
AUDIO_CHUNK_BYTES = 512 * 1024
# Exact Audius validator storage observed in its official signed redirects.
AUDIUS_STORAGE_HOST = "validator.eeba4a6ca56a0d87af802270217c2a51.r2.cloudflarestorage.com"
MAX_SEARCH_LENGTH = 90

# Cachés pequeñas, con bloqueo. En Vercel son por instancia: no persistentes ni compartidas.
_cache_lock = threading.RLock()
_search_cache: OrderedDict[tuple, tuple[float, list]] = OrderedDict()
_archive_cache: OrderedDict[str, tuple[float, str]] = OrderedDict()
_commons_cache: OrderedDict[str, tuple] = OrderedDict()
_radio_cache: OrderedDict[str, tuple] = OrderedDict()
_youtube_cache: OrderedDict[tuple, tuple] = OrderedDict()
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
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": f"Maggy/{VERSION} (https://electronicama.com; music catalogue)"})
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
                  "rows": limit, "page": page, "output": "json"}
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


def search_audius(query: str, limit: int = 10, page: int = 1) -> list:
    for endpoint in AUDIUS_ENDPOINTS:
        try:
            tracks = fetch_json(endpoint, {"query": query, "app_name": AUDIUS_APP_NAME, "limit": limit, "offset": (page - 1) * limit}, timeout=(2, 3)).get("data", [])
            if not tracks:
                continue
            results = []
            for track in tracks[:limit]:
                if track.get("is_explicit") is True: continue
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










def commons_track(page):
    info = (page.get("imageinfo") or [{}])[0]
    metadata = info.get("extmetadata") or {}
    def text(name):
        return html.unescape(re.sub(r"<[^>]+>", " ", str((metadata.get(name) or {}).get("value", "")))).strip()
    license_name = text("LicenseShortName")
    if not re.fullmatch(r"(?:CC0|Public domain|PD|CC BY(?:-SA)? [1-4]\.\d)", license_name, re.I):
        return None
    url = info.get("url", "")
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "upload.wikimedia.org" or info.get("mime") not in {"audio/mpeg", "audio/ogg", "audio/flac", "audio/x-flac", "audio/wav", "audio/x-wav", "audio/mp4"}:
        return None
    ident = str(page.get("pageid", ""))
    if not ident.isdigit(): return None
    artist = text("Artist") or text("Credit") or "Autor indicado en Wikimedia Commons"
    title = str(page.get("title", "Grabación musical")).removeprefix("File:")
    title = re.sub(r"\.(ogg|oga|opus|mp3|wav|flac|m4a)$", "", title, flags=re.I).replace("_", " ")
    page_url = "https://commons.wikimedia.org/?curid=" + ident
    license_url = (metadata.get("LicenseUrl") or {}).get("value", "")
    if not str(license_url).startswith("https://creativecommons.org/"):
        license_url = page_url
    track = {"id": "commons_" + ident, "title": title[:180], "channel": artist[:120], "source": "COMMONS", "thumbnail": "",
             "mime": info["mime"], "license": license_name, "license_url": license_url,
             "attribution": text("Attribution") or artist, "page_url": page_url, "url": page_url, "stream_url": url}
    cached_put(_commons_cache, ident, track)
    return track


def search_commons(query, limit=50, page=1):
    params = {"action": "query", "format": "json", "formatversion": 2, "generator": "search",
              "gsrsearch": "filetype:audio " + query, "gsrnamespace": 6, "gsrlimit": limit,
              "gsroffset": (page-1)*limit, "prop": "imageinfo", "iiprop": "url|mime|extmetadata"}
    try:
        response = fetch_json("https://commons.wikimedia.org/w/api.php", params)
        pages = response.get("query", {}).get("pages", [])
        return [track for page in sorted(pages, key=lambda p: p.get("index", 0)) if (track := commons_track(page))]
    except (requests.RequestException, ValueError, TypeError) as exc:
        app.logger.warning("Commons search failed: %s", type(exc).__name__)
        return []


def resolve_commons(ident):
    if not re.fullmatch(r"[0-9]{1,12}", ident): raise ValueError("Identificador no válido")
    track = cached_get(_commons_cache, ident, 3600)
    if track: return track
    result = fetch_json("https://commons.wikimedia.org/w/api.php", {"action":"query", "format":"json", "formatversion":2,
                        "pageids": ident, "prop":"imageinfo", "iiprop":"url|mime|extmetadata"})
    for page in result.get("query", {}).get("pages", []):
        track = commons_track(page)
        if track: return track
    raise LookupError("No hay audio con licencia compatible")


RADIO_API_HOSTS = ("de1.api.radio-browser.info", "nl1.api.radio-browser.info")


def radio_track(station):
    ident = str(station.get("stationuuid", ""))
    if not re.fullmatch(r"[a-fA-F0-9-]{36}", ident): return None
    stream = str(station.get("url_resolved") or station.get("url") or "")
    try:
        parsed = urlparse(stream)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or not host or host in {"localhost", "localhost.localdomain"} or host.endswith((".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global: return None
        except ValueError: pass
        if parsed.path.lower().endswith((".m3u", ".pls", ".m3u8")): return None
    except ValueError: return None
    if str(station.get("lastcheckok", "")) != "1" or str(station.get("codec", "")).upper() not in {"MP3", "AAC", "AAC+", "AAC-LC"}: return None
    page_url = "https://www.radio-browser.info/history/" + ident
    track = {"id":"radio_" + ident, "title":str(station.get("name") or "Radio en directo").strip()[:180],
             "channel":"En directo · " + str(station.get("country") or "Radio internacional")[:90], "source":"RADIO",
             "thumbnail":str(station.get("favicon") or ""), "stream_url":stream, "page_url":page_url, "url":page_url,
             "attribution":"Emisora en directo. Catálogo de Radio Browser; los contenidos y condiciones dependen de la emisora."}
    cached_put(_radio_cache, ident, track)
    return track


def search_radio(query, limit=12, page=1):
    for host in RADIO_API_HOSTS:
        try:
            stations = fetch_json(f"https://{host}/json/stations/search", {"name":query, "limit":limit*2, "offset":(page-1)*limit*2,
                                  "hidebroken":"true", "order":"clickcount", "reverse":"true"}, timeout=(2,3))
            if not isinstance(stations, list): continue
            return [track for station in stations if (track := radio_track(station))][:limit]
        except (requests.RequestException, ValueError, TypeError): continue
    return []


def resolve_radio(ident):
    if not re.fullmatch(r"[a-fA-F0-9-]{36}", ident): raise ValueError("Identificador no válido")
    hit = cached_get(_radio_cache, ident, 1800)
    if hit: return hit
    for host in RADIO_API_HOSTS:
        try:
            stations = fetch_json(f"https://{host}/json/stations/byuuid/{ident}", timeout=(2,3))
            for station in stations:
                track = radio_track(station)
                if track: return track
        except (requests.RequestException, ValueError, TypeError): continue
    raise LookupError("No hay una emisión HTTPS compatible")


class YouTubeUnavailable(Exception):
    def __init__(self, code, message, status=503):
        self.code,self.message,self.status=code,message,status


def search_youtube(query, page=1):
    key=os.getenv('YOUTUBE_API_KEY','').strip()
    if not key:raise YouTubeUnavailable('youtube_not_configured','YouTube aún no está configurado. Administración debe revisar YOUTUBE_API_KEY en Vercel.')
    if page>3:return []
    query=sanitize_query(query)
    cached=cached_get(_youtube_cache,(query.casefold(),page),600)
    if cached is not None:return cached['tracks']
    token=''
    if page>1:
        search_youtube(query,page-1)
        previous=cached_get(_youtube_cache,(query.casefold(),page-1),600)
        token=(previous or {}).get('next','')
        if not token:return []
    params={'part':'snippet','q':query,'maxResults':50,'type':'video','videoCategoryId':'10','videoEmbeddable':'true','videoSyndicated':'true','safeSearch':'strict','relevanceLanguage':'es','key':key}
    if token:params['pageToken']=token
    try:
        response=requests.get('https://www.googleapis.com/youtube/v3/search',params=params,timeout=(2.5,6))
        if response.status_code!=200:
            if response.status_code in (403,429):raise YouTubeUnavailable('youtube_access_or_quota','YouTube ha limitado la consulta. Revisa la cuota y los permisos de la API en Google Cloud.')
            raise YouTubeUnavailable('youtube_unavailable','YouTube no responde ahora. Vuelve a intentarlo.')
        data=response.json();tracks=[]
        if not isinstance(data,dict):raise ValueError('provider response')
        for item in data.get('items',[]):
            ident=(item.get('id') or {}).get('videoId','');snippet=item.get('snippet') or {}
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident):continue
            tracks.append({'id':'youtube_'+ident,'video_id':ident,'source':'YOUTUBE','title':html.unescape(str(snippet.get('title') or 'YouTube'))[:140],'channel':html.unescape(str(snippet.get('channelTitle') or 'YouTube'))[:90],'description':str(snippet.get('description') or '')[:600],'thumbnail':'https://i.ytimg.com/vi/'+ident+'/hqdefault.jpg','url':'https://www.youtube.com/watch?v='+ident})
        cached_put(_youtube_cache,(query.casefold(),page),{'tracks':tracks,'next':str(data.get('nextPageToken') or '')})
        return tracks
    except (requests.RequestException,ValueError,TypeError):
        # Never log provider exceptions: their URL may contain the private API key.
        raise YouTubeUnavailable('youtube_unavailable','No se pudo consultar YouTube. Vuelve a intentarlo.') from None


def multi_search(query: str, page: int = 1, source: str = "ALL") -> list:
    cache_key = (normalize(query), page, source)
    ranking_query = provider_query(query)
    hit = cached_get(_search_cache, cache_key, SEARCH_CACHE_SECONDS)
    if hit is not None:
        return hit
    if source == "MIX":
        candidates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            jobs = [pool.submit(search_commons, query, page=page), pool.submit(search_radio, query, page=page)]
            for job in concurrent.futures.as_completed(jobs):
                try: candidates.extend(job.result())
                except Exception: app.logger.warning("A mix provider failed")
    elif source == "RADIO":
        candidates = search_radio(query, page=page)
    elif source == "COMMONS":
        candidates = search_commons(query, page=page)
    elif source == "AUDIUS":
        candidates = search_audius(query, limit=60, page=page)
    elif source == "ARCHIVE":
        candidates = search_archive(query, limit=60, page=page)
    else:
        workers = [(search_archive, 60), (search_audius, 60)]
        candidates = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(workers)) as pool:
            futures = [pool.submit(fn, query, n, page=page) for fn, n in workers]
            for future in concurrent.futures.as_completed(futures):
                try:
                    candidates.extend(future.result() or [])
                except Exception:
                    app.logger.exception("A provider failed")
    seen = set()
    scored = []
    for item in candidates:
        if item.get("source") not in {"ARCHIVE", "AUDIUS", "COMMONS", "RADIO"}:
            continue
        ident = (item.get("source"), item.get("id"))
        score = 1 if item.get("source") in {"COMMONS", "RADIO"} else relevance(item, ranking_query)
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
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), display-capture=(self), geolocation=()" if request.path in {"/streamers","/live"} else "camera=(self), microphone=(), display-capture=(), geolocation=()" if request.path=="/" else "camera=(), microphone=(), display-capture=(), geolocation=()"
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
                    "providers": ["ARCHIVE", "AUDIUS", "COMMONS", "RADIO"] + (["YOUTUBE"] if os.getenv("YOUTUBE_API_KEY", "").strip() else []),
                    "youtube_configured": bool(os.getenv("YOUTUBE_API_KEY", "").strip()),
                    "search_cache": "instance-local"})






def catalogue_response(tracks):
    # Public playback metadata; never return internal provider/debug fields.
    fields={'id','title','channel','description','source','thumbnail','url','stream_url','mime','license','license_url','attribution','page_url','video_id'}
    return [{key:value for key,value in track.items() if key in fields}|{'locked':False} for track in tracks]


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
    if source not in {"ALL", "ARCHIVE", "AUDIUS", "COMMONS", "RADIO", "MIX", "YOUTUBE"}:
        return jsonify({"error": "Plataforma no válida"}), 400
    if source=='YOUTUBE':
        if not rate_allowed('youtube-search',12):return jsonify(error='Espera un minuto antes de repetir la búsqueda de YouTube.'),429
        try:return jsonify(catalogue_response(search_youtube(query,page)))
        except YouTubeUnavailable as error:return jsonify(error=error.message,code=error.code),error.status
    tracks = multi_search(query, page=page) if source == "ALL" else multi_search(query, page=page, source=source)
    return jsonify(catalogue_response(tracks))


@app.get('/api/admin/youtube-diagnostic')
def youtube_diagnostic():
    from membership import get_user
    user=get_user()
    if not user or user['role']!='admin':return jsonify(error='Se requiere administración.'),403
    if not rate_allowed('youtube-diagnostic',2):return jsonify(error='Espera un minuto antes de repetir la prueba.'),429
    try:
        tracks=search_youtube('piano',1)
        return jsonify(configured=True,connected=True,result_count=len(tracks),message='Conexión con YouTube comprobada. Los vídeos bloqueados dependen de cada creador.')
    except YouTubeUnavailable as error:
        return jsonify(configured=bool(os.getenv('YOUTUBE_API_KEY','').strip()),connected=False,error=error.message,code=error.code),error.status


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
    """Authorize native playback; Audius uses bounded, same-origin byte ranges."""
    if not rate_allowed("play", 90):
        return jsonify({"error": "Límite temporal de reproducción"}), 429
    if item_id.startswith("radio_"):
        try:
            return redirect(resolve_radio(item_id[6:])["stream_url"], code=302)
        except ValueError:
            return jsonify({"error": "Identificador no válido"}), 400
        except LookupError:
            return jsonify({"error": "Emisora no disponible"}), 404
    if item_id.startswith("commons_"):
        try:
            track = resolve_commons(item_id[8:])
            return relay_audio(track["stream_url"], track["mime"])
        except ValueError:
            return jsonify({"error": "Identificador no válido"}), 400
        except (requests.RequestException, LookupError, TypeError):
            return jsonify({"error": "Grabación no disponible"}), 404
    if item_id.startswith("audius_"):
        ident = item_id[7:]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", ident):
            return jsonify({"error": "Identificador no válido"}), 400
        host = "discoveryprovider2.audius.co" if request.args.get("retry") == "1" else "api.audius.co"
        return relay_audio(f"https://{host}/v1/tracks/{quote(ident)}/stream?app_name={quote(AUDIUS_APP_NAME)}")
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
        return (host == AUDIUS_STORAGE_HOST or host == "upload.wikimedia.org" or host == "archive.org" or host.endswith(".archive.org")
                or host == "audius.co" or host.endswith(".audius.co"))
    except ValueError:
        return False


def _safe_upstream(url: str, headers: dict):
    for _ in range(4):
        if not allowed_stream_url(url):
            raise ValueError("Destino no permitido")
        response = requests.get(url, headers={"User-Agent": f"Maggy/{VERSION} (https://electronicama.com; music catalogue)", **headers}, stream=True,
                                allow_redirects=False, timeout=REQUEST_TIMEOUT)
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        next_url = urljoin(url, response.headers.get("Location", ""))
        response.close()
        url = next_url
    raise ValueError("Demasiadas redirecciones")


def relay_audio(url, expected_mime="audio/mpeg"):
    """Small, bounded byte ranges: Safari can seek without cross-site redirects."""
    requested = request.headers.get("Range", "bytes=0-")
    match = re.fullmatch(r"bytes=(\d{0,12})-(\d{0,12})", requested)
    if not match or not any(match.groups()):
        return jsonify({"error": "Rango no válido"}), 416
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), start + AUDIO_CHUNK_BYTES - 1) if last else start + AUDIO_CHUNK_BYTES - 1
        if end < start:
            return jsonify({"error": "Rango no válido"}), 416
        byte_range = f"bytes={start}-{end}"
    else:
        byte_range = f"bytes=-{min(int(last), AUDIO_CHUNK_BYTES)}"
    try:
        upstream = _safe_upstream(url, {"Range": byte_range, "Accept": "audio/*,application/octet-stream", "Accept-Encoding": "identity"})
        if upstream.status_code == 416:
            headers = {"Content-Range": upstream.headers.get("Content-Range", "bytes */*")}
            upstream.close()
            return Response(status=416, headers=headers)
        size = int(upstream.headers.get("Content-Length", "0") or 0)
        kind = upstream.headers.get("Content-Type", "application/octet-stream").split(";")[0].lower()
        if upstream.status_code not in (200, 206) or not (kind.startswith("audio/") or kind in {"application/ogg", "application/octet-stream"}):
            upstream.close()
            return jsonify({"error": "La fuente no entregó audio reproducible", "code": "provider_unavailable", "provider_status": upstream.status_code, "provider_type": kind}), 502
        if size > AUDIO_CHUNK_BYTES or (upstream.status_code == 206 and not upstream.headers.get("Content-Range")):
            upstream.close()
            return jsonify({"error": "La fuente no admite la descarga parcial solicitada", "code": "provider_range_error"}), 502
        forwarded = {key: upstream.headers[key] for key in ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"] if key in upstream.headers}
        if kind == "application/octet-stream": forwarded["Content-Type"] = expected_mime
        elif kind == "application/ogg": forwarded["Content-Type"] = "audio/ogg"
        def chunks():
            total = 0
            try:
                for chunk in upstream.iter_content(64 * 1024):
                    total += len(chunk)
                    if total > AUDIO_CHUNK_BYTES: break
                    if chunk: yield chunk
            finally:
                upstream.close()
        return Response(stream_with_context(chunks()), status=upstream.status_code, headers=forwarded)
    except (requests.RequestException, ValueError, OSError) as exc:
        app.logger.warning("Audio relay failed: %s", type(exc).__name__)
        return jsonify({"error": "No se pudo conectar con el audio de la fuente", "code": "provider_connection_error"}), 502


@app.get("/api/admin/audio-diagnostic/<track_id>")
def audio_diagnostic(track_id):
    from membership import get_user
    user = get_user()
    if not user or user["role"] != "admin":
        return jsonify({"error": "Se requiere administración"}), 403
    if not rate_allowed("audio-diagnostic", 6):
        return jsonify({"error": "Espera un minuto"}), 429
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", track_id):
        return jsonify({"error": "Identificador no válido"}), 400
    start = time.monotonic()
    try:
        url = resolve_commons(track_id[8:])["stream_url"] if track_id.startswith("commons_") else f"https://api.audius.co/v1/tracks/{quote(track_id)}/stream?app_name={quote(AUDIUS_APP_NAME)}"
        upstream = _safe_upstream(url, {"Range": "bytes=0-2047", "Accept-Encoding": "identity"})
        try:
            data = next(upstream.iter_content(2048), b"")
            return jsonify(authorization="ok", provider_status=upstream.status_code,
                           content_type=upstream.headers.get("Content-Type"), bytes_received=len(data),
                           elapsed_ms=round((time.monotonic()-start)*1000))
        finally:
            upstream.close()
    except (requests.RequestException, ValueError, LookupError, OSError) as exc:
        return jsonify(authorization="ok", provider_error=type(exc).__name__, elapsed_ms=round((time.monotonic()-start)*1000)), 502


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
from streamers import install as install_streamers
install_streamers(app,rate_allowed)
from two_factor import install as install_two_factor
install_two_factor(app)
from subscriptions import install as install_subscriptions
install_subscriptions(app)
from community import install as install_community
install_community(app)
from notifications import install as install_notifications
install_notifications(app)
from rewards import install as install_rewards
install_rewards(app)
from founders import install as install_founders
install_founders(app)
from live_access import install as install_live_access
install_live_access(app)
from human_check import install as install_human_check
install_human_check(app)
from sounds import install as install_sounds
install_sounds(app)


from analytics import install as install_analytics
install_analytics(app)


from operations import install as install_operations
install_operations(app)
from payments import install as install_payments
install_payments(app)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8080")), debug=False)
