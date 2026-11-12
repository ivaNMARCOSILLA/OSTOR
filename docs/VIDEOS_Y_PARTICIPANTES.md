# Vídeos y seguimiento de participantes

La zona pública está en `/videos`. El formulario tiene acceso directo en
`/videos#video-upload`, en el menú principal, en la barra móvil y en la portada.
Cualquier cuenta gratuita puede subir sus creaciones; el acceso anual de Ol Live
no es un requisito para compartir vídeos.

## Publicación y cuarentena

Los archivos se envían directamente al almacenamiento privado, por partes.
Flask y Vercel solo reciben los datos del formulario y las peticiones de control.
La finalización comprueba las partes existentes, sus tamaños, el tamaño total y
la cabecera del archivo. Se admiten MP4, MOV y WebM. Esta comprobación identifica
el formato; no constituye un antivirus ni una revisión automática del contenido.

El vídeo terminado queda en cuarentena. Solo administración puede abrir su
vista privada y aprobarlo tras confirmar que lo ha revisado. El tiempo de espera
no provoca su publicación. Una denuncia crea un aviso para administración y no
permite a otra cuenta retirar automáticamente un vídeo ajeno. Administración
puede rechazarlo o devolver un vídeo publicado a cuarentena.

La revisión está en `/videos#video-admin`, también enlazada desde el panel de
administrador. Las decisiones conservan su responsable, fecha y motivo. Las
cuentas normales no pueden consultar esa cola ni los archivos pendientes de
otras personas.

Los enlaces de reproducción caducan a los 60 segundos. Al retirar un vídeo se
dejan de emitir enlaces nuevos; una transferencia ya iniciada puede continuar.
Si el navegador necesita otro rango después de la caducidad, el reproductor
ofrece volver a cargar el vídeo conservando su posición cuando sea posible.

No hay cuota comercial por número de publicaciones ni restricción de temática
dentro de las normas. El límite técnico de cada archivo procede del proveedor
y, opcionalmente, de `VIDEO_MAX_BYTES`. Las subidas se dividen en hasta 10.000
partes. Los controles contra abuso limitan los inicios repetidos en un minuto.

## Activar las subidas reales

1. Crea o selecciona un depósito R2 **privado**, con su URL pública desactivada.
   Se recomienda un depósito específico para los vídeos de la comunidad.
2. Configura como secretos del servidor `VIDEO_R2_ENDPOINT`, `VIDEO_R2_BUCKET`,
   `VIDEO_R2_ACCESS_KEY_ID` y `VIDEO_R2_SECRET_ACCESS_KEY`. Un valor específico
   sustituye al correspondiente `R2_*`; no compartas claves en el navegador.
3. Aplica una política CORS para el origen exacto de la web. El ejemplo está en
   `docs/videos-r2-cors.json`; adapta los dominios si usas otro despliegue.
4. Mantén la eliminación de grabaciones de 30 días limitada a `directos/`.
   Los vídeos publicados usan `videos/` y no deben heredar esa caducidad.
   Configura el aborto de subidas multipart incompletas con un plazo adecuado
   para tus archivos grandes, por ejemplo siete días. Esto permite limpiar
   cargas interrumpidas cuyo identificador remoto no pudiera recuperarse.
5. Después de verificar el depósito privado, establece
   `VIDEO_STORAGE_PRIVATE_CONFIRMED=1` y `OL_VIDEOS_ENABLED=1`.
6. Prueba una subida pequeña, su cuarentena, la revisión y su reproducción desde
   otra cuenta antes de anunciar el servicio. La presencia de configuración no
   verifica por sí sola las credenciales, la política CORS ni el servicio real.

Si falta configuración, el formulario indica que las subidas se están
preparando. No se simula una subida ni una aprobación. Si falla la eliminación
del archivo, la fila queda pendiente de limpieza y permite reintentarla.

## Seguimiento individual

Administración dispone de `/account#participant-tracking`. La ficha reúne datos
que ya conserva la aplicación: alta y estado de cuenta, acceso a Ol Live,
insignia permanente, actividad verificada disponible, canales, vídeos, pagos y
cambios de cuenta. Un dato de actividad ausente se muestra como no disponible,
no como prueba de que la persona nunca haya entrado.

El seguimiento es privado y de consulta. No registra nuevas IP, pulsaciones,
contenido de formularios ni historial de navegación individual. Los datos
opcionales de visitas mantienen su consentimiento y su conservación existentes.
La identidad estable de la cuenta conserva la relación cuando cambia su usuario.

Las cuentas con vídeos o historial de moderación no se borran físicamente desde
la eliminación simplificada de cuentas sin pagos; se conserva la revisión y se
permite su archivo. Los vídeos de autores archivados dejan de aparecer y no
reciben enlaces públicos nuevos.

## Entrada por correo y auditoría

Cada nuevo inicio de sesión exige por defecto la contraseña, el segundo factor
existente si la cuenta lo tiene y un código enviado a su correo. También se
verifica el correo al crear una cuenta o aceptar una invitación. Una cuenta
antigua sin correo puede vincular el primero después de acreditar su contraseña
y confirmar ese código; el correo que ya esté vinculado no se sustituye por el
que alguien escriba en el acceso.

El código caduca en diez minutos, admite cinco intentos y sirve una única vez
en el navegador que lo solicitó. Reenviarlo tiene un intervalo mínimo de un
minuto. Si el envío no está disponible, el acceso no se concede por otra vía.
Los cambios de versión de sesión o del correo invalidan las solicitudes
pendientes. Las sesiones ya autenticadas conservan su vigencia normal.

Configura `OL_EMAIL_FROM` y el proveedor existente: `RESEND_API_KEY`, o
`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` y, si procede, `SMTP_PORT`. Conserva
`OL_LOGIN_EMAIL_REQUIRED=1` y `OL_LOGIN_AUDIT_EMAILS=1` en producción. Las
pruebas antiguas utilizan explícitamente el modo de compatibilidad; la prueba
de seguridad ejecuta el flujo completo de correo con mensajes capturados.

El panel `/account#login-security-audit` reúne intentos, verificaciones,
recuperaciones y resultados durante 90 días. No muestra contraseñas, códigos,
enlaces de acceso ni IP completas. Las direcciones se ocultan parcialmente y
la correlación técnica de red utiliza un código protegido que cambia cada día.
La ficha del participante incorpora sus eventos de acceso conocidos sin
confundir un intento fallido con actividad realizada por esa persona.

Los avisos se dirigen al destinatario administrativo ya configurado en el
servicio de notificaciones. Se agrupan para evitar una avalancha de mensajes;
el acceso confirmado fuerza el envío del resumen pendiente. Un fallo de correo
administrativo queda registrado y permite reintentar el envío desde el panel.
No se afirma que un aviso se haya entregado si el proveedor lo ha rechazado.
La tabla operativa de bloqueo de envío se reinicia en una migración; no es
historial de acceso ni debe bloquear la copia de los registros.
