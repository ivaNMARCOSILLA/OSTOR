# Apertura de electronicama · Ol Livis

## Preparado en el código

Se recuperan registro público con comprobación humana, inicio de sesión, correo confirmado, recuperación de contraseña, bienvenida y promoción de las 100 plazas. La música permanece como inicio y gratuita. El producto de directos se llama Ol Livis. Se conservan rutas /live, variables OL_*, sesiones y datos para no romper integraciones existentes.

Oferta vigente: 25 EUR por un año desde el pago confirmado, sin prueba gratuita y con renovación manual. Cancelar conserva el acceso hasta la fecha de vencimiento; no hay cargo automático. No se ofrecen devoluciones voluntarias, respetando los reembolsos legalmente exigibles y la corrección de errores de cobro. Las 100 plazas requieren acceso pagado vigente y actividad. Los acuerdos de suscriptores y permisos de Gref siguen administrados por el administrador. No se recuperan PayPal, Rubi ni ofertas de tres meses o siete días.

Roles de comunidad: Activo por defecto. Las colaboraciones como Voluntario o Docente se solicitan por Gmail a Iván; solo administración aprueba o retira el rol en Clientes y amigos. Son etiquetas de comunidad y no conceden privilegios administrativos, moderación ni acceso de pago. El error concreto de credenciales queda pendiente de identificar con el mensaje que aparezca, sin solicitar contraseñas.

## Orden de activación en producción

1. Stripe: completar verificación del titular y banco; no declarar la activación por disponer de una clave. En administración → Preparación de Ol Livis real → Comprobar activación real de Stripe, consultar `charges_enabled`, `payouts_enabled` y requisitos pendientes. Es una consulta privada sin cobros. Una clave restringida puede necesitar permiso de lectura de Accounts.
2. En Vercel Production, revisar `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CONNECT_CLIENT_ID`, `STRIPE_CONNECT_WEBHOOK_SECRET`. No enviar secretos por chat. Las claves reales deben pertenecer a la misma cuenta; el client ID es de Connect, no la clave publicable.
3. Webhooks HTTPS de esta implementación:
   - Cuenta de plataforma: https://electronicama.com/api/payments/webhook/platform
   - Cuentas conectadas: https://electronicama.com/api/payments/webhook/connect
   - Sandbox: https://electronicama.com/api/payments/webhook/test
   Cada destino utiliza su propio secreto `whsec_`. Eventos snapshot: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`, `charge.refunded`, `charge.dispute.created`. Mantener compatibilidad con la versión de API 2024-06-20 que envía este servidor; revisar eventos antes de cambiarla.
4. Connect: completar perfil de plataforma y conexión de un creador. Retorno OAuth existente: https://electronicama.com/api/payments/connect-return. Probar precios y acuerdo antes de vender suscripciones del creador.
5. Vídeo: `LIVEKIT_URL` (wss://…), `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `MAGGY_STREAMERS_ENABLED=1`. Comprobar entrada y emisión entre dos dispositivos, audio, cámara, reconexión y permisos. LiveKit sirve también a la web.
6. Sandbox: configurar `STRIPE_TEST_SECRET_KEY` y `STRIPE_TEST_WEBHOOK_SECRET`; completar Checkout desde el panel administrador y confirmar recepción del webhook. Los pagos de prueba no conceden plazas ni beneficios reales. Comprobar duplicados, rechazo, expiración y reembolso.
7. Mientras se comprueba lo anterior: `OL_PAYMENTS_ENABLED=0`; no activar acceso pagado por abrir una cuenta. Cuando el vídeo esté listo, `OL_LIVE_PREMIERE=0` permite mostrar catálogo y estudio. Los paneles preparados siguen detrás de la bandera mientras no se confirme disponibilidad.
8. Tras verificar cuenta, vídeo y recorrido de pagos: `MAGGY_STREAMER_SALES_ENABLED=1`, `OL_PAYMENTS_ENABLED=1`; volver a desplegar. Comprobar `/api/admin/launch-readiness` y el panel. No se cambia automáticamente una bandera de cobro al renombrar la web.
9. Verificar publicación: nombre y botones, registro, correo, aislamiento de usuarios, acceso anual y precio de 25 EUR/año. No hacer un cargo real sin un comprador y una compra reales autorizados. Preparar devolución y soporte.

## Límites de la comprobación actual

El entorno de trabajo no tiene acceso de red a electronicama.com, Stripe ni Vercel; no se han leído ni modificado sus ajustes reales en esta revisión. El despliegue Git no demuestra que Stripe esté activo ni que el despliegue publicado haya terminado. La prueba en dos dispositivos y la verificación real de Stripe siguen pendientes hasta disponer de esos resultados.
