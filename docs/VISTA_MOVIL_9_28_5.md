# Vista móvil · 9.28.5

La presentación para pantallas de hasta 800 px tiene navegación propia, con las
mismas cuentas, datos, permisos y destinos de la vista de ordenador.

- Barra inferior común en inicio, cuenta, Ol Livis y páginas legales: Inicio,
  Música, Ol Livis, Hologramas y Mi cuenta. El acceso actual queda señalado.
- Cabecera de inicio compacta con menú y acceso a la búsqueda. El idioma pasa al
  menú móvil, que se abre sobre el contenido y permite desplazarse sin empujarlo.
- Música en filas verticales con carátula, títulos completos, fuente y favoritos.
  Los filtros de fuente se recorren horizontalmente.
- El reproductor se sitúa sobre la barra inferior. Al ver un directo o entrar en
  pantalla completa la barra se oculta para dejar libre el vídeo y el chat.
- En ordenador se conservan la barra lateral y la distribución amplia.

Los enlaces son los mismos de la web. Cambiar el tamaño de pantalla recoloca el
selector de idioma sin duplicarlo ni perder su preferencia. No se crean cuentas
paralelas ni se modifican los pagos o permisos.

Verificación: navegación móvil con datos temporales en Chromium, cinco tamaños
entre 320 y 800 px, orientación horizontal, menú, idioma, búsqueda, reproductor,
destinos reales y preservación del escritorio. Se mantienen las pruebas de menú
en ocho anchuras y las comprobaciones de contraste y directos. No se ha verificado
en Safari de un iPhone físico desde este entorno.

Revisión 9.28.6: el acceso activo también se sincroniza al usar los enlaces del
menú o la búsqueda. Las etiquetas se comprueban a 320 px en los siete idiomas
disponibles, reservando espacio para sus nombres completos.
