# Hologramas

Sección integrada después de la colección y disponible en el menú móvil y de escritorio. Nombre público: Hologramas. Conserva el crédito textual del creador; la frase personal anterior se ha retirado a petición del autor. La foto nueva necesita el archivo original para publicarse; no se sustituye por una recreación.

Adaptación del código aportado a JavaScript modular, sin añadir React ni un paso de compilación a Ol. Las 256 opciones son variantes generativas 3D y una transición final al cuadrado; sus rótulos no presentan las formas como pruebas científicas ni como proyecciones físicas de 180 dimensiones. Incluye globo, malla/sólido, pausa, velocidad, controles por ratón, tacto y teclado.

El visor y Three.js se cargan al abrir la sección. La cámara requiere pulsar Activar cámara; no se solicita micrófono. El seguimiento de la mano usa MediaPipe Hands local y solo se carga al activarlo. Cámara, seguimiento y animación se detienen al cerrar o pasar la página a segundo plano; al volver, la cámara sigue apagada. Se liberan geometrías, materiales, texturas y el contexto gráfico al cerrar. No hay almacenamiento persistente de cámaras, manos ni archivos del usuario.

OBJ y STL se analizan localmente, sin cargar archivos remotos de materiales. Límite 5 MB, hasta 60.000 triángulos y coordenadas finitas. Se comprueban los tamaños declarados de STL antes de asignar sus buffers. Las imágenes PNG/JPG/WebP se abren localmente. Cada archivo temporal se libera o revoca al reemplazarlo; los resultados tardíos no sustituyen una selección nueva.

Three.js 0.170.0, licencia MIT; OBJLoader y STLLoader se adaptan únicamente para importar la copia local del módulo. MediaPipe Hands 0.4.1675469240, licencia Apache 2.0; avisos y licencia conservados en assets/vendor. Los modelos y WASM se sirven como archivos estáticos de Vercel: algunos superan el límite de respuesta de una función. El resto de rutas continúa en Flask. Los paquetes no se descargan en cada visita a la portada.

Pruebas en Chromium con WebGL real por software y cámara simulada: dibujo, 256 controles, modelos locales, seguimiento real con modelo MediaPipe local, cámara sin audio, cierre/reapertura, movimiento reducido, teclado, música simultánea y cuatro anchuras. El reconocimiento de gestos concretos y el rendimiento en dispositivos físicos requieren una prueba con cámara real. No se afirma esa prueba física ni publicación verificada en producción desde este entorno.
