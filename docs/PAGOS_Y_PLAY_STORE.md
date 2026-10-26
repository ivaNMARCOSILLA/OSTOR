# Gestor común de Ol y distribución Android

Implementación preparada el 26 de octubre de 2026. No se han abierto cuentas comerciales, cobrado pruebas, añadido tarjetas ni publicado una aplicación. Las tarifas vigentes no se pudieron verificar: el acceso a las páginas oficiales fue rechazado por la política de red del entorno. Compararlas antes de contratar.

## Decisión técnica preparada

Stripe Checkout con Connect Standard: Ol cobra su acceso de 25 EUR y cada creador conecta su propia cuenta para cobrar directamente sus suscripciones. No hay comisión de Ol para el creador ni custodia de regalos. El procesador descuenta sus comisiones del importe cobrado: eso reduce ingresos, no equivale a financiar costes con beneficios netos ni garantiza que Ol no tenga otros costes. Las obligaciones fiscales son de cada vendedor.

Se mantiene la mensualidad de canal como periodo con renovación **manual**, según el acuerdo entre creador, administración y Gref. No se suscribe a nadie a cargos recurrentes por defecto. Esto evita introducir Stripe Billing y sus costes adicionales sin otra decisión. Los beneficios y el destinatario se versionan y requieren las tres aprobaciones; Rubi solo puede consultar si administración se lo permite.

Comparar precios oficiales según país y tipo de tarjeta: [Stripe España](https://stripe.com/es/pricing), [Connect](https://stripe.com/es/connect/pricing), [Mollie](https://www.mollie.com/es/pricing), [PayPal empresas](https://www.paypal.com/es/business/paypal-business-fees). No se afirma que una opción sea la más barata en todos los mercados.

## Activación real

1. El titular verifica en Stripe su actividad, identidad, país, cuenta bancaria y condiciones; configura Connect Standard/OAuth. Cada creador acepta y verifica su propia cuenta mediante el enlace alojado por Stripe.
2. Guardar en Vercel Production: `STRIPE_SECRET_KEY`, `STRIPE_CONNECT_CLIENT_ID`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_WEBHOOK_SECRET`; nunca enviarlos en chat ni guardarlos en Git.
3. Registrar OAuth redirect exacto: `https://electronicama.com/api/payments/connect-return`.
4. Registrar webhooks separados de plataforma y cuentas conectadas: `/api/payments/webhook/platform` y `/api/payments/webhook/connect`. Eventos: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `charge.refunded`, `charge.dispute.created`.
5. Comprobar primero con claves de prueba en un entorno de pruebas separado (el cobro público no admite eventos de prueba). Probar firma, reintentos, rechazo de importes, cuentas de destino y devolución. Las pruebas automatizadas locales cubren esos contratos con respuestas simuladas; no sustituyen una prueba de integración de la cuenta real.
6. Tras verificar vídeo real, cuenta real, avisos legales, impuestos y política de devoluciones, configurar `OL_PAYMENT_PROVIDER=stripe`, `OL_PAYMENTS_ENABLED=1` y las banderas existentes de Ol Live. No activar cobros antes.

Los datos bancarios se introducen en Stripe, no en Ol. Un retorno del navegador nunca activa beneficios: solo un webhook firmado y coincidente con el pedido. Se aceptan tarjetas en esta primera versión. Firmas con tolerancia de cinco minutos; eventos y pedidos idempotentes; reembolsos totales y disputas suspenden el acceso relacionado, con historial conservado. Una disputa revertida requiere revisar el caso; no hay restauración automática inventada. Las devoluciones parciales no se tratan como devolución total. Los pedidos ambiguos quedan pendientes hasta caducar para evitar que una repetición cobre dos veces.

## Plaza y pago

La prueba sigue siendo de tres meses calendario, desde el vídeo disponible. Se puede pagar voluntariamente durante la última semana. Los **siete días para confirmar los mismos 25 EUR son la última semana dentro de esos tres meses**; no son un periodo adicional. Al terminar la prueba sin pago se libera el número. Una operación completada después de la liberación habilita acceso, pero no recupera un número ya reasignado. No se ha creado un cargo de reserva adicional.

## Android y Play Store

La PWA se instala desde el navegador sin que el usuario compile nada. Publicar en Google Play sí requiere un Android App Bundle firmado, una cuenta de Play Console y revisión de Google. La plantilla `android/twa-manifest.template.json` prepara una Trusted Web Activity; no es un AAB compilado ni una publicación.

En un equipo de publicación con Node, JDK y SDK Android, ejecutar las herramientas oficiales Bubblewrap (`@bubblewrap/cli`), inicializar desde `https://electronicama.com/manifest.webmanifest`, revisar la plantilla, definir la clave de firma y generar el AAB. La clave y sus contraseñas deben permanecer fuera del repositorio. En Google Play, configurar Play App Signing y usar su huella SHA-256 real en `OL_ANDROID_SHA256`; `OL_ANDROID_PACKAGE` por defecto `com.electronicama.ol`. Solo entonces Ol publica `/.well-known/assetlinks.json`; antes responde 404. No se publica una huella ficticia.

El inicio de la variante Play lleva `distribution=googleplay`. Ol deshabilita los checkouts web en esa sesión. Esto es una preparación defensiva, **no una certificación de cumplimiento de las políticas de Google ni una integración con Play Billing**. No publicar compras de funciones digitales con Stripe dentro de la app hasta verificar que existe autorización aplicable o integrar Google Play Billing. No basta ocultar un botón ni cambiar un parámetro para eludir las políticas. Antes de publicar: revisar fichas, privacidad, eliminación de cuenta, seguridad de datos, público objetivo, clasificación de contenido, pruebas exigidas y permisos de cámara/micrófono. Los comentarios y directos requieren moderación y canales de denuncia.

Referencias oficiales: [TWA](https://developer.chrome.com/docs/android/trusted-web-activity/overview), [política de pagos de Google Play](https://support.google.com/googleplay/android-developer/answer/9858738), [Bubblewrap](https://github.com/GoogleChromeLabs/bubblewrap).

## Mantenimiento

Administración → Mantenimiento, gestor y supervisión permite bloquear todo, solo directos o solo pagos con un aviso público de Ol y HTTP 503/Retry-After. El administrador conserva acceso. Los webhooks siguen recibiéndose para no perder confirmaciones. `OL_MAINTENANCE=1` es el cierre de emergencia. Desactivar exige retirar esa variable si está activa. El estado se comparte entre la web y la PWA; no hay una app publicada que sincronizar todavía. Los periodos no se extienden automáticamente por un mantenimiento.
