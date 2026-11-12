# Permiso específico para subir vídeos

La instrucción del titular para AdminSiempre se aplica una sola vez en producción.
Se utiliza el identificador guardado en su promoción anterior cuando existe; el
respaldo por nombre solo admite la cuenta existente antes de la instrucción. El
resultado queda guardado incluso si la cuenta falta, para no conceder el permiso
a otra persona que registre ese nombre más adelante.

`video_upload_grants` conserva el permiso por identificador, sin vencimiento. No
modifica roles, planes, moderación ni permisos de otras zonas. Permite preparar,
completar y cancelar subidas propias y consultar su estado aunque venza el margen
del alta. El servidor sigue comprobando sesión, CSRF, propiedad y almacenamiento.
Las cuentas bloqueadas o dadas de baja no pueden utilizarlo.

Los vídeos siguen en cuarentena hasta la revisión habitual. El permiso no activa
un almacenamiento sin configurar ni publica automáticamente el contenido.
