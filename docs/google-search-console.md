# Google Search Console · electronicama

Añade la propiedad de dominio `electronicama.com` en Google Search Console y verifica el DNS. Si ya está verificada, usa esa propiedad.

En **Sitemaps**, envía esta dirección cuando esté desplegada la versión nueva:

https://electronicama.com/sitemap.xml

El sitemap reúne estas cinco páginas públicas canónicas:

- https://electronicama.com/
- https://electronicama.com/live
- https://electronicama.com/legal/aviso-legal.html
- https://electronicama.com/legal/privacidad.html
- https://electronicama.com/legal/cookies.html

La imagen principal se incluye también en el sitemap, en los datos estructurados y en la portada:

https://electronicama.com/assets/electronicama-social.png

Puedes comprobar el permiso de rastreo en https://electronicama.com/robots.txt.

Usa **Inspección de URLs → Probar URL publicada → Solicitar indexación** para la portada y `/live`. No necesitas enviar cada archivo ni cada ancla de la página. `/streamers` señala `/live` como canónica. La cuenta privada tiene `noindex`; las API y el panel de administración quedan fuera del sitemap.

Google decide la indexación y si muestra una imagen. Enviar el sitemap no garantiza una fotografía ni una fecha de aparición. Esta configuración no presenta una apelación en Google Ads.

El catálogo musical necesita que Google pueda consultar `/api/search`, `/api/locale` y `/api/status` durante la representación de la portada. `robots.txt` permite esas consultas públicas; sus respuestas JSON llevan `X-Robots-Tag: noindex` para que no se indexen como páginas independientes. Las rutas de cuentas y administración permanecen fuera del rastreo.

Después de cambiar estas reglas, vuelve a usar **Probar URL publicada** y revisa los recursos. Un fallo de descarga de JavaScript requiere su mensaje concreto o repetir la prueba; no demuestra por sí solo un fallo del código.
