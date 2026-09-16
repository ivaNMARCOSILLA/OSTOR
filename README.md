# OSTO Multi

Aplicación web/PWA para buscar y reproducir audio desde fuentes compatibles.

## Arranque local

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
# .venv\Scripts\activate

pip install -r requirements.txt
export OSTO_PASSWORD="cambia-esto"
export SECRET_KEY="genera-una-clave-larga"
python app.py
```

Abre `http://localhost:8080`.

## Docker

```bash
docker build -t osto .
docker run --rm -p 8080:8080 \
  -e OSTO_PASSWORD="cambia-esto" \
  -e SECRET_KEY="una-clave-larga-y-aleatoria" \
  osto
```

## Variables

- `OSTO_PASSWORD`: obligatoria para acceder.
- `SECRET_KEY`: clave persistente y aleatoria para las sesiones.
- `JAMENDO_CLIENT_ID`: opcional.
- `YOUTUBE_API_KEY`: opcional; los resultados de YouTube se reproducen dentro del reproductor de OSTO mediante el reproductor oficial embebido de YouTube.
- `AUDIUS_APP_NAME`: nombre de la aplicación enviado a Audius.
- `PORT`: puerto HTTP, por defecto `8080`.
- `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`: ajustes del servidor.

No pongas claves ni contraseñas reales dentro de `app.py`, HTML o README.

## Móvil

El proyecto incluye manifest y service worker para instalarse como PWA. En navegadores compatibles puede abrirse como aplicación independiente.

La reproducción directa usa `<audio>` y Media Session cuando el navegador lo admite, por lo que el sistema puede mostrar controles en la pantalla bloqueada/notificaciones y mantener el audio mientras se navega o se minimiza el reproductor.

El comportamiento exacto en segundo plano depende del navegador y del sistema operativo. En iOS/Android no es posible convertir una página web en una reproducción de YouTube equivalente a una suscripción Premium: el contenido de YouTube sigue las restricciones de su reproductor y plataforma.

## Proxy de audio

`/api/proxy` mantiene soporte para `Range`, `Content-Range` y `Accept-Ranges`. Esto permite que navegadores móviles puedan iniciar, pausar y buscar dentro de streams que necesitan pasar por el servidor.

El proxy solo acepta HTTPS y una lista de hosts de audio conocidos. No debe convertirse en un proxy abierto.

## Producción

Sirve siempre mediante HTTPS. HTTPS es especialmente importante para PWA, Media Session y políticas de reproducción del navegador.

Comprueba:

```text
GET /health
```

Debe devolver `{"status":"ok", ...}`.

## Estructura

```text
app.py
index.html
manifest.webmanifest
sw.js
icon.svg
requirements.txt
Dockerfile
README.md
```


### YouTube dentro de OSTO

Las pistas encontradas en YouTube se muestran y reproducen dentro del reproductor de la propia web mediante el embed oficial de YouTube. OSTO no descarga ni extrae el audio de YouTube. El comportamiento de reproducción en segundo plano sigue las reglas del navegador, sistema operativo y YouTube.
