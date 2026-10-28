# Fondo de Ol y audio mientras se usan otras aplicaciones

Mi espacio → Fondo de Ol ofrece el PNG original de las hojas verdes para guardarlo y seleccionarlo desde los ajustes de Android, iOS/iPadOS, Windows, macOS o Linux. El fondo es una imagen: no ejecuta Ol, no reproduce vídeos y no cambia ajustes sin intervención del usuario. Los menús y formatos admitidos dependen de cada sistema. El PNG original se conserva sin retoques.

El audio usa el elemento HTML audio y Media Session cuando el navegador lo admite. Se publican título, artista, portada y acciones de reproducir, pausar, detener, anterior, siguiente y desplazamiento. Cada navegador y sistema decide qué controles muestra. En particular, no se añade una estrella a las notificaciones del sistema: la estrella de favoritos y el botón de inicio pertenecen al reproductor de Ol.

Minimizar audio reduce los controles dentro de Ol sin crear un nuevo elemento de audio ni interrumpirlo. Inicio vuelve a la portada sin navegar a otro documento. La preferencia compacta se guarda por usuario en el navegador. Los accesos de icono declarados en el manifiesto son Inicio, Favoritos y Fondo, donde el navegador los admita.

Cambiar de aplicación o pestaña no pausa deliberadamente el audio nativo. Es necesario mantener Ol abierto y conectado. La suspensión del navegador, las restricciones de energía y la gestión del sistema pueden interrumpir la reproducción; la web no garantiza continuidad después de cerrar la aplicación ni implementa un servicio nativo permanente.

YouTube mantiene visible su reproductor oficial y se pausa al ocultar la página. El modo compacto no se aplica a vídeos. Al avanzar en una lista de audio desde segundo plano se omiten los vídeos; pueden seleccionarse al volver a Ol. Al cerrar la reproducción se retiran las acciones y los metadatos multimedia anteriores.

Un fondo interactivo que ejecute Ol detrás de otras aplicaciones requiere integraciones específicas por sistema; no lo proporciona una PWA ni este fondo descargable. No se afirma disponibilidad de un fondo animado, un overlay universal ni una aplicación nativa publicada.

Las pruebas locales verifican el PNG real, el modo compacto, la estrella y el inicio sin cortar audio, las acciones Media Session simuladas, visibilidad, cambio entre audio y vídeo y cuatro anchuras. No sustituyen probar las notificaciones y la suspensión en dispositivos físicos.
