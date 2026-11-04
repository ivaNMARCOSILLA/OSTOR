# Flores y consultas del contador · 9.29.1

El diseño compartido usa una flor natural de trazo fino, con tallo, hojas y
pétalos dorados junto a los títulos principales. Es una referencia botánica
decorativa, independiente de las cuentas, sin interacción ni animación.

La administración tiene una sección propia «(primitivo)*ovelix · Flores» con la
distinción «Triunfador» y un enlace a su canal. La etiqueta usa una flor geométrica
en dorado y conserva literalmente el apodo solicitado. Se asigna únicamente a la
cuenta `rosas`: aparece en su canal y en sus comentarios dentro de ese canal.
Se conservan el nombre Flores, usuario, insignia, permisos y pagos existentes.
La consulta administrativa es privada y no modifica cuentas.

El contador no tiene un límite de quince visitas. Quince es el número de fechas
por página del historial. El total es un entero BIGINT compartido entre todos los
dispositivos con entradas consentidas. El origen fijo de catorce días y el
historial anónimo permanente se mantienen.

La portada utiliza `compact=1` mientras «Últimas entradas» está cerrado. La
consulta establecida lee cuatro veces las tablas anónimas, sin recuentos de
sesiones, detalles personales ni limpieza. El detalle se solicita al abrirlo.
Las actualizaciones siguen llegando cada tres segundos y conservan la protección
frente a respuestas antiguas. Se añaden índices de fecha en sesiones y última
actividad en dispositivos. La limpieza del detalle sigue ejecutándose en
escrituras, administración y consulta completa.

La herramienta `tools/benchmark_visit_capacity.py` crea únicamente una base
desechable con datos sintéticos. Una ejecución con 150.000 sesiones por día
durante siete días (1.050.000 filas) y cinco mediciones obtuvo medianas locales
de 1,179 ms para la lectura compacta y 35,654 ms para la completa. Es una medida
de consultas SQLite; no demuestra concurrencia ni garantiza la capacidad real
de Vercel o PostgreSQL. No se introducen visitas simuladas en el contador público.

Validación: 351 pruebas de servidor, con 22 pruebas PostgreSQL omitidas por no
disponer de instancia local. Navegadores aislados comprueban contador compartido,
consentimiento, carga del detalle al abrirlo, historial de catorce días e idiomas.
El apodo se comprueba en administración, catálogo, directo y chat a 320, 390 y
1440 píxeles, junto con el cambio de canal y el tratamiento literal del texto.
