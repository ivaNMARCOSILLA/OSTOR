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

Cada sticker tiene una frase original positiva que se pronuncia al pulsarlo. Las mil frases base son diferentes. Se conservan los sonidos breves originales como alternativa para dispositivos sin síntesis de voz. No hay reproducción automática. Los diseños personalizados también reciben una frase.

## Música gratuita y Ol Live

La música y la biblioteca son gratuitas. Todo Ol Live se ofrece con tres meses de prueba y, después, 25 € en un único pago voluntario, sin vencimiento mientras el servicio siga operativo. No hay renovaciones. Las invitaciones de administración siguen siendo un acceso especial independiente. Los regalos siguen siendo externos, sin comisión de Ol.

## Los 100 fundadores

Hay 100 plazas numeradas que requieren actividad: un primer directo verificado de 30 minutos durante la prueba y luego 120 minutos por ventana de 30 días. Al final de la prueba se debe confirmar el pago único de 25 € para conservar la plaza, además de las condiciones de actividad. Las plazas tienen una comprobación visual antiautomatismos; el número se conserva en el historial. Solo n.º 1 se marca para una posible cesión futura; la venta no está habilitada y los demás números no son transferibles. El panel permite revisar el progreso y ampliar plazos por incidencias.

La insignia se personaliza con una letra, frase, canción gratuita o sonido sin alterar el número oficial. Las normas de buen trato y seguridad se mantienen. Revocar invalida las sesiones; la música permanece gratuita.

## Estadísticas y personas en línea

El panel muestra clientes registrados, altas de los últimos siete días, periodos pagados vigentes, amigos, fundadores, canales, emisiones, pagos confirmados e importes total y del mes UTC. Una tabla resume siete días por fecha UTC. Los importes son los pagos registrados por administración, no beneficios, facturación auditada ni saldo consultado en PayPal. Los grupos de acceso pueden coincidir. El resumen se actualiza al abrir el panel, cada minuto mientras está visible y al pulsar Actualizar estadísticas. Solo administración recibe estos datos.

El contador público distingue cuentas conectadas y visitantes sin cuenta. Comprueba presencia cada 30 segundos en páginas visibles o con audio/vídeo activo y usa una ventana de 90 segundos. Deduplica una cuenta entre pestañas y dispositivos; un visitante se estima por navegador mediante una cookie técnica firmada de un día. No se guardan IP, ubicación ni historial de navegación en la tabla de presencia. Los registros vencidos se eliminan al recibir otra presencia. No es un recuento exacto de seres humanos y no filtra todos los robots. Un error de conexión se muestra como pendiente, sin inventar ceros.

## Ol del bueno · actualización comercial

Sustituye los planes de 1, 6 y 8 euros: una prueba de tres meses y después 25 € en un único pago voluntario. Los pagos e historiales anteriores se conservan. El servidor rechaza nuevas operaciones de los planes retirados, pagos antes de los últimos siete días de la prueba con plaza reservada, referencias repetidas y un segundo pago de por vida. La prueba solo puede iniciarse una vez y no comienza con el vídeo desactivado. Revocar invalida las sesiones y el acceso nuevo; no reinicia la prueba.

Las plazas de fundador son condicionales: primer directo continuo de 30 minutos y luego 120 minutos en los últimos 30 días, tras el periodo inicial de tres meses. Se consulta ListParticipants de LiveKit para verificar pistas de cámara o pantalla publicadas por la identidad del creador; no se confía únicamente en el indicador del navegador. Solo se acreditan intervalos de hasta 75 segundos entre verificaciones. La falta de actividad desactiva derechos especiales para revisión; si vence la prueba sin pago se libera el número y se conserva un historial privado. La venta de plazas no está habilitada. Solo n.º 1 es elegible para una opción futura, sin valor económico prometido.

La comprobación visual contra automatismos caduca en cinco minutos, está vinculada a la sesión y solo sirve una vez. Limita reservas automatizadas; no garantiza identidad única ni elimina todos los bots. Usuarios con dificultades de lectura necesitan ayuda de administración. Para protección adicional especializada puede integrarse un proveedor de retos con sus credenciales.

Los stickers pronuncian frases positivas mediante la voz española del dispositivo; no utilizan el micrófono ni una voz clonada. La disponibilidad depende del navegador; se muestra el texto y se conserva un sonido alternativo cuando no hay síntesis de voz. No hay reproducción automática. El tamaño de formulario es de al menos 16 px para evitar el zoom automático de iPhone; el zoom manual sigue permitido.

## Reserva durante la prueba y liberación por falta de pago

Iniciar una nueva prueba reserva atómicamente el menor número libre entre 1 y 100, después de la comprobación visual. Si están ocupados los cien, no se consume la prueba. Una reserva previa a la activación real de vídeo no consume días; su periodo comienza al estar disponible Ol Live.

Para conservar el número se deben confirmar 25 € antes del vencimiento. Se permite el pago voluntario durante los últimos siete días para confirmar la operación mediante el gestor; no se producen cargos automáticos. Si vence sin confirmación, la siguiente comprobación del sistema libera la plaza antes de asignar o contabilizar reservas. No hace falta que el antiguo usuario vuelva a entrar. El número, fechas y diseño anterior se archivan en un historial privado de 25 registros por página.

