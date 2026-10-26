# Ol Live · próximo estreno (9.8.1)

La web muestra únicamente la idea de negocio: siete días de prueba gratuitos y después 25 EUR en un único pago voluntario. No se ofrecen cobros ni enlaces de pago durante el próximo estreno. Las pruebas todavía no empiezan. La noticia conserva sus hojas verdes decorativas.

Configuración de producción:

```dotenv
OL_PAYMENT_PROVIDER=stripe
OL_LIVE_PREMIERE=1
OL_PAYMENTS_ENABLED=0
```

La preparación de Stripe y su prueba sin dinero real se muestran solo en el panel administrativo. No borrar claves, pedidos históricos ni destinos de webhook: permiten revisar operaciones anteriores y continuar la configuración cuando la cuenta esté verificada.

Para abrir el servicio en el futuro: completar verificación del gestor, comprobar destinos firmados y cuenta conectada, probar vídeo real entre dispositivos y confirmar los requisitos comerciales. Solo entonces se revisan los indicadores de estreno, mantenimiento y habilitación de cobros. No cambiar esos indicadores como sustituto de la verificación.

Se han retirado los formularios de cobros externos y regalos monetarios. Los historiales financieros y los accesos ya concedidos se conservan; las tablas y adaptadores históricos no constituyen métodos disponibles en producción. El antiguo apartado de supervisión está retirado y no concede permisos; las cuentas de usuario no se eliminan por ello.

Los textos permiten saltos de línea naturales y respetan el zoom expreso del navegador. Las comprobaciones de interfaz incluyen anchos de 320, 390, 768 y 1440 píxeles.

La noticia utiliza una ilustración botánica original sin marcas ni personajes. El archivo WebP conserva transparencia y reduce el tamaño de descarga respecto al original generado.
