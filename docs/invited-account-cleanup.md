# Limpieza de cuentas creadas por invitaciones de amigos

La petición del titular se aplica una sola vez en producción a los identificadores
existentes antes del 12 de noviembre de 2026 a las 19:56:52 UTC. Incluye invitaciones
aceptadas y pendientes. Se conserva el resultado en `owner_access_migrations`.

La procedencia debe estar registrada como `owner_invitation`. Para cuentas antiguas
sin esa procedencia se requieren tanto el registro de invitación como la concesión
de amigo anterior a la petición. Una concesión gratuita aislada no basta: los
registros normales y las cuentas antiguas sin pruebas suficientes se conservan.

Se conservan administradores, personal con permisos vigentes, la identidad de
Flores/@rosas, las cuentas bloqueadas y el permiso de vídeos dado por comandos a
AdminSiempre. Las demás cuentas de invitados se eliminan con el procedimiento
habitual que protege pagos, vídeos, incidencias e historial de otras personas.
Si hay historial protegido, se da de baja la cuenta y se retira de las listas
activas, conservando esos registros. También se limpia su invitación del panel.

La selección y los resultados se guardan por ID. Los nuevos registros y las
invitaciones posteriores no quedan sujetos a esta limpieza. La desconexión de
antiguas salas se solicita después de confirmar los cambios de base de datos.