El antiguo titular pierde la insignia y no puede iniciar otra prueba ni recuperar automáticamente el número. Puede pagar 25 € para continuar en Ol Live y, si queda una plaza libre, solicitar otra con el acceso pagado. La misma plaza nunca tiene dos titulares actuales: pagos, vencimientos y asignaciones utilizan la misma transacción serializada. Un pago confirmado a tiempo conserva el número tras la prueba. La posible cesión futura de la plaza n.º 1 sigue sin estar habilitada.

## Suscripciones a cada creador

Son opcionales e independientes del acceso de 25 € a Ol Live y de los regalos. El creador propone importe en euros, periodo (mes manual o pago único), beneficios y su PayPal de cobro. Cada versión requiere tres aprobaciones expresas, desde cuentas distintas: creador, administración y moderador de acuerdos Gref. Cambiar importe, periodo, beneficios o PayPal requiere una nueva versión; no se reutilizan las aprobaciones y no cambian las condiciones de recibos anteriores.

Administración puede designar la cuenta `gref` desde Cuenta → Suscripciones de creadores. La cuenta tiene que existir; si está pendiente de activar, se muestra así y no puede aprobar nada hasta aceptar su invitación privada. No se afirma que una persona externa haya aceptado ni se envían invitaciones por correo automáticamente. El moderador solo revisa acuerdos, no obtiene administración ni puede confirmar pagos ajenos. Si el creador también es administrador, otra cuenta de administración debe representar esa parte del acuerdo.

Los tres beneficios posibles son insignia de suscriptor, chat para suscriptores y directos reservados. Los contadores reflejan suscripciones activas reales. El creador decide cuándo activar el modo de chat o directo exclusivo, siempre que ese beneficio forme parte del acuerdo aprobado. Los mensajes publicados en chat exclusivo conservan su audiencia privada aunque el canal vuelva a abrir el chat a todos. Los tokens de vídeo verifican el acceso; las comprobaciones de emisión del creador revalidan espectadores en salas exclusivas y retiran accesos vencidos. Si la comprobación no puede proteger la sala, no se sigue acreditando la emisión como válida.

Los pagos van al PayPal del creador sin comisión de Ol ni renovación automática. No se permite cobrar mientras el vídeo y las ventas no estén habilitados. El creador comprueba el ingreso, marca la verificación e introduce usuario, importe y referencia única desde su panel. Solo entonces se activan los beneficios. El importe debe coincidir con la versión aprobada y no se admite repetir una referencia; abrir el enlace o enviar un regalo no concede suscripción. Ol no verifica automáticamente las cuentas PayPal de terceros ni custodia esos fondos. El creador dispone de registros privados paginados de 25 elementos e importes confirmados, que no son beneficios netos ni saldo consultado en PayPal.

## Verificación opcional de dos factores

Cuenta → Seguridad → Verificación de dos factores permite preparar una clave TOTP tras comprobar la contraseña actual. Se añade manualmente a una app autenticadora y se confirma un código de seis cifras antes de activar. La preparación caduca en diez minutos. No se activa por defecto ni desde administración para otra persona. La activación cierra las demás sesiones y entrega ocho códigos de recuperación de un solo uso; se muestran una vez, no se guardan en almacenamiento del navegador y el usuario debe conservarlos de forma privada.

Después, iniciar sesión requiere contraseña y un código nuevo de la app o un código de recuperación. No se aceptan códigos TOTP ya utilizados y los intentos están limitados. Desactivar requiere contraseña y un segundo factor válido, e invalida las otras sesiones. No hay SMS ni costes de proveedor de códigos.

El secreto del autenticador se deriva mediante HMAC con separación de dominio, el identificador de cuenta y un nonce aleatorio; la base guarda el nonce y una huella del secreto de servidor, no la clave manual. Los códigos de recuperación se guardan como resúmenes HMAC. Es imprescindible conservar el mismo MAGGY_SESSION_SECRET al migrar: la herramienta rechaza migraciones con 2FA activa si la huella no coincide. No rotar ese secreto sin planificar la migración de credenciales y sesiones. Los códigos y claves no deben copiarse a Git, registros, correos ni al chat.


### Permisos de Gref
Designar la cuenta no concede permisos. Desde «Suscripciones de creadores → Permisos del moderador», solo administración puede permitir ver propuestas y, por separado, aprobar precios y beneficios. Aprobar exige poder ver. «Retirar todos los permisos» bloquea la siguiente petición incluso con sesiones abiertas. Sin permiso de aprobación se pausan nuevas suscripciones; los recibos y beneficios adquiridos se conservan. No concede clientes, pagos, estadísticas, suspensiones ni gestión de permisos. Una nueva designación tras revocación requiere autorizar de nuevo.


La versión 9.6 usa Stripe como gestor preparado para cobros nuevos, con activación todavía condicionada a la configuración y prueba real. Los enlaces PayPal del creador quedan para regalos; las confirmaciones manuales conservan soporte de historial únicamente en el modo legado. La plaza se confirma durante los últimos siete días dentro de los tres meses; al vencer la prueba sin pago se libera el número, sin plazo adicional ni precio de reserva. Véase [pagos y Play Store](PAGOS_Y_PLAY_STORE.md). Rubi tiene un control de supervisión de solo lectura separado de Gref, sin activación automática. El aviso de mantenimiento está en el panel de operaciones.

Los apodos opcionales de afición «Lola», «Lolo» y «Loles» se guardan en la cuenta y se muestran junto al usuario en comentarios. No cambian el inicio de sesión ni los permisos. La frase del sticker del creador no se cambia por estos apodos.
