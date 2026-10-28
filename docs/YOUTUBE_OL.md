# YouTube en Ol

La búsqueda usa YouTube Data API v3 desde el servidor. La reproducción utiliza el iframe oficial visible de YouTube, sin extraer audio, ocultar el vídeo ni eludir bloqueos. Escuchar estas fuentes sigue siendo gratuito; los pagos de Ol Live no cambian.

En Vercel Production, la variable esperada es `YOUTUBE_API_KEY`. La clave debe pertenecer a un proyecto con YouTube Data API v3 habilitada y cuota disponible. Restríngela a esa API. Una clave limitada mediante referentes de navegador no sirve para esta llamada desde el servidor. No añadas el secreto al código del navegador. Los cambios de variables necesitan un nuevo despliegue.

En Administración → Mantenimiento → «Comprobar conexión con YouTube» se realiza una consulta real y se muestra un resultado sin la clave. La comprobación general solo informa de la presencia de la variable. Ni una variable presente ni un test con proveedor simulado garantizan permisos, cuota o reproducción real de todos los vídeos.

El filtro «YOUTUBE · VÍDEO» busca hasta 50 vídeos por página; «Cargar más» permite hasta tres páginas, según los resultados reales. Los filtros de audio conservan su búsqueda habitual. Se cachean las consultas durante diez minutos por instancia, y los límites de frecuencia son de mejor esfuerzo por instancia. La búsqueda de YouTube consume cuota de Google; no se ejecuta en cada visita ni en las revisiones automáticas de mantenimiento.

El reproductor se carga al elegir un vídeo. Los controles incluyen pausa, avance, siguiente, cierre y enlace a YouTube para vídeos retirados, bloqueados o restringidos. No se garantiza reproducción en segundo plano. Ol ya no solicita una pausa al ocultarse la página; los límites reales de YouTube, Safari y el sistema operativo siguen aplicándose. Los controles Media Session solicitan reproducir, pausar y cambiar de pista en el iframe oficial. Al cambiar a audio se destruye el iframe. Las respuestas tardías de una reproducción anterior no sustituyen una pista nueva.

Las pruebas locales de YouTube simulan sus respuestas y su API de iframe; no gastan cuota ni crean datos en producción. La prueba de audio usa WAV locales y verifica el reintento por error y por bloqueo de carga. La caché PWA se actualiza a 9.9.2 para retirar la interfaz anterior.

El reproductor incluye un diagnóstico local de hasta 40 eventos (visibilidad, estado y código de error), descargable por el usuario. No recoge la clave ni se envía al servidor. Las pruebas simulan la visibilidad y la API de YouTube; no verifican continuidad en un iPhone físico.
