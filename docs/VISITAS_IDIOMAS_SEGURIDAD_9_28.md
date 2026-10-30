# Visitas, idioma y seguridad 9.28

## Pantalla principal

La portada presenta entradas reales compartidas con permiso: hora de Madrid redondeada al minuto, tipo aproximado de dispositivo y sección general. Se muestran hasta 20 entradas recientes y los totales de sesiones y navegadores estimados en las últimas 24 horas. No se publica usuario, IP, código de red o identificadores persistentes. Los rechazos no fabrican visitas ni impiden usar la web.

El perfil profesional conserva el detalle de las visitas consentidas durante 7 días, con filtros y paginación: navegador estimado, sesión, cuenta si se ha iniciado sesión, tipo de dispositivo/sistema/navegador, fechas y páginas generales. Los códigos de navegador son aleatorios protegidos y los códigos de conexión usan HMAC diario. No se guarda una IP completa ni huella del dispositivo. Una conexión compartida o VPN no prueba que dos accesos sean de personas distintas. Se ignoran encabezados genéricos de IP reenviada; solo el encabezado propio de Vercel se usa en ese alojamiento. Retirar permiso borra el registro del navegador; también se respetan GPC y DNT.

## Idioma

Preferencia manual guardada, seguida del país fiable del alojamiento y después idioma del navegador. Soporta es, ca, en, fr, pt, de e it; si no hay coincidencia utiliza castellano. El selector permite cambiar o volver a automático. No hay petición externa de geolocalización. Se traducen etiquetas principales de interfaz y consentimiento; los textos de usuarios, nombres y documentación legal original se preservan. No es una traducción completa de cada mensaje dinámico o documento legal.

## Correcciones de seguridad

Retiradas las fuentes de Google, las preconexiones externas de arranque y la carga automática del script de estadísticas Vercel. Las métricas propias opcionales requieren permiso. La CSP restringe scripts a código del sitio y API oficiales de YouTube, permite el JSON-LD estático mediante hash y la compilación WebAssembly de los controles locales; no permite scripts arbitrarios en línea ni eval genérico. Restringe formularios, objetos activos, base de URLs y marcos. Las conexiones multimedia solicitadas por el usuario se mantienen para música y LiveKit.

No se encontraron formularios propios que capturen tarjetas, código de malware ni un CMS con complementos en los archivos revisados. Esto no es un análisis forense exhaustivo de producción ni una consulta actual de todas las bases de vulnerabilidades. Una advertencia externa depende de la revisión del servicio que la emitió; no se afirma que desaparezca al cambiar el código. Las pruebas de vídeo anteriores usan señalización simulada y no certifican siete dispositivos físicos.

El contador de actividad también requiere permiso explícito y respeta GPC/DNT. Retirar permiso elimina su cookie y presencia actuales. El monitor público programado comprueba ahora la cabecera CSP y avisa si vuelven a aparecer cargas automáticas de Google Fonts o Vercel Insights. Los diagnósticos del admin incluyen los nuevos módulos y las protecciones de scripts.

## Validación

299 pruebas de servidor ejecutadas: 279 correctas y 20 omitidas por requerir PostgreSQL. Las 20 pruebas de PostgreSQL se ejecutaron aparte con éxito; incluyen registro consentido, ausencia de identidad en el registro público y borrado en cascada. Pruebas de Chromium correctas para registro público/privado, consentimiento y retirada, países/selector de idioma, bloqueo efectivo de scripts en línea y ajenos, controles musicales, YouTube, Hologramas y siete fuentes de vídeo sintéticas. La CSP permaneció activa en las pruebas: el auxiliar de espera usa evaluación del depurador en lugar de eval de la página, sin desactivar su política.
