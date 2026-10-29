# electronicama · Directos y suscripciones 9.12

## Continuidad y estudio

La presencia de la emisión se verifica cada 25 segundos; su fallo temporal no cierra WebRTC ni acredita actividad no comprobada. El listado se refresca cada 30 segundos y no decide por sí solo si termina una sala. El espectador tiene una comprobación autenticada de acceso que distingue la caducidad del listado de la finalización explícita. La consulta de sesión cada minuto conserva el último acceso verificado ante fallos transitorios; las respuestas de denegación siguen retirándolo. Las solicitudes periódicas no se solapan y las respuestas de otra conexión se ignoran.

El estudio sigue los pasos canal → preparación → emisión. Los ajustes de suscripciones están plegados. Los controles de sonido, cámara, micrófono, pantalla completa y compartir pantalla están dentro del reproductor; ampliar incluye su barra de controles. Solo el emisor puede cambiar o detener su pantalla y guardar la vista de la emisión. El espectador recibe esa vista en la siguiente comprobación de acceso.

La calidad automática consulta las capacidades y muestra la resolución real de la cámara; se mantiene selección manual. La calidad enviada depende también del navegador y del ancho de banda, sin prometer eliminar esas limitaciones. Las pistas se adjuntan una sola vez; la monitorización local queda silenciada. Compartir todo el escritorio requiere elegir Pantalla completa en el selector del sistema. Se solicita esa superficie, sin saltar los permisos.

## Precios y meses

Los nuevos precios de canal están limitados a 300–400 céntimos por mes natural. El creador puede cambiar el precio de forma automática cuando conserva los beneficios ya aprobados. Cambiar los beneficios o el destinatario conserva las revisiones de creador, administración y Gref; no se inventan aprobaciones. Sin destinatario o moderador se guarda un borrador, no se publica una tarifa cobrable.

La oferta y Checkout calculan el menor precio entre la tarifa vigente y los importes previamente confirmados del mismo suscriptor no revocados. Un cambio no modifica ningún registro ni vencimiento ya adquirido. Un pedido abierto conserva el importe almacenado. El mes se calcula en la zona IANA que envía el navegador al abrir el pago, se guarda con el pedido y se transforma a UTC para persistirlo. El mes corto se ajusta al último día; los cambios estacionales conservan la hora local cuando es posible. La interfaz muestra el vencimiento en la zona local. Las renovaciones siguen siendo manuales, sin cargos adicionales automáticos.

Antes del pago de canal se exige la comprobación humana de un solo uso, ligada a la sesión, además de CSRF y límites de intentos. Una respuesta errónea consume el código; la interfaz pide uno nuevo. Las propuestas y la emisión de tokens de sala tienen límites propios. Son controles contra automatización, no una garantía de eliminar todos los bots.

## Fundadores y veracidad

Las 100 insignias numeradas limitan los beneficios de fundador; no bloquean nuevas altas ni el acceso anual ordinario. Después de las 100, la contratación sigue disponible sin ventajas de fundador.

No se añaden perfiles, suscriptores o contadores ficticios. El catálogo proviene de canales existentes y la actividad real se muestra en administración. La presencia pública solo devuelve confirmación de registro, sin cifras de actividad para visitantes.

## Verificación

207 pruebas de servidor superadas, 18 de PostgreSQL omitidas por no disponer de esa instancia. Pruebas de navegador superadas para los temporizadores 25/30/60 con sala simulada, salida explícita/revocación, captura local, controles dentro del reproductor, acuerdos de suscripción y estadísticas privadas. La simulación solo pertenece a las pruebas y no genera perfiles públicos. Las emisiones físicas entre dispositivos, el audio y los ajustes externos de Stripe/LiveKit deben comprobarse en producción; el entorno de trabajo no puede acceder a esas APIs remotas.
