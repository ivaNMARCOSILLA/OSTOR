# Administración de Ol

En electronicama.com/account entra con tu cuenta de administración.

- **Invitar amigo sin pagar** crea una cuenta individual con acceso gratuito a Ol Live para ver directos, sin vencimiento hasta su retirada. El enlace privado caduca a las 48 horas; este plazo no es la duración del acceso. Una invitación pendiente puede regenerarse escribiendo otra vez su usuario. Una cuenta ya activada recibe el acceso con **Dar acceso gratuito**.
- Los registros anteriores de invitaciones de amigos recuperan ese acceso al actualizar, salvo cuentas revocadas. No se inventan pagos ni se conceden permisos de administración o creador de Ol Live.
- Clientes: buscador, contadores y páginas de 25 cuentas. Los historiales y el calendario están plegados. Las invitaciones y la moderación se consultan en páginas de 25 registros.
- Borrar historial usado/caducado conserva cuentas, accesos y pagos. Cancelar una invitación pendiente invalida el enlace. Retirar acceso gratuito conserva periodos pagados. Revocar acceso cierra las sesiones.

## Correo a normalesoutro@gmail.com

Los eventos de registro, aceptación de invitación, pagos comprobados y avisos/denuncias de moderación generan notificaciones persistentes. El correo usa resúmenes sin contraseñas, enlaces de invitación, referencias bancarias ni conversaciones completas. El panel distingue pendientes, fallidos y enviados al proveedor; este último estado no garantiza que el destinatario lo haya leído o que haya llegado a su bandeja principal.

En Vercel → nohumanitas → Settings → Environment Variables, configura como secretos de servidor:

- `OL_EMAIL_FROM`: remitente autorizado (por ejemplo, tu propia cuenta de correo).
- SMTP: `SMTP_HOST`, `SMTP_PORT` (465 TLS o 587 STARTTLS), `SMTP_USER`, `SMTP_PASSWORD`. Gmail requiere una contraseña de aplicación con verificación en dos pasos, no la contraseña de acceso normal.
- Alternativa: `RESEND_API_KEY` más un remitente validado por Resend en `OL_EMAIL_FROM`.

Selecciona Production y vuelve a desplegar. No publiques las credenciales en el chat, Git ni JavaScript. Sin credenciales los avisos siguen en el panel y pendientes de correo. **Reintentar** procesa hasta 3 pendientes por pulsación. No hay programador externo contratado; un envío fallido requiere reintento desde el panel.

## Moderación

Se filtran textos públicos y comentarios mediante reglas de insultos graves, amenazas, referencias sexuales sobre menores y ofertas ilegales. El filtro no interpreta perfectamente el contexto ni detecta todas las formas de evasión. Los comentarios bloqueados no aparecen en el chat; administración puede revisar contexto y denuncias.

La voz se transcribe en español mediante SpeechRecognition del navegador durante una conexión real de emisión. Solo se envían resultados finales; los fragmentos se guardan de forma privada durante 30 días. No se guarda el audio. El navegador puede usar su servicio de reconocimiento y su micrófono predeterminado. La interfaz indica si está activo, detenido, no disponible o si falla. Silenciar el micrófono y salir del directo detiene el reconocimiento. No es una transcripción garantizada de todo el audio ni de la pantalla compartida. Un cliente modificado puede eludir este mecanismo: la supervisión de voz independiente del cliente requeriría un servicio en el servidor.

Las detecciones producen avisos de posible suspensión, nunca una sanción automática basada en un reconocimiento que puede fallar. Tres avisos en 24 horas o un caso grave quedan señalados para revisión. Las denuncias son privadas. Administración puede revocar la cuenta tras revisar el caso. Los registros con más de 30 días se eliminan al utilizar comentarios o revisión.

La emisión pública sigue necesitando la configuración de LiveKit; no se activan ventas de Ol Live durante estas pruebas.

## Colección Ol

Cada cuenta gratuita registrada dispone de una colección base de 1000 stickers y recibe 10 puntos por minuto de uso activo. El sticker número 1 es el retrato del creador y es gratuito al entrar. Los once hitos anteriores conservan sus tiempos de desbloqueo; los otros disfraces se incorporan en pasos de tres minutos activos. Los stickers son reutilizables en comentarios y se validan en el servidor.

