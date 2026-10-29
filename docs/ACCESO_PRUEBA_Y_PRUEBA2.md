# Concesión de acceso completo gratuito

Solicitada por el titular el 29-10-2026 para las cuentas ya registradas `prueba` y `prueba2`.

En el primer arranque de producción de esta versión se buscan esas cuentas existentes, activadas y de rol member. Se registra una concesión por ID de cuenta, con fecha y administrador, y un asiento independiente por cada destinatario. Si falta una cuenta, se registra que no se concedió; una futura inscripción con ese nombre no obtiene acceso por nombre. No se crean cuentas ni contraseñas.

La concesión permite ver, crear y emitir cuando el servicio esté disponible, y utilizar las prestaciones de suscriptor sin cobros. No crea pagos, acuerdos de precio ni suscripciones facturadas; no da permisos administrativos ni de moderación. Mantiene las condiciones de actividad de fundadores y no asigna un número automáticamente.

Clientes y amigos → Dar/Retirar acceso completo gratuito permite gestionarla. La retirada invalida las sesiones y no se deshace por un nuevo despliegue: el asiento de aplicación impide repetir la migración. Los accesos pagados o invitaciones previas son independientes; Retirar acceso gratuito revoca también la concesión completa.

La ejecución real y las banderas de vídeo/cobro deben verificarse en producción. El entorno de trabajo no puede consultar su base de datos remota.

## Prueba privada de vídeo (9.11.2)

Las cuentas con concesión completa pueden entrar al estudio y al catálogo privado durante el próximo estreno. No se cambian las banderas de cobro ni se abre el catálogo a visitantes. Una cuenta publica únicamente en su propio canal y la otra recibe un token de espectador, sin permiso de publicación. LiveKit debe estar realmente configurado; la concesión no inventa una conexión ni elimina ese requisito.

Primer dispositivo: entrar con prueba en /live#creator-panel, guardar canal, aceptar cámara/micrófono y pulsar Iniciar directo. Segundo dispositivo: entrar con prueba2 en /live#live-catalogue y abrir el canal en directo. Usar auriculares para evitar acoplamiento. La prueba entre dispositivos físicos sigue pendiente de realizar por el titular.

## Continuidad del directo (9.11.3)

Los errores temporales de verificación de presencia (25 segundos), listado (30 segundos) o consulta de sesión (60 segundos) ya no cierran por sí solos una conexión WebRTC. Se reintenta sin acreditar actividad hasta que LiveKit confirme el vídeo. Las comprobaciones no se solapan y las respuestas tardías no actúan sobre otra sesión. El espectador revalida su permiso por un endpoint autenticado independiente del listado; una finalización explícita o la pérdida de acceso sí cierra el directo.

Las pruebas de regresión usan reloj de navegador y una sala LiveKit simulada para reproducir errores HTTP, desaparición del listado y revocación. No sustituyen la comprobación física de vídeo/audio entre los dispositivos del titular.
