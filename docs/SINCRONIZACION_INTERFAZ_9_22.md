# Actualización entre dispositivos · 9.22.0

Las operaciones correctas que cambian canales, emisión, pantalla, acuerdos,
pagos, administración y perfiles publican una revisión compartida en la base
de datos. Las lecturas y operaciones fallidas no cambian esa revisión. Los
comentarios mantienen su propio flujo incremental y no fuerzan recargas globales.

/api/sync devuelve únicamente identificadores opacos de revisión, sin datos
privados y sin caché. Los visitantes solo reciben la revisión pública. El navegador
consulta aproximadamente cada tres segundos, sin peticiones solapadas, con un
límite de tiempo y espera progresiva al fallar. Pausa la consulta en segundo plano
y comprueba cambios al volver a la pestaña o recuperar conexión.

Ol Livis actualiza datos y títulos sin reconstruir la sala de vídeo. La lista de
canales sigue sin reconstruirse cuando su contenido es igual. Cuenta, promoción
de fundadores y mantenimiento reaccionan a sus cambios. El formulario con foco
conserva el borrador durante las actualizaciones; la cuenta aplaza el refresco
mientras se escribe. Se conserva la comprobación periódica de respaldo de Ol Livis.

Pruebas con dos contextos de navegador: una edición del canal en el segundo se
muestra en el primero sin navegación; el texto que se está editando no se pisa.
Pruebas de continuidad de sala, privacidad de revisiones y operaciones fallidas.
No es un canal WebSocket: el cambio puede tardar unos segundos y requiere conexión.
