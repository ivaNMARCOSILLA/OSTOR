# Plan de integración Stripe para Ol

Contexto: https://electronicama.com · música gratuita y transmisiones Ol Live. Revisión local del 26 de octubre de 2026; **no generada por stripe_implementation_planner**. El plugin no se instaló porque no existe `claude`; la configuración MCP del entorno es de solo lectura y el acceso de red a los servidores de Stripe está bloqueado. La alternativa `npx skills add https://docs.stripe.com` también falló al descargar. Verificar las decisiones contra la documentación oficial cuando se pueda conectar.

## Diseño recomendado y revisión del código

| Producto | Aplicación a Ol | Situación y siguiente paso |
| --- | --- | --- |
| Payments + Checkout | Pago único de 25 EUR, voluntario, con plaza confirmable en la última semana dentro de los tres meses de prueba | Preparado con precios del servidor, pedido persistente, firma y antigüedad del webhook, importe/moneda/destinatario verificados, idempotencia y tratamiento de devoluciones/disputas. Falta prueba real de integración de la cuenta. |
| Connect Standard | Cada creador es vendedor de sus suscripciones y recibe cobros directos, sin comisión adicional de Ol | OAuth con estado de un uso; exige verificación bancaria y acuerdo versionado de tres partes. Los secretos OAuth no se guardan. Verificar las condiciones, costes y capacidades del país de cada creador. |
| Billing | Suscripciones de canal con renovación automática, si se decide ofrecerlas | **No activado.** Ahora los periodos mensuales se renuevan manualmente. Antes de automatizar: versionar consentimiento y términos de renovación, aprobarlos entre las tres partes, usar Checkout `mode=subscription`, gestionar `invoice.paid`, impagos, cancelación/portal y eventos fuera de orden. Revisar sus comisiones adicionales; no crear cargos recurrentes unilateralmente. El acceso de Ol de 25 EUR sigue siendo de pago único. |
| Identity | Verificaciones documentales adicionales cuando exista una necesidad concreta | **No activado ni contratado.** La identificación de vendedores ya pasa por Connect. Identity es un producto adicional, puede tener coste y requiere definir finalidad, base jurídica, conservación y acceso. No pedir documentos a todos los aficionados por defecto ni confundir Identity con el reto antirrobots. |
| Radar | Riesgo de pagos, autenticación y señales antifraude | Usar las herramientas y configuración disponibles en el Dashboard de Stripe para Checkout. No se afirma que haya reglas personalizadas ni un plan avanzado contratado. Probar autenticación/3DS, rechazo y reintentos en sandbox. No garantiza eliminar todo fraude. |

## Prueba segura preparada

En Vercel, proyecto `garcia-fills/nohumanitas`, añadir variables privadas `STRIPE_TEST_SECRET_KEY` (`sk_test_…` o una clave restringida `rk_test_…` con permisos suficientes para Checkout) y `STRIPE_TEST_WEBHOOK_SECRET` (`whsec_…`). No confundirlas con la clave publicable `pk_test_…` ni con las variables de producción. El Checkout alojado no necesita la clave publicable en el navegador de Ol. No pegar claves secretas en el chat.

En Stripe, seleccionar el mismo entorno de pruebas de la clave y registrar el destino `https://electronicama.com/api/payments/webhook/test`, con eventos `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `charge.refunded`, `charge.dispute.created`. Guardar su secreto de firma y volver a desplegar Vercel.

Administración → Mantenimiento, gestor y supervisión → Probar Stripe. El botón crea una sesión alojada de prueba de 25 EUR, sin dinero real; solo admite administración. Usar los datos de tarjeta de prueba oficiales, nunca una tarjeta real. Un evento de pruebas no puede activar cuentas, consumir pruebas, reservar plazas, registrar ventas reales ni enviar un correo de ingreso. No se han hecho pagos de prueba en la cuenta del usuario mientras faltan estas variables.

Las sesiones y eventos de sandbox se registran con el tipo `test`, separados de los beneficios y del historial de pagos reales. Los webhooks de producción rechazan eventos de prueba; el endpoint de pruebas rechaza eventos reales. La prueba no sustituye verificar el flujo completo de Connect y cada política de reembolso antes de vender.

## Condiciones antes de producción

Completar identidad y banco del titular; probar vídeo real; comprobar derechos de emisión, precios, comisiones y condiciones vigentes; terminar información fiscal, privacidad y devoluciones; probar confirmaciones y fallos en sandbox. Mantener `OL_PAYMENTS_ENABLED=0` mientras falta lo anterior. Solo después configurar las claves reales y las banderas de venta. Ver también [pagos y Play Store](PAGOS_Y_PLAY_STORE.md): una app de Google Play requiere revisar sus reglas de compras digitales e integrar su facturación cuando corresponda. No publicar Stripe dentro de la app como atajo.

Referencias que deben consultarse al disponer de acceso: [MCP](https://docs.stripe.com/mcp), [Checkout](https://docs.stripe.com/payments/checkout), [webhooks](https://docs.stripe.com/webhooks), [Connect](https://docs.stripe.com/connect), [Billing](https://docs.stripe.com/billing), [Identity](https://docs.stripe.com/identity), [Radar](https://docs.stripe.com/radar).