Una presencia cada 30 segundos mantiene el contador. La web envía presencias mientras se usa una página visible (interacción en los últimos 5 minutos) o hay reproducción activa. La cuenta comparte un único reloj entre pestañas y dispositivos; no se acreditan intervalos sin comprobación de más de 90 segundos ni tiempo sin conexión. Un navegador en segundo plano puede limitar las comprobaciones. No es una verificación de atención humana: un cliente modificado puede simular presencia, aunque no ganar tiempo más deprisa que el reloj del servidor. Los puntos no son dinero ni se compran; el álbum no incluye sorteos.

### Subir diseños propios

En Administración → **Diseños de stickers**, elige crear uno nuevo o sustituir el diseño de uno existente. Indica nombre y puntos y sube PNG, JPG o WebP. La web prepara una imagen de 256 píxeles y el servidor vuelve a validarla y guardarla como WebP en PostgreSQL, de forma persistente entre despliegues. No se admiten SVG ni imágenes animadas subidas por usuarios. El catálogo admite hasta 1000 diseños personalizados.

Los diseños existentes conservan su umbral para no bloquear de nuevo una colección ya conseguida. El retrato del creador está fijado como número 1 a cero puntos. Los stickers siguen siendo reutilizables y sin pagos adicionales.

### Álbum de 1000 y láminas

La colección base reúne el retrato del creador y 999 emojis disfrazados seleccionados de 11 láminas originales generadas para Ol: espacio, fantasía, profesiones, aventuras, música, deporte, animales, estaciones, fiesta, sabores y leyendas. Los símbolos antiguos se sustituyen por disfraces conservando sus identificadores y puntos; ningún tiempo ganado se reinicia.

El álbum, el selector del chat y el gestor muestran 24 resultados por página. Admiten búsqueda por nombre, número y temática. El chat solo permite enviar stickers desbloqueados y el servidor vuelve a comprobarlo. El gestor incluye «Ver las 11 láminas» para abrir los mosaicos completos. Los diseños personalizados del administrador se conservan además de la colección base.

Se seleccionaron 999 disfraces completos entre las once láminas, revisando sus cuadrículas. Se guardan recortes transparentes de 160 píxeles y vistas generales WebP; la página no descarga los mil diseños de golpe. Los fuentes PNG no forman parte del despliegue.

Cada sticker tiene un sonido original diferente de menos de un segundo, generado sin muestras musicales ajenas. Solo suena al pulsar su botón o un sticker del chat; no hay reproducción automática. Los diseños personalizados también reciben su propio sonido.

## Música gratuita y Ol Live

La búsqueda, reproducción, favoritos, listas y temporizador musicales son gratuitos. Una cuenta gratuita permite conservar los puntos de la colección. Los pagos se aplican exclusivamente al vídeo de Ol Live: bienvenida 1 € / 14 días, espectador 6 € / mes y creador 8 € / mes. Los cobros permanecen bloqueados hasta que el servicio de vídeo esté preparado. Los regalos se envían al PayPal del creador sin comisión de Ol.

El directorio muestra emisiones reales, con categorías Videojuegos, Música, Entretenimiento y Actualidad. Destacados se gestiona desde administración; no se inventan canales ni espectadores.

## Los 100 fundadores

Las primeras 100 cuentas que reserven expresamente una plaza obtienen acceso de creador sin vencimiento, sin pago ni renovación. El contador se comprueba en el servidor; una reserva simultánea no puede superar las 100 plazas. Cada cuenta conserva un número único e inmutable. Las plazas revocadas permanecen en el historial y no se vuelven a asignar.

El fundador puede adornar su insignia con una letra, una frase positiva, una canción gratuita del buscador o un sonido original. Esto no cambia su número oficial. Las canciones conservan su atribución y disponibilidad de origen; el sonido solo se reproduce por acción del visitante. Las normas de moderación se aplican también a los fundadores. Revocar una cuenta invalida sus sesiones y el acceso de fundador, manteniendo la música gratuita.
