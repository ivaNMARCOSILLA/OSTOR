# Maggy · OSTOR / nohumanitas

Maggy para el proyecto Vercel **nohumanitas** del equipo **garcia-fills**, vinculado a **ivaNMARCOSILLA/OSTOR**. Diseño azul y rojo con amarillo; fuentes musicales Internet Archive y Audius.

La web y el catálogo se pueden explorar sin pagar. Escuchar, guardar favoritos y crear canales requiere desbloqueo: **1 € por 14 días de bienvenida**, una vez por cuenta; después **6 € por un mes**. El administrador confirma los pagos PayPal manualmente y el servidor aplica los vencimientos.

- [Vercel y PostgreSQL](docs/VERCEL.md)
- [Administrador, calendario y Windows](docs/ADMINISTRACION.md)
- [Funciones y límites](docs/MAGGY.md)

En Vercel hace falta `DATABASE_URL` persistente y un secreto estable `MAGGY_SESSION_SECRET` (o el `SECRET_KEY` existente, si es fuerte). La aplicación no usa SQLite efímero en funciones. Para Windows/local se conserva SQLite en `.instance`.

`tools/migrate_sqlite.py` permite conservar cuentas y pagos locales al pasar a PostgreSQL, sin sobrescribir una base que ya tenga datos. No se suben `.instance`, contraseñas ni variables de entorno a Git.

Las instrucciones actuales de despliegue están en docs/VERCEL.md. El historial de Git conserva OSTO antes de esta actualización. Los textos legales siguen siendo provisionales.

### Experiencia móvil 8.4

Reproductor vertical ampliable con zonas seguras para iPhone, controles táctiles grandes, saltos de 15 segundos y temporizador de 15/30/60 minutos. Selecciones por actividad: desconectar, entrenar, concentrarse y viajar. Media Session incorpora búsqueda temporal cuando el navegador la admite. AirPlay y controles de pantalla bloqueada dependen de Safari y del dispositivo; no se garantiza reproducción continua en segundo plano. El temporizador se comprueba también al recibir eventos de audio y al volver a la página; iOS puede suspender JavaScript en segundo plano.

### Reproducción y búsqueda 8.4.1

El elemento de audio reutilizable inicia `/api/play/<id>` en el propio gesto del usuario. Esta ruta comprueba el acceso vigente y redirige al proveedor, conservando la descarga parcial y los controles nativos; no espera a `/api/account/me` y `/api/resolve` antes de sonar. Si falla, intenta una conexión alternativa una vez.

La búsqueda consulta las dos fuentes en paralelo y muestra cada respuesta al llegar. Archive se filtra por formatos compatibles y elementos públicos, sin descargar metadatos por cada resultado; el archivo seleccionado se resuelve y guarda en caché al reproducir. Prioriza MP3 y excluye archivos privados/elementos restringidos. Audius usa su API oficial, excluye pistas marcadas no disponibles o con acceso restringido y dispone de un segundo proveedor. Esto reduce esperas, pero no garantiza disponibilidad de contenido externo ni reproducción instantánea.
