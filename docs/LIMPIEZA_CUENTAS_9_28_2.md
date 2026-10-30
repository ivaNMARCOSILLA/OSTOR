# Limpieza de cuentas solicitada por el propietario

Se retira la frase personal de Hologramas y se conservan el visor, el crédito del creador y los controles.

El propietario solicita eliminar definitivamente las cuentas existentes `amigo`, `prueba` y `prueba2`. La migración se ejecuta una sola vez en Production al arrancar esta versión, y registra el resultado por nombre. No afecta a cuentas creadas después ni a administradores. Un apodo como `admin` no concede permisos administrativos.

La eliminación comprueba los registros financieros y las dependencias antes de borrar. Una cuenta con pagos, grabaciones, incidencias de moderación o referencias que deban conservarse no se elimina automáticamente; el panel comunica el motivo. No se realizan cargos ni reembolsos ni se envían correos como parte de esta limpieza.

El panel de clientes incorpora una acción para eliminar cuentas sin pagos. También permite dar de baja otras cuentas conservando sus historiales y restaurarlas posteriormente. Las bajas cierran las sesiones, impiden entrar o recuperar el acceso por correo y retiran la cuenta de los listados y estadísticas activos; restaurar exige volver a iniciar sesión. Los administradores permanecen protegidos.

La ejecución en producción requiere que Vercel despliegue y arranque esta versión. El entorno de desarrollo no tiene acceso directo a la base de producción; preparar y enviar la migración no acredita que ya se haya ejecutado en ella.
