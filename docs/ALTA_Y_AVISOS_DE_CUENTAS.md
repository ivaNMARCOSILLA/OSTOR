# Alta, ayuda de acceso e informes de cuentas

## Pago único del alta

El alta de las cuentas registradas requiere un pago único de 1 EUR tras cinco
minutos de uso verificado. El plazo se guarda en el servidor; cambiar el reloj,
recargar la página o volver a entrar no lo reinicia. Las cuentas anteriores
comienzan su plazo al volver a acceder con esta política. La confirmación por
correo se completa antes de iniciar los cinco minutos.

La cuota no compra Ol Live ni una insignia. Tampoco se considera pagada por una
aportación voluntaria o un antiguo pago anual. El pago se inicia únicamente tras
aceptar sus condiciones y pulsar el botón de Stripe; no se realizan cargos
automáticos. El webhook firmado o una consulta autenticada al Checkout propio
confirman los 100 céntimos y su vínculo con la cuenta. La URL de regreso no
concede acceso. Una devolución o disputa impide utilizar esa confirmación como
un pago vigente.

Están exentos los administradores, los supervisores con revisión activa y los
moderadores de acuerdos activos, además de la cuenta rosas identificada por el
propietario. La exención de rosas se guarda por su ID estable, para conservarla
al renombrar su cuenta y no trasladarla a otra cuenta que tome ese usuario.
Los permisos de moderador huérfanos o revocados no eximen del alta. Una invitación
o concesión de Ol Live gratuita por sí sola tampoco exime, según la aclaración
del propietario.

El servidor bloquea las APIs de consumo cuando vence el plazo sin pagar. El
perfil, las opciones de seguridad, recuperación, ayuda y pago permanecen
accesibles. El aviso usa el tiempo confirmado por el servidor, conserva los
borradores y no fuerza recargas. Los medios se pausan al confirmar el vencimiento.
«Ya he pagado · comprobar» consulta el pedido existente sin crear otra compra.

`OL_REGISTRATION_FEE_ENABLED=1` activa esta política por defecto. El pago usa la
clave real de Stripe, su webhook y `OL_PAYMENTS_ENABLED=1`, respetando el
mantenimiento de pagos y las restricciones de la distribución Play. No depende
del estreno de Ol Live. Las pruebas antiguas desactivan expresamente la política;
las pruebas dedicadas comprueban los cinco minutos y los pagos con datos aislados.

## Ayuda de acceso

`/account#access-help-panel` ofrece recuperación de contraseña y una solicitud
de ayuda por código de correo, contraseña, segundo factor o pago. La incidencia
llega al destinatario administrativo existente. No se pide ni envía una
contraseña o un código, no se modifica la cuenta y la respuesta no revela si el
usuario indicado existe. Los intentos tienen un límite por IP protegido, con
validación del cuerpo y CSRF. Un fallo de correo deja el aviso pendiente.

## Cuentas existentes y nuevas por correo

El destinatario configurado es `normalesoutro@gmail.com`. Los informes incluyen
usuario, correo y su estado de verificación, nombre y apodo guardados, fecha,
rol, estado del alta y último pago anual cuando exista. Se seleccionan los
campos necesarios; no se cargan contraseñas, hashes, códigos ni tokens para
construir el informe.

La primera visita a la portada o a una ruta pública de estado prepara y envía
el resumen inicial solicitado por el propietario, en lotes de hasta 100 cuentas.
La respuesta pública nunca incluye los datos del informe ni su estado privado. Las nuevas altas generan su propio
aviso. Una cuenta nueva ya encolada no se repite en el resumen inicial. Los
marcadores de envío no dependen del historial de notificaciones del panel y se
conservan aunque ese historial se limpie.

Los envíos utilizan el proveedor SMTP o Resend existente y una cola duradera.
Se envían como máximo dos mensajes por petición, después de cerrar las
transacciones de base de datos. Si no hay proveedor, el informe permanece
pendiente. Solo se marca enviado tras la aceptación del proveedor; su cuerpo
se elimina de la cola después. Un fallo permite reintentar desde
`/account#account-reports-panel`. Como en cualquier entrega de correo con
reintentos, una interrupción posterior a la aceptación puede requerir revisar
el justificante del proveedor.

`OL_ACCOUNT_REPORT_EMAILS=1` activa los avisos automáticos. Las pruebas de correo
capturan los mensajes localmente y no envían datos reales. Las herramientas de
revisión pública no reciben los cuerpos de estos informes.

## Contador público

El contador muestra números completos de entradas registradas y ya no añade
«Al menos». Mantiene 120 fechas por página y conserva el historial. Las fechas
sin información recuperable se identifican sin inventar visitas.
