# Ol Live real y paquete 9.7

La web y la PWA comparten vídeo, cuentas y pagos. LiveKit sirve tanto en el navegador como en una aplicación que use Ol. Quitar mantenimiento no activa un cobro ni sustituye conectar los servicios.

## Estado comprobado

- Stripe sandbox: un pago simulado de 25 EUR confirmado mediante webhook firmado. No es un ingreso real.
- Producción: faltan los datos reales de Stripe; los cobros siguen desactivados.
- LiveKit: los datos antiguos guardados en Preview son incorrectos: URL sin formato WebSocket, Key y Secret iguales y secreto demasiado corto. No se han copiado a Production ni se ha afirmado que funcionen.
- «Fondos Web»: etiqueta editorial dentro de acontecimientos de Ol, sin formulario, saldo, cargo ni movimiento económico.
- Paquete: fuente web/PWA con SHA-256 y plantilla Android; no contiene secretos, cuentas ni claves de firma. No es un AAB firmado ni una publicación en tienda.

## Pasar vídeo a Production

En el proyecto correcto de LiveKit, obtener WebSocket URL (`wss://…`), API Key y API Secret de la misma pareja. Guardarlos en Vercel Production, nunca en el chat. El secreto es distinto de la API Key. No se pueden deducir a partir de las claves de Stripe.

Desde una terminal autenticada en la cuenta de Vercel:

```sh
vercel env add LIVEKIT_URL production --scope garcia-fills
vercel env add LIVEKIT_API_KEY production --scope garcia-fills
vercel env add LIVEKIT_API_SECRET production --scope garcia-fills
vercel env add MAGGY_STREAMERS_ENABLED production --scope garcia-fills
```

Cada comando solicita el valor por entrada privada; no poner valores como argumentos ni guardarlos en el repositorio. La bandera de vídeo debe valer `1` cuando estén los datos reales. Mantener `MAGGY_STREAMER_SALES_ENABLED=0` y `OL_PAYMENTS_ENABLED=0` mientras se prueba la emisión. Si una variable ya existe, actualizarla en el panel o mediante `vercel env update`; no eliminar valores válidos a ciegas.

Redesplegar Production y entrar como administrador en `/live#video-setup`. «Comprobar conexión» hace una petición real a LiveKit, sin publicar cámara ni crear emisiones. Después probar cámara, micrófono, pantalla, salida y visualización desde otro dispositivo. La vista privada no demuestra que otros reciban el vídeo. Comprobar permisos y recepción en un iPhone real antes de dar por terminado su funcionamiento móvil.

## Pasar pagos a real

Verificar identidad y banco en Stripe, política comercial y costes aplicables. Guardar en Production `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_CLIENT_ID` y `STRIPE_CONNECT_WEBHOOK_SECRET`. Los creadores conectan sus cuentas y el destinatario, importe y beneficios deben aprobarlos las tres partes. Las claves de sandbox y sus webhooks no sirven para producción.

Solo cuando el vídeo esté verificado y los servicios reales listos, habilitar `MAGGY_STREAMER_SALES_ENABLED=1` y `OL_PAYMENTS_ENABLED=1`. El pago único sigue siendo 25 EUR; tres meses de prueba y confirmación voluntaria durante los últimos siete días dentro de la prueba. No se han activado nuevas cuotas automáticas ni comprado planes adicionales.

Administración → Mantenimiento, gestor y supervisión muestra cada variable pendiente sin enseñar valores. Es un informe de configuración, no una certificación de emisiones reales. El mantenimiento puede afectar solo pagos o solo vídeo y dejar la música disponible.

## Empaquetar

```sh
python tools/build_release.py
python tools/verify_release.py ../artifacts/OL_9_7_1.zip
```

Para instalar la web/PWA no hace falta compilar. Google Play requiere un paquete firmado, cuenta del titular y revisión; véanse `android/twa-manifest.template.json` y `docs/PAGOS_Y_PLAY_STORE.md`. Las políticas de compras digitales deben resolverse antes de publicar ventas en la app.
