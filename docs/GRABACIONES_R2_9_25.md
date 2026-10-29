# Preparación de R2 y denuncias · 9.25.0

No hay depósito ni credenciales conectados por esta sesión. No se ha grabado
ningún vídeo real ni enviado correo real desde las pruebas. La integración está
desactivada por defecto hasta completar estos pasos en las cuentas del titular.

1. Abrir https://dash.cloudflare.com/?to=/:account/r2 y crear un depósito privado,
   por ejemplo electronicama-directos. No activar acceso público ni dominio r2.dev.
2. En el depósito, crear una regla de ciclo de vida que elimine los objetos del
   prefijo directos/ después de 30 días. Esta regla es la garantía de borrado físico
   independiente de que la web esté encendida. Verificarla antes de declararla lista.
3. Crear credenciales de R2 limitadas a ese depósito, con permisos de escritura,
   lectura y borrado. Guardarlas en Vercel, nunca en el chat, repositorio ni frontend:
   R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
   R2_BUCKET=nombre-real-del-deposito
   R2_ACCESS_KEY_ID y R2_SECRET_ACCESS_KEY.
4. Confirmar que el proyecto LiveKit admite Egress y revisar su facturación.
   La grabación y almacenamiento pueden generar costes del proveedor.
5. Solo después: OL_RECORDING_RETENTION_CONFIRMED=1 y OL_RECORDINGS_ENABLED=1,
   redeploy. Antes de abrir públicamente, comprobar un directo y un MP4 real.

Administración: https://electronicama.com/account#live-recordings-admin

El servidor pide grabación compuesta a LiveKit cuando verifica al emisor. Un
estado STARTING no se presenta como ACTIVE; el directo no se publica hasta que
el servicio confirma actividad. Los errores de grabación requerida detienen la
publicación. Los tiempos de espera inciertos no provocan arranques duplicados.
El creador debe aceptar el aviso y los participantes deben ser informados.

Al terminar se solicita StopEgress. Administración puede comprobar el estado,
abrir archivos completados mediante un enlace firmado de hasta 120 segundos
y borrar archivos caducados. Tras caducar, la aplicación ya no emite enlaces.
Los errores de servicio y estados inciertos requieren revisión en LiveKit; no se
consideran grabaciones completadas. El borrado físico automático requiere la
regla del depósito indicada arriba, no depende de una visita al panel.

Las denuncias de directo o comentario guardan motivo, canal, fecha, identidades
de cuenta de denunciante/denunciado y copia del comentario señalado. Pueden incluir
los correos de contacto verificados, solo para administración. Se relacionan los
identificadores de grabación disponibles. La notificación se dirige exclusivamente
al correo de administración configurado (normalesoutro@gmail.com); no a las partes.
Si falla el correo, la denuncia queda guardada y la notificación se puede reintentar
 desde el panel. Contraseñas, claves y fechas de nacimiento no se incluyen.
Una denuncia o grabación no prueba por sí sola que exista una infracción legal.

Validación final: 262 pruebas generales (243 SQLite y 19 de PostgreSQL separadas),
más comprobaciones de navegador de denuncias, mantenimiento, control adulto,
reproductor y comentarios. Las llamadas a correo, R2 y Egress se simulan en las
pruebas. El seguimiento de 30 minutos corresponde al reproductor y sincronización
locales; no a una grabación real en R2.
