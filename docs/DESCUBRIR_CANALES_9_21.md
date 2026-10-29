# Buscar canales y más vistos · 9.21.0

El buscador compara título, creador y presentación sin distinguir mayúsculas
ni tildes. Sugiere hasta 12 títulos coincidentes y prioriza coincidencias al
principio del nombre. El orden predeterminado es Más vistos; también permite
Destacados y Consultados en este dispositivo. El catálogo y sus contadores
pueden consultarse sin registro. Ver el vídeo mantiene el acceso existente.

Los recientes son identificadores de canales guardados en el navegador con la
clave de la cuenta actual (o visitante); no se envían al servidor. Se mantienen
como máximo 20 y se borran al eliminar los datos del sitio.

El contador no inventa usuarios: tras conectarse se solicita una comprobación
servidor a servidor de la presencia del espectador en la sala de LiveKit.
Solo entonces se registra una visita por cuenta, canal y día UTC. Se excluye
al propietario; volver a pedirlo no suma. Los agregados se publican sin identidad
de espectadores. Los contadores nuevos comienzan en cero, sin estimar el pasado.
Las suscripciones de canales exclusivos siguen comprobándose antes de contar.
Si la comprobación del vídeo falla, la reproducción no se interrumpe y no se suma.

Pruebas: búsqueda anónima, orden por contador, coincidencias sin tildes,
confirmación de presencia simulada, ausencia de presencia y deduplicación diaria.
Las comprobaciones reales de LiveKit se ejecutarán con las credenciales del
servidor de producción; no se ha fabricado tráfico para generar visitas.
