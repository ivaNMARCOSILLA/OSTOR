# Concesión de acceso completo gratuito

Solicitada por el titular el 29-10-2026 para las cuentas ya registradas `prueba` y `prueba2`.

En el primer arranque de producción de esta versión se buscan esas cuentas existentes, activadas y de rol member. Se registra una concesión por ID de cuenta, con fecha y administrador, y un asiento independiente por cada destinatario. Si falta una cuenta, se registra que no se concedió; una futura inscripción con ese nombre no obtiene acceso por nombre. No se crean cuentas ni contraseñas.

La concesión permite ver, crear y emitir cuando el servicio esté disponible, y utilizar las prestaciones de suscriptor sin cobros. No crea pagos, acuerdos de precio ni suscripciones facturadas; no da permisos administrativos ni de moderación. Mantiene las condiciones de actividad de fundadores y no asigna un número automáticamente.

Clientes y amigos → Dar/Retirar acceso completo gratuito permite gestionarla. La retirada invalida las sesiones y no se deshace por un nuevo despliegue: el asiento de aplicación impide repetir la migración. Los accesos pagados o invitaciones previas son independientes; Retirar acceso gratuito revoca también la concesión completa.

La ejecución real y las banderas de vídeo/cobro deben verificarse en producción. El entorno de trabajo no puede consultar su base de datos remota.
