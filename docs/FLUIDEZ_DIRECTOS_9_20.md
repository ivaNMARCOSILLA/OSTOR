# Fluidez, chat incremental y directo móvil · 9.20.0

El chat devuelve un cursor compuesto por fecha e identificador. Las siguientes
consultas piden solo mensajes posteriores. La respuesta tiene como máximo 100
mensajes recientes y avisa cuando descarta el historial intermedio por volumen.
No se promete mostrar todos los mensajes cuando llegan miles de golpe.

El cliente evita peticiones superpuestas, agrupa la inserción en un fragmento,
limita a 100 filas y 200 identificadores de deduplicación y consulta cada 1–2
segundos, con espera mayor si hay errores o la pestaña está oculta. Tras enviar
se intenta actualizar inmediatamente. No utiliza WebSockets ni garantiza
latencia instantánea. Se mantienen moderación, límites y privacidad de audiencias.

Índices de canal/fecha e identidad/fecha facilitan las consultas. Los registros
antiguos se purgan como máximo una vez por hora al escribir, no en cada lectura.
El catálogo de stickers solo se carga si hay stickers y las insignias de suscriptor
se consultan para los autores de la página, no todos los suscriptores del canal.

En móvil el vídeo ocupa el viewport; los comentarios se superponen y pueden
ocultarse. El emisor empieza con los comentarios ocultos. Las herramientas
secundarias están tras Controles, conservando salida/finalización y micrófono.
Pantalla compartida grande y cámara pequeña sin recortar la pantalla. El modo
cámara prioritario sigue disponible en el selector del creador.

La lista de canales no se reconstruye si sus datos/filtros no han cambiado.
No se actualiza el catálogo en una pestaña oculta de un espectador. Las luces
LED se pausan fuera de vista y con la pestaña oculta; el vídeo no se pausa.

Validación: historial de 3.000 mensajes, deltas sin duplicados, respuesta acotada,
privacidad y moderación. Suite general de 251 pruebas con 19 de PostgreSQL
omitidas; dos expectativas antiguas de acceso al chat exclusivo se actualizaron
y las 20 pruebas relacionadas pasaron. Navegador: seis tamaños, cámara/pantalla,
menú móvil, continuidad del espectador gratuito, transcripción, contraste y música.
No se ha realizado una carga distribuida real de miles de usuarios concurrentes.
