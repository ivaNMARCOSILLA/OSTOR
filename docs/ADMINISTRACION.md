# Maggy 8.3.0 · Acceso, administrador y pagos

## Tarifas y calendario

La web y el catálogo se pueden explorar sin pagar. Reproducir música y usar favoritos, historial y canales requiere acceso de pago. Registrar una cuenta o aceptar una invitación no desbloquea la reproducción.

- Bienvenida: **1 € por 14 días**, una vez por cuenta, como primer periodo de pago.
- Continuación: **6 € por un mes**. Se añade un mes natural al vencimiento vigente si aún está activo, o a la fecha actual si ya venció. El día se ajusta al último día del mes cuando procede: 31 de enero → 28/29 de febrero.
- Los plazos empiezan cuando el administrador confirma un pago real. Al vencer, el servidor deniega la resolución de audio y las APIs de reproducción; la web y las búsquedas permanecen visibles en modo de vista previa. Una página ya abierta comprueba su sesión cada minuto y al volver a primer plano.
- No hay cargos automáticos: PayPal.me/IMarcosIlla no permite comprobar pagos por sí solo. La confirmación de pagos en esta edición es manual. No se crean periodos al pulsar un enlace ni al enviar parámetros desde el navegador.

Cada operación verificada queda registrada con referencia única, importe, fechas, usuario y administrador. La referencia no se puede reutilizar. El panel permite revisar el calendario de vencimientos por mes y revocar acceso. La bienvenida solo puede utilizarse una vez por cuenta; no se verifica la identidad civil de una persona que cree varias cuentas, pero cada nuevo periodo requiere su propio pago comprobado.

## Instalar en un servidor persistente

Python 3.12, HTTPS y disco persistente. No servir index.html como web estática. No usar SQLite en un sistema de archivos efímero: se perderían cuentas/pagos y sesiones. Para Vercel usa PostgreSQL y un secreto estable, siguiendo docs/VERCEL.md. La modalidad local sigue usando SQLite.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
export MAGGY_DATA_DIR=/ruta/privada/persistente/maggy
.venv/bin/python manage.py create-admin --username admin
.venv/bin/gunicorn --bind 127.0.0.1:8080 --workers 2 --threads 4 --timeout 60 app:app
```

El comando pide una contraseña de al menos 12 caracteres sin mostrarla; no la pases como argumento ni la subas a Git. En producción pon un proxy HTTPS delante de Gunicorn y deja MAGGY_COOKIE_SECURE=1 (valor por defecto). Para pruebas HTTP exclusivamente locales puede usarse MAGGY_COOKIE_SECURE=0.

SQLite y la clave de sesión se guardan en MAGGY_DATA_DIR (por defecto .instance). Conserva ese directorio privado entre reinicios y actualizaciones. Haz copias de seguridad con el servicio parado o con una herramienta que utilice la API de backup de SQLite; protege las copias como los originales. Para varias máquinas servidor hay que migrar a base de datos/almacenamiento compartido; no copiar independientemente SQLite activo entre réplicas.

Dockerfile y compose.yaml ofrecen una alternativa con volumen persistente; no se han construido ni probado en Docker en este entorno. Tras desplegar por ese método: `docker compose exec maggy python manage.py create-admin --username admin`. El puerto del compose se limita a loopback y necesita un proxy HTTPS.

## Cuenta de administrador creada en el entorno actual

Usuario: **admin**. Se creó en /workspace/maggy-state. Su contraseña aleatoria inicial está únicamente en /workspace/maggy-private/admin-initial-password.txt (archivo privado, permisos 600), nunca en el ZIP, GitHub o el chat. Recupera ese archivo solo desde el terminal autorizado del entorno y cambia la contraseña antes de usarla en público:

```bash
cd /workspace/Maggy
MAGGY_DATA_DIR=/workspace/maggy-state /workspace/maggy-venv/bin/python manage.py set-password --username admin
```

El cambio cierra todas las sesiones de esa cuenta. En otra instalación del ZIP, crea tu propio administrador con create-admin: no se distribuye ninguna contraseña predeterminada ni base de datos de usuarios.

## Usar el panel desde diferentes dispositivos

Abre **/account** en el mismo sitio publicado e inicia sesión con admin y tu contraseña. La cuenta de gestión puede abrir varias sesiones a la vez. No necesita un periodo de cliente para gestionar el producto.

Para tus amigos:

1. En el panel, introduce un usuario y pulsa «Crear invitación de cliente».
2. Comparte de forma privada el enlace de invitación. Caduca en 48 horas y solo se usa una vez.
3. El amigo elige su propia contraseña; no obtiene permisos de administrador ni acceso gratuito.
4. Tras recibir y comprobar su pago en PayPal, selecciona su usuario, el plan y la referencia de la operación; confirma que el pago está completado y pulsa «Registrar pago y activar periodo».

Cada cuenta y cada navegador tienen su propio espacio local: no se sincronizan favoritos, canales ni historial entre dispositivos. No se importan automáticamente los antiguos datos locales sin cuenta para evitar asignarlos a una persona equivocada. Los datos del servidor sí mantienen el acceso contratado de esa cuenta en todos sus dispositivos. Usar la misma cuenta desde dos dispositivos no transfiere sus canales.

No hay recuperación de contraseña por correo; el operador puede restablecerla mediante manage.py set-password. No compartas tu contraseña de administración: utiliza las invitaciones de cliente.

## Verificación y límites

22 pruebas unitarias, incluidas caducidad en el instante exacto, primera bienvenida, renovación anticipada, fin de mes, referencia duplicada, invitados sin acceso, aislamiento de roles, CSRF, revocación y sesiones en dos dispositivos. Pruebas de navegador con servidor/DB temporales: `python tests/run_browsers.py` tras instalar requirements-dev.txt y disponer de Chromium.

El control de acceso protege Maggy y sus APIs. No convierte los audios públicos de proveedores externos en contenido privado ni impide que alguien use esos servicios directamente. Las fuentes musicales son Internet Archive y Audius; su disponibilidad depende de los proveedores.

Dominio/DNS, HTTPS público y automatización de pagos con PayPal Business/webhooks no se han desplegado. Los textos legales se han actualizado a las funciones reales pero siguen siendo borradores y requieren datos del titular antes de comercializar.

## Windows PowerShell: instalación y actualización

En la carpeta descomprimida de Maggy:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:MAGGY_DATA_DIR = Join-Path $PWD.Path ".instance"
$env:MAGGY_COOKIE_SECURE = "0"
.\.venv\Scripts\python.exe manage.py create-admin --username admin
.\.venv\Scripts\python.exe app.py
```

Abre http://127.0.0.1:8080/account. Para detener: Ctrl+C. Si ya tienes admin, no repitas create-admin. Para cambiar su contraseña usa manage.py set-password --username admin.

Para actualizar desde una edición anterior, detén el servidor y conserva una copia de seguridad de .instance. Extrae esta edición en una carpeta nueva y copia allí .instance; luego crea su .venv e instala requirements.txt. No copies los antiguos assets ni archivos del programa. Si configuraste MAGGY_DATA_DIR con una ruta absoluta distinta, mantén esa misma ruta en vez de copiar el directorio. Así conservas tus cuentas, pagos y clave de sesión.
