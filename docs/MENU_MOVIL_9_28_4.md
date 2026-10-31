# Menú móvil · 9.28.4

La navegación de inicio conservaba una regla antigua con fondo blanco que ganaba
al tema oscuro. El botón del logotipo también heredaba el fondo dorado de los
botones generales y la cabecera de altura fija comprimía sus tres controles.

- Menú oscuro completo, incluidos los márgenes y espacios entre grupos.
- Logotipo sobre fondo transparente, texto dorado y sin etiqueta partida.
- Cabecera de altura flexible con espacio para las zonas seguras del dispositivo.
  En pantallas de hasta 600 px, la marca ocupa una fila y los accesos a cuenta e
  idioma comparten la siguiente.
- Opción de idioma «Automático» abreviada para que se pueda leer entera; se
  conserva la selección automática por país o navegador.
- Navegación, cierre con Escape, preferencias de cookies y desplazamiento del
  menú conservados.

La prueba de navegador comprueba fondo y contraste del menú abierto, límites y
solapamientos de los controles, idiomas y ocho anchuras entre 320 y 900 px,
incluida una ventana horizontal. Las comprobaciones se ejecutan en Chromium con
datos temporales; no equivalen a una prueba en un iPhone físico.
