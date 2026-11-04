# Contador compartido y recorrido diario · 9.29.0

La portada usa un único total de la base de datos para móvil, tableta y ordenador.
Cada dispositivo puede aportar su sesión consentida aunque comparta cuenta o IP
con otro. Las actualizaciones de una sesión en curso no crean entradas nuevas.

La pantalla consulta el total cada tres segundos mientras permanece visible.
Las actualizaciones que llegan durante otra consulta quedan pendientes; una
respuesta antigua no sustituye al total confirmado de una entrada más reciente.
Las consultas tienen un límite de espera y se recuperan al volver a la página,
recuperar el foco o restablecer la conexión. No se suma ninguna cifra local.

El origen del recorrido se fija catorce días de calendario de Madrid antes de
activar esta actualización. Si el contador ya tenía un origen anterior, se
mantiene. Al ampliar un origen más reciente, solo se añaden las entradas reales
conservadas de los días anteriores a aquel origen, evitando contarlas dos veces.
El origen queda fijo; el total y el historial diario siguen acumulándose sin
reinicio semanal ni borrado de los días antiguos.

El detalle personal continúa conservándose siete días y respeta la retirada del
consentimiento, GPC y No rastrear. Las tablas permanentes contienen únicamente
sumas anónimas por fecha. Los días antiguos sin registros recuperables aparecen
como «Sin datos disponibles» y los recuentos parciales como «Al menos». Un total
anterior sin fecha recuperable se conserva sin inventar su distribución diaria.

La consulta devuelve quince fechas por página; los controles permiten recorrer
los periodos anteriores. La paginación limita el tamaño de las actualizaciones
aunque el historial siga creciendo. Las estructuras nuevas se incluyen en la
migración SQLite/PostgreSQL y en las comprobaciones de mantenimiento.

Validación local: la suite de servidor pasó 342 pruebas con 22 pruebas de
PostgreSQL omitidas por no disponer de una instancia de pruebas. Se comprobaron
en navegador tres dispositivos independientes, recuperación de consultas
bloqueadas, consentimiento y retirada, historial y paginación a 320, 390 y
1440 píxeles. La revisión de navegación encontró 237 enlaces internos sin errores.
Estas comprobaciones usan datos aislados; no certifican el despliegue público.
