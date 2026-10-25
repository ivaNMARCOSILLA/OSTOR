# Maggy en Vercel · nohumanitas / OSTOR

Destino confirmado por la API de Vercel: equipo **garcia-fills**, proyecto **nohumanitas**, GitHub **ivaNMARCOSILLA/OSTOR**, rama de producción **main**, directorio raíz `.`. Dominios asociados: electronicama.com, www.electronicama.com y nohumanitas.vercel.app.

## Almacenamiento y sesiones

En Vercel las cuentas y los pagos usan PostgreSQL. No se guarda SQLite en `/tmp` ni se generan claves de sesión nuevas en cada función. La aplicación falla de forma explícita si falta la configuración obligatoria, en vez de simular persistencia con archivos efímeros.

Variables privadas en Vercel:

- `DATABASE_URL`: conexión PostgreSQL del proveedor, para Production y Preview. No poner el valor en Git ni en el chat.
- `MAGGY_SESSION_SECRET`: secreto aleatorio estable de al menos 32 caracteres. Si ya existe un `SECRET_KEY` fuerte, se reutiliza como alternativa sin cambiarlo.
- `AUDIUS_APP_NAME`: opcional; no se requieren claves de YouTube/Jamendo, que están retirados.

`VERCEL=1` lo establece la plataforma. Las cookies Secure se fuerzan allí. Las conexiones PostgreSQL remotas verifican TLS e identidad del servidor mediante las CA de certifi; `MAGGY_DATABASE_CA` permite usar un archivo CA oficial del proveedor si fuese necesario. Solo las pruebas en loopback permiten conexión sin TLS.

Las tablas viven en el esquema PostgreSQL `maggy`, separado de `public`. Los pagos, las invitaciones y la limitación de intentos usan transacciones; las operaciones concurrentes de bienvenida e invitación no pueden conceder dos accesos. Se admite el pool de conexión de Neon/Vercel.

## Despliegue

1. Conectar PostgreSQL desde Storage/Marketplace de nohumanitas. No contratar un plan de pago sin autorización del titular. Configurar variables privadas de Production y Preview.
2. Mantener `SECRET_KEY` si ya es fuerte o añadir `MAGGY_SESSION_SECRET` antes de desplegar.
3. Si hay cuentas locales que conservar, migrarlas antes de abrir el nuevo sitio. Si la base es nueva, crear el administrador antes de publicar la aplicación.
4. Desplegar una vista previa y comprobar `/health`, `/`, `/account`, catálogo sin URLs de audio para visitantes y denegación de `/api/resolve/*` sin pago.
5. Tras las comprobaciones, desplegar/promover a producción. `vercel.json` dirige las rutas a la función WSGI de `api/index.py`; `.python-version` fija Python 3.12.

El constructor oficial @vercel/python 28.0.2 se ha ejecutado localmente y genera una Lambda Python 3.12. Eso verifica el empaquetado, no acredita por sí solo un despliegue público.

## Conservar cuentas de Windows (.instance)

La base local no se sube automáticamente a Vercel. El migrador lee SQLite en modo de solo lectura y copia cuentas, hashes de contraseña, pagos, fechas e invitaciones en una sola transacción. Exige un destino completamente vacío; no mezcla ni sobrescribe datos existentes.

Desde la carpeta del nuevo código, con el servidor local detenido y una copia de seguridad de `.instance`:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools\migrate_sqlite.py --source "C:\ruta\Maggy\.instance\members.sqlite3"
```

Se pedirá la conexión PostgreSQL sin mostrarla si no está en `DATABASE_URL`. Escríbela solo en tu terminal autorizado; no la compartas en el chat. Los usuarios mantienen sus contraseñas y periodos, pero deben iniciar sesión de nuevo en el dominio publicado. El migrador no modifica el SQLite original.

Si prefieres una instalación nueva, configura `DATABASE_URL` en tu terminal de forma privada y ejecuta `python manage.py create-admin --username admin`; la contraseña se pide sin mostrarla. No hay contraseña predeterminada incluida en el repositorio. Los administradores ya existentes no se sobrescriben durante despliegues.

## Pruebas

- Suite predeterminada: `python -m unittest discover -s tests -v` (las pruebas PostgreSQL se omiten si no se indica una base de prueba).
- Navegador con SQLite temporal: `python tests/run_browsers.py`.
- PostgreSQL real: `tests/test_postgres_integration.py`, con `DATABASE_URL` y `MAGGY_TEST_POSTGRES_URL` apuntando a una base dedicada `maggy_test` de loopback y un secreto de sesión temporal. La suite se niega a borrar datos de un destino remoto.

Se han validado pagos y vencimientos, referencias duplicadas, operaciones simultáneas, sesión entre instancias independientes, revocación y migración SQLite→PostgreSQL que conserva contraseñas/pagos y rechaza sobrescrituras.

El catálogo sigue siendo público y la reproducción requiere desbloqueo de 1 € por 14 días o 6 € por un mes. PayPal se confirma manualmente desde administración. El soporte PostgreSQL no activa cobros automáticos ni cambia tarifas.

## Activación privada del primer administrador

En esta publicación nueva, la cuenta `admin` se prepara sin contraseña predeterminada. El enlace privado para elegirla se guarda únicamente en la variable cifrada `MAGGY_ADMIN_INVITE_URL` de Production, dentro de los ajustes de nohumanitas. Solo los operadores autorizados del proyecto deben consultar ese valor. Caduca en 48 horas y se usa una sola vez. El enlace no se publica en GitHub ni se entrega en la respuesta pública de ninguna API.

Abre los ajustes de variables en https://vercel.com/garcia-fills/nohumanitas/settings/environment-variables, consulta ese valor privado y ábrelo después de publicar el dominio. Elige tu contraseña y el panel reconocerá la cuenta como administrador. No compartas el enlace ni tu contraseña con clientes; utiliza las invitaciones del panel.

La base de datos de tu ordenador Windows no se importa automáticamente a esta instalación. Si necesitas conservar cuentas/pagos locales, consulta el procedimiento de migración: solo permite un destino vacío y no sobrescribe cuentas que ya existan.
