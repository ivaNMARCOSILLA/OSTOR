# Maggy 8.3.0 · electronicama.com

Web y PWA musical con Internet Archive y Audius. Esta edición elimina las integraciones de YouTube y Jamendo: buscadores, reproductores, enlaces, endpoints y claves. No se realizan solicitudes a esos proveedores. Sus antiguas canciones guardadas se ignoran en favoritos, historial y canales, sin borrar permanentemente el almacenamiento previo.

## Funciones actuales

- Audio HTML5, anterior/siguiente, controles de reproducción y Media Session cuando el navegador lo admite.
- Favoritos, historial, canales y ambientes locales separados por cuenta y navegador. No hay sincronización entre dispositivos.
- Vista previa pública, reproducción de pago: 1 € por 14 días una sola vez por cuenta y 6 € por un mes. El administrador confirma los pagos manualmente y el servidor aplica los vencimientos automáticamente.
- Administrador multidispositivo, invitaciones de cliente, historial de pagos y calendario. [Instalación y administración](ADMINISTRACION.md).
- PWA para navegadores compatibles de Android, iPhone/iPad y escritorio. En iOS: Safari → Compartir → Añadir a pantalla de inicio. Necesita HTTPS y conexión para verificar la cuenta; no permite música offline. No se generan APK ni IPA.

## Desarrollo y pruebas

Python 3.12; instalar requirements-dev.txt para ejecutar `python -m unittest discover -s tests -v`. Pruebas de navegador: `python tests/run_browsers.py`, con Chromium disponible. Usan una base de datos temporal y pistas simuladas. 22 pruebas unitarias y pruebas funcionales verifican audio, biblioteca, ausencia de solicitudes a proveedores retirados, cuatro anchos de pantalla, cuentas, pagos e invitaciones.

La disponibilidad real de las búsquedas y audios depende de Archive/Audius y de la red. Las pruebas de reproducción usan un WAV de prueba, no certifican todo su catálogo. Las capturas de docs se generan con datos ficticios.

## Despliegue y límites

Hace falta un servidor con almacenamiento persistente y HTTPS. No servir como web estática ni usar SQLite efímero en Vercel. Esta adaptación admite PostgreSQL persistente: consulta VERCEL.md. Dockerfile y compose.yaml están preparados pero no probados en Docker en este entorno. La publicación en electronicama.com y sus DNS/HTTPS sigue pendiente.

No hay cobro automático ni comprobación automática de PayPal: el administrador debe comprobar el pago en su cuenta antes de registrarlo. Los documentos legales siguen siendo provisionales. Pagar a Maggy no concede derechos adicionales sobre canciones de terceros.

El ZIP excluye contraseñas, bases de datos y sesiones. MAGGY_SHA256.txt permite comprobar su integridad; la identificación editorial no es una firma notarial o certificada.

## Paleta visual 8.3.0

Azul eléctrico y rojo intenso como colores principales, amarillo vivo en botones, viñetas, etiquetas y foco de teclado. Incluye reproductor, formularios, panel de administrador, calendario e iconos PWA. Las opciones antiguas de ambiente conservan sus claves pero ahora muestran variantes de esta misma paleta.

## Vista previa y desbloqueo 8.3

La portada, el catálogo y las búsquedas son públicos. La respuesta pública solo contiene identificador, título, artista, proveedor, miniatura y marca locked; no entrega URLs de audio, enlaces externos ni campos internos del proveedor. Las respuestas se marcan no-store para impedir mezclar resultados públicos y privados en cachés compartidas.

Pulsar reproducir, favoritos, historial, perfil o crear canales sin acceso muestra «Desbloquear Maggy». Las primeras altas ven 1 € por 14 días; las cuentas que ya usaron la bienvenida ven 6 € por un mes. El servidor sigue comprobando cada resolución de audio y proxy. Cada reproducción obtiene un enlace fresco tras verificar la cuenta: no usa las URLs antiguas guardadas en el navegador.

Al vencer o revocar, el reproductor se detiene al comprobar la sesión (cada minuto y al volver a la pestaña), pero el catálogo permanece visible. El modo sin conexión no permite escuchar ni eludir la verificación. Los audios públicos de los proveedores siguen siendo accesibles directamente fuera de Maggy; este control protege el uso de la aplicación, no constituye DRM de esos servicios.
