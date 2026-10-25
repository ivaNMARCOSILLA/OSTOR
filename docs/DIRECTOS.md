# Directos de Maggy: estado y activación

La zona `/streamers` incorpora emisión con cámara y micrófono dentro de Maggy mediante LiveKit. Los botones para emitir y cobrar el plan Streamer permanecen bloqueados hasta conectar y habilitar el vídeo. El SDK 2.23.0 se sirve localmente y conserva su licencia Apache 2.0 en `assets/vendor/LIVEKIT-LICENSE.txt`.

## Precios y regalos

- Bienvenida de Maggy normal: 1 EUR por 14 días, una vez por cuenta.
- Maggy normal: 6 EUR por un mes.
- Maggy Streamer: 8 EUR por un mes, con funciones de Maggy y permiso de emisión. El pago manual se comprueba desde administración. No hay renovación automática.
- Regalos: enlace PayPal.me configurado por cada creador. Comisión de Maggy: **0 %**. PayPal puede aplicar sus propias tarifas. No se cobra a través del enlace de suscripción de Maggy.

Un regalo solo prepara un enlace externo. La web no declara que se haya pagado, no guarda un saldo, no custodia dinero ni inventa estadísticas de ingresos. El usuario comprueba el destinatario en PayPal. No se necesita el sistema de reparto de comisiones de PayPal Commerce Platform para este modelo de enlaces directos.

El mes Streamer empieza al confirmar ese pago, incluso si quedaba tiempo del plan normal. Renovar Streamer antes de vencer añade un mes a su propio vencimiento. El acceso normal no se acorta. Pagar 6 EUR no da permiso de emitir. Revocar acceso elimina el permiso Streamer y cierra las sesiones de la cuenta.

## Conectar vídeo real

Hace falta un proyecto de vídeo LiveKit propio. Este cambio no crea ni contrata servicios externos. Consulta [LiveKit Cloud](https://cloud.livekit.io/) y sus [precios y límites vigentes](https://livekit.io/pricing) antes de elegir un plan: la cuota de Maggy y la factura del alojamiento de vídeo son independientes.

1. Crear o seleccionar un proyecto LiveKit. No contratar planes de pago sin autorización del titular de Maggy.
2. Configurar en las variables **privadas de Preview** del proyecto Vercel `garcia-fills/nohumanitas`:
   - `LIVEKIT_URL`: URL de conexión `wss://...` del proyecto.
   - `LIVEKIT_API_KEY`: identificador de API del proyecto.
   - `LIVEKIT_API_SECRET`: secreto del proyecto, de al menos 32 caracteres.
   - `MAGGY_STREAMERS_ENABLED=1`: habilitación explícita en esa vista previa.
3. Volver a desplegar la vista previa. Nunca pegar secretos en chats, repositorios o documentos.
4. Con la cuenta administradora (exenta de pagar), guardar el canal y probar cámara/micrófono. Mirar el directo desde otro navegador o dispositivo; comprobar sonido, permisos del espectador y fin de emisión. No registrar pagos ficticios en producción.
5. Solo después de una prueba real satisfactoria, configurar las mismas variables en Production y publicar el código. Se habilitará entonces el enlace de suscripción Streamer de 8 EUR en PayPal. Sin activación explícita, el servidor rechaza confirmar ese plan.

La aplicación no solicita grabación ni almacenamiento de las emisiones. La lista de directos usa un aviso del emisor cada 25 segundos; una desconexión deja de aparecer al caducar el aviso, como máximo 75 segundos después. La cuenta necesita acceso vigente para obtener credenciales de sala; solo el propietario con permiso Streamer recibe permiso de publicar cámara y micrófono. Las credenciales duran cinco minutos y no contienen el secreto de API.

## Comprobar cambios

`python -m unittest discover -s tests -p 'test_*.py'` prueba importes, permisos de publicación, firmas de credenciales, regalos sin comisión, validación de destinos PayPal, vencimientos y revocación. `python tests/run_browsers.py test_streamers_browser.py` prueba interfaz y bloqueo cuando no hay vídeo conectado. La emisión WebRTC real necesita el proyecto externo; no se declara comprobada con una simulación.
