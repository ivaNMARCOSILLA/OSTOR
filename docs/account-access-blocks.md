# Bloqueo de acceso por cuenta

La instrucción del titular del 12 de noviembre de 2026 se aplica una sola vez a
la cuenta existente `loladrones`, en el primer arranque del despliegue de
producción. El resultado y el identificador se conservan en
`owner_access_migrations`. Si la cuenta no existe o fue creada o renombrada
después de la instrucción, se registra el resultado sin bloquear otra cuenta.

El bloqueo retira administración, moderación y accesos concedidos, invalida
sesiones y códigos pendientes y archiva la cuenta. Conserva pagos, titularidad
histórica de fundador y registros. Una sesión identificada de esta cuenta recibe
403 también en las páginas y contenidos públicos; no se convierte en invitado.
Restaurar una baja o borrar la cuenta desde el panel no elimina el bloqueo.

Las conexiones LiveKit requieren expulsión adicional. Una cola persistente
elimina sus identidades de espectador y emisor, cierra su antigua sala propia y
repite los barridos hasta confirmar uno completo después de seis minutos. Cada
GET correcto a `/`, `/health`, `/api/status` o `/api/account/me` procesa como máximo un trabajo,
con ocho llamadas y cuatro segundos de presupuesto. Sin tráfico, credenciales
válidas o confirmación de LiveKit, el trabajo sigue pendiente. No hay llamadas
de red dentro de la transacción del bloqueo ni cambios a las salas ajenas.
Las mismas rutas también procesan la cola cuando responden 403 por este bloqueo,
para expulsar una conexión abierta desde el propio chequeo de la cuenta.

El bloqueo identifica la cuenta, no a una persona anónima. Otro navegador sin
sesión puede consultar lo que la web ofrece públicamente. Los contenidos ya
descargados tampoco pueden retirarse del dispositivo.

Para verificar el despliegue, el operador puede consultar el resultado de la
migración, `account_blocks` y el estado de `account_block_livekit_jobs` desde la
base de datos autorizada. No existe un endpoint público que revele esos datos.
