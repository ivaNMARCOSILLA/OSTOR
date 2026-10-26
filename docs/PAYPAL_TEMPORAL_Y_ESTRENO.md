# Ol 9.8.0 · próximo estreno y PayPal temporal

Estado actual: música gratuita; Ol Live se presenta como próximo estreno. El anuncio lleva hojas verdes originales sobre la paleta clara de Ol. Los paneles públicos de canales y emisión están ocultos; administración conserva su estudio y comprobación de LiveKit. No se inicia ninguna nueva prueba ni se cobra durante este estado.

Configuración actual del servidor:

```dotenv
OL_PAYMENT_PROVIDER=legacy_paypal
OL_LIVE_PREMIERE=1
```

Son los valores predeterminados de esta versión. No retirar las claves de Stripe ni borrar sus pedidos o webhooks: siguen disponibles para conciliación e historial y para una futura reactivación. Los botones de Stripe están ocultos; sus endpoints de nuevos pagos y conexión no se pueden utilizar bajo PayPal.

Al abrir el estreno, cambiar OL_LIVE_PREMIERE a 0 y desplegar después de verificar emisión real entre dos dispositivos. Comprobar también el mantenimiento y MAGGY_STREAMER_SALES_ENABLED; los cobros permanecen bloqueados hasta completar esas comprobaciones. LiveKit sirve tanto a la web como a las aplicaciones.

Las nuevas pruebas duran siete días completos, una sola vez por cuenta. Los tres meses ya no se ofrecen. Los vencimientos ya concedidos y los pagos existentes se conservan. Después, continuar cuesta 25 EUR en un único pago, sin renovación automática. Una plaza impagada vencida se libera; pagar más tarde no garantiza recuperar el número.

PayPal: https://paypal.me/IMarcosIlla/25EUR. El enlace solo se ofrece cuando corresponde a la cuenta y los pagos están habilitados. Utilizar el pago comercial que corresponda; no solicitar envíos entre amigos para una compra. El cliente indica su usuario de Ol en el concepto y conserva su referencia.

Administración debe comprobar directamente en su cuenta PayPal destinatario, importe exacto de 25 EUR, moneda EUR y operación completada, y registrar su referencia única en Cuenta → Clientes de pago. Capturas, retornos del navegador y enlaces abiertos no acreditan el ingreso. Las referencias repetidas se rechazan; las invitaciones gratuitas y las cuentas con pago único ya confirmado no admiten otro cobro.

PayPal puede requerir también identificación y documentación. Este cambio no sustituye la verificación del proveedor ni las obligaciones fiscales. No se ha certificado la habilitación comercial de la cuenta PayPal desde este repositorio.

Para volver a Stripe: validar primero la cuenta y sus claves de producción, Connect y los destinos firmados; revisar acuerdos de los creadores, verificar pagos en pruebas y configurar explícitamente OL_PAYMENT_PROVIDER=stripe. El cambio no exige eliminar historial. Los documentos antiguos que describen tres meses o Stripe como método activo son históricos; este documento describe la configuración vigente.
