# Borrado del historial de avisos, conservando Flores

El propietario ha aclarado que desea borrar los registros históricos del panel, no silenciar los correos de otras cuentas. Se conserva el historial de notificaciones relacionado con la cuenta `rosas`, conocida como Flores.

La limpieza elimina físicamente los demás registros de `admin_notifications`, incluidos los avisos enviados y los pendientes. Las relaciones con Flores se comprueban mediante identificadores internos y referencias fiables de los eventos anteriores; copiar su apodo o mencionarlo en un texto no hace que se conserve otro aviso. Si no se puede encontrar la cuenta de Flores, no se vacía el historial automáticamente.

Este borrado no elimina las cuentas, pagos, grabaciones ni registros originales de moderación. Los futuros avisos administrativos siguen creándose y enviándose como antes. También se mantienen la confirmación de correo, recuperación de contraseña y confirmación de acceso anual al cliente. No se ha instalado un filtro para silenciar otros usuarios.

La limpieza solicitada se ejecuta una sola vez al arrancar Production. El panel permite repetirla con «Borrar historial excepto Flores». La ejecución requiere que Vercel despliegue y arranque la versión; las pruebas locales no acreditan su ejecución en producción ni eliminan mensajes que ya estén en un buzón externo.
