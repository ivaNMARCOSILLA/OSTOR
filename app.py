from flask import Flask, request, jsonify, send_from_directory, session, redirect, render_template_string, Response, stream_with_context
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from urllib.parse import quote, urlparse
import os
import functools
import requests
import concurrent.futures
import time
import secrets
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
CORS(app, supports_credentials=True)

# ConfiguraciÃ³n: no se guardan credenciales reales en el cÃ³digo.
OSTO_PASSWORD = os.environ.get("OSTO_PASSWORD", "")
SECRET_KEY = os.environ.get("SECRET_KEY", "")
JAMENDO_CLIENT_ID = os.environ.get("JAMENDO_CLIENT_ID", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
AUDIUS_APP_NAME = os.environ.get("AUDIUS_APP_NAME", "osto")

if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
app.secret_key = SECRET_KEY

ARCHIVE_TTL = int(os.environ.get("ARCHIVE_CACHE_TTL", "3600"))
REQUEST_TIMEOUT = (5, 15)

_archive_cache = {}
_cache_time = {}

LOGIN_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#07100c"><title>OSTO Â· Acceso</title>
<style>
:root{color-scheme:dark;--bg:#050807;--card:#0c1310;--line:#1c3027;--text:#effff7;--muted:#719286;--accent:#00e5a0}
*{box-sizing:border-box}body{margin:0;min-height:100svh;display:grid;place-items:center;background:radial-gradient(circle at 20% 10%,#0c3b2b 0,transparent 35%),var(--bg);color:var(--text);font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:20px}
.box{width:min(420px,100%);padding:32px;border:1px solid var(--line);border-radius:28px;background:linear-gradient(180deg,#0e1713,#080d0b);box-shadow:0 24px 80px #0009}
.logo{text-align:center;font-size:32px;font-weight:850;letter-spacing:-1.5px}.logo b{color:var(--accent)}.sub{text-align:center;color:var(--muted);font-size:12px;margin:8px 0 28px}
input{width:100%;padding:15px 16px;border:1px solid var(--line);border-radius:15px;background:#060a08;color:#fff;font-size:16px;outline:0}input:focus{border-color:var(--accent);box-shadow:0 0 0 4px #00e5a022}
button{width:100%;margin-top:12px;padding:15px;border:0;border-radius:15px;background:var(--accent);color:#00150e;font-weight:850;font-size:15px;cursor:pointer}
.err{margin-top:12px;text-align:center;color:#ff6684;font-size:13px}
</style></head>
<body><main class="box"><div class="logo">OSTO<b>Â·</b>MULTI</div><div class="sub">Acceso privado</div>
<form method="post" action="/login" autocomplete="on">
<input type="password" name="password" placeholder="ContraseÃ±a" autocomplete="current-password" required autofocus>
<button type="submit">Entrar</button>
{% if error %}<div class="err">{{ error }}</div>{% endif %}
</form></main></body></html>"""

def login_required(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("osto_auth"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "No autorizado"}), 401
            return redirect("/login")
        return fn(*args, **kwargs)
    return wrapper

@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    resp.headers["Permissions-Policy"] = "microphone=(), camera=(), geolocation=()"
    if request.path.endswith((".html", "/")):
        resp.headers["Cache-Control"] = "no-store"
    return resp

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if OSTO_PASSWORD and secrets.compare_digest(request.form.get("password", ""), OSTO_PASSWORD):
            session.clear()
            session["osto_auth"] = True
            session.permanent = True
            return redirect("/")
        error = "ContraseÃ±a incorrecta"
    return render_template_string(LOGIN_HTML, error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/manifest.webmanifest")
def manifest():
    return send_from_directory(BASE_DIR, "manifest.webmanifest", mimetype="application/manifest+json")

@app.route("/sw.js")
def service_worker():
    return send_from_directory(BASE_DIR, "sw.js", mimetype="application/javascript")

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "6.0",
        "audio": "direct-stream-with-range-proxy",
        "configured": {
            "password": bool(OSTO_PASSWORD),
            "jamendo": bool(JAMENDO_CLIENT_ID),
            "youtube": bool(YOUTUBE_API_KEY)
        }
    })

def _archive_file_url(identifier):
    now = time.time()
    if identifier in _archive_cache and now - _cache_time.get(identifier, 0) < ARCHIVE_TTL:
        return _archive_cache[identifier]
    r = requests.get(f"https://archive.org/metadata/{quote(identifier, safe='')}", timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    files = r.json().get("files", [])
    audio = [
        f for f in files
        if f.get("name", "").lower().endswith((".mp3", ".m4a", ".ogg", ".opus"))
        and "spectrogram" not in f.get("name", "").lower()
        and "waveform" not in f.get("name", "").lower()
    ]
    audio.sort(key=lambda f: int(f.get("size", 0) or 0), reverse=True)
    if not audio:
        raise RuntimeError("El elemento no contiene un audio compatible")
    name = quote(audio[0]["name"], safe="/")
    url = f"https://archive.org/download/{quote(identifier, safe='')}/{name}"
    _archive_cache[identifier] = url
    _cache_time[identifier] = now
    return url

def search_archive(query, limit=7, page=1):
    try:
        params = {
            "q": f"({query}) AND mediatype:audio",
            "fl[]": ["identifier", "title", "creator", "description"],
            "sort[]": ["downloads desc"],
            "rows": limit * 4,
            "page": page,
            "output": "json",
        }
        data = requests.get("https://archive.org/advancedsearch.php", params=params, timeout=REQUEST_TIMEOUT).json()
        docs = [d for d in data.get("response", {}).get("docs", []) if d.get("identifier")][:limit]
        out = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(docs) or 1)) as pool:
            futures = {pool.submit(_archive_file_url, d["identifier"]): d for d in docs}
            for f in concurrent.futures.as_completed(futures):
                d = futures[f]
                try:
                    identifier = d["identifier"]
                    title = d.get("title", "Sin tÃ­tulo")
                    creator = d.get("creator", "Archive")
                    out.append({
                        "id": f"archive_{identifier}",
                        "title": str(title[0] if isinstance(title, list) else title)[:140],
                        "channel": str(creator[0] if isinstance(creator, list) else creator)[:90],
                        "description": str(d.get("description", ""))[:600],
                        "thumbnail": f"https://archive.org/services/img/{identifier}",
                        "url": f"https://archive.org/details/{identifier}",
                        "stream_url": f.result(),
                        "source": "ARCHIVE",
                    })
                except Exception as exc:
                    app.logger.warning("Archive item error: %s", exc)
        return out
    except Exception as exc:
        app.logger.warning("Archive search error: %s", exc)
        return []

def search_audius(query, limit=7):
    endpoints = [
        "https://discoveryprovider.audius.co/v1/tracks/search",
        "https://audius-discovery-1.cultur3stake.com/v1/tracks/search",
        "https://discoveryprovider2.audius.co/v1/tracks/search",
    ]
    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, params={"query": query, "app_name": AUDIUS_APP_NAME}, timeout=REQUEST_TIMEOUT)
            if r.ok:
                tracks = r.json().get("data", [])
                if tracks:
                    result = []
                    for t in tracks[:limit]:
                        art = t.get("artwork") or {}
                        result.append({
                            "id": f"audius_{t.get('id')}",
                            "title": str(t.get("title", "Track"))[:140],
                            "channel": str((t.get("user") or {}).get("name", "Audius"))[:90],
                            "description": str(t.get("description", ""))[:600],
                            "thumbnail": art.get("1000x1000") or art.get("480x480") or art.get("150x150") or "",
                            "url": f"https://audius.co{t.get('permalink','')}" if t.get("permalink") else f"https://audius.co/tracks/{t.get('id')}",
                            "stream_url": f"https://discoveryprovider.audius.co/v1/tracks/{t.get('id')}/stream?app_name={quote(AUDIUS_APP_NAME)}",
                            "source": "AUDIUS",
                        })
                    return result
        except requests.RequestException:
            continue
    return []

def search_jamendo(query, limit=7):
    if not JAMENDO_CLIENT_ID:
        return []
    try:
        params = {
            "client_id": JAMENDO_CLIENT_ID, "format": "json", "limit": limit,
            "search": query, "audioformat": "mp32", "include": "musicinfo+licenses", "imagesize": "300"
        }
        tracks = requests.get("https://api.jamendo.com/v3.0/tracks/", params=params, timeout=REQUEST_TIMEOUT).json().get("results", [])
        return [{
            "id": f"jamendo_{t.get('id')}",
            "title": str(t.get("name", "Track"))[:140],
            "channel": str(t.get("artist_name", "Jamendo"))[:90],
            "description": f"{t.get('album_name','')} Â· {t.get('artist_name','')}",
            "thumbnail": t.get("image") or t.get("album_image") or "",
            "url": t.get("shareurl") or f"https://www.jamendo.com/track/{t.get('id')}",
            "stream_url": t.get("audio") or t.get("audiodownload") or "",
            "source": "JAMENDO",
        } for t in tracks]
    except Exception as exc:
        app.logger.warning("Jamendo error: %s", exc)
        return []

def search_youtube(query, limit=5):
    if not YOUTUBE_API_KEY:
        return []
    try:
        params = {"part": "snippet", "q": query, "maxResults": limit, "type": "video",
                  "videoCategoryId": "10", "key": YOUTUBE_API_KEY}
        items = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=REQUEST_TIMEOUT).json().get("items", [])
        return [{
            "id": f"youtube_{i['id'].get('videoId')}",
            "title": str(i["snippet"].get("title", "YouTube"))[:140],
            "channel": str(i["snippet"].get("channelTitle", ""))[:90],
            "description": str(i["snippet"].get("description", ""))[:600],
            "thumbnail": i["snippet"].get("thumbnails", {}).get("high", {}).get("url", ""),
            "url": f"https://www.youtube.com/watch?v={i['id'].get('videoId')}",
            "source": "YOUTUBE",
            "video_id": i["id"].get("videoId"),
        } for i in items]
    except Exception as exc:
        app.logger.warning("YouTube error: %s", exc)
        return []

def multi_search(query, limit=60, page=1):
    if page > 1:
        return search_archive(query, limit=20, page=page)
    funcs = [search_archive, search_audius, search_jamendo]
    if YOUTUBE_API_KEY:
        funcs.append(search_youtube)
    per = max(4, limit // len(funcs))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(funcs)) as pool:
        futures = [pool.submit(fn, query, per) for fn in funcs]
        for f in concurrent.futures.as_completed(futures):
            try:
                results.extend(f.result() or [])
            except Exception as exc:
                app.logger.warning("Search source error: %s", exc)
    # DeduplicaciÃ³n estable.
    seen, clean = set(), []
    for item in results:
        key = (item.get("source"), item.get("id"))
        if key not in seen:
            seen.add(key); clean.append(item)
    return clean[:limit]

@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()[:160]
    if not q:
        return jsonify([])
    try:
        page = max(1, min(int(request.args.get("page", "1")), 100))
    except ValueError:
        page = 1
    return jsonify(multi_search(q, page=page))

@app.route("/api/trending")
def api_trending():
    return jsonify(multi_search("lofi chill jazz", 20))

@app.route("/api/resolve/<path:item_id>")
def api_resolve(item_id):
    if item_id.startswith("archive_"):
        identifier = item_id[len("archive_"):]
        try:
            return jsonify({"id": item_id, "stream_url": _archive_file_url(identifier), "source": "ARCHIVE"})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 404
    return jsonify({"id": item_id, "stream_url": ""})

ALLOWED_STREAM_HOSTS = {
    "archive.org", "ia800", "ia801", "ia802", "ia803", "ia804", "ia805", "ia806", "ia807", "ia808", "ia809",
    "audius.co", "jamendo.com", "cdn.jamendo.com", "mp3l.jamendo.com"
}

def allowed_stream_url(raw):
    try:
        u = urlparse(raw)
        host = (u.hostname or "").lower().rstrip(".")
        if u.scheme != "https" or not host:
            return False
        if host in ALLOWED_STREAM_HOSTS or host.endswith(".archive.org") or host.endswith(".audius.co") or host.endswith(".jamendo.com"):
            return True
    except Exception:
        pass
    return False

@app.route("/api/proxy")
@login_required
def api_proxy():
    target = request.args.get("url", "")
    if not allowed_stream_url(target):
        return jsonify({"error": "Origen no permitido"}), 403
    headers = {"User-Agent": "OSTO/6.0", "Accept": "audio/*,*/*;q=0.8"}
    if request.headers.get("Range"):
        headers["Range"] = request.headers["Range"]
    try:
        upstream = requests.get(target, headers=headers, stream=True, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if not upstream.ok and upstream.status_code != 206:
            return jsonify({"error": f"Origen respondiÃ³ {upstream.status_code}"}), 502

        response_headers = {}
        for name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges", "ETag", "Last-Modified"):
            if upstream.headers.get(name):
                response_headers[name] = upstream.headers[name]
        response_headers["Cache-Control"] = "private, max-age=60"
        status = 206 if upstream.status_code == 206 else 200

        def generate():
            try:
                for chunk in upstream.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        return Response(stream_with_context(generate()), status=status, headers=response_headers,
                        direct_passthrough=True)
    except requests.RequestException as exc:
        return jsonify({"error": f"No se pudo abrir el audio: {exc}"}), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)



