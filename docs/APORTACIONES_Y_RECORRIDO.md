# Aportaciones voluntarias y recorrido de entradas

## Aportar a electronicama

La portada incluye `/#contributions`, enlazado desde el menú en móvil y ordenador.
Se proponen 3, 5 y 10 euros y una cantidad libre de 1 a 500 euros. El formulario
requiere confirmar expresamente el carácter voluntario y el pago único. Admite
cuentas gratuitas y visitantes sin cuenta. El importe se valida en céntimos
enteros tanto en el navegador como en el servidor.

Las aportaciones financian el mantenimiento de electronicama. No conceden Ol
Live, insignias, participación empresarial ni servicios de pago. No se crea una
sesión de cobro al visitar la página; Stripe se abre únicamente tras enviar el
formulario. Cada pago se confirma en Stripe y es de una sola vez.

Se utiliza la configuración de Stripe ya existente y sus controles de
mantenimiento. El formulario informa de indisponibilidad cuando el cobro no está
habilitado. No se exponen claves ni se reciben datos completos de tarjeta en la
aplicación. Los regresos `contribution=processing`, `received` o `cancelled` no
confirman el pago desde el cliente.

El webhook existente `/api/payments/webhook/platform` valida la firma y el modo
real antes de procesar la aportación. Debe recibir `checkout.session.completed`,
`checkout.session.async_payment_succeeded`, `checkout.session.expired`,
`charge.refunded`, `charge.dispute.created` y `charge.dispute.closed`. No hace
falta otro endpoint de webhook ni un secreto público nuevo.

El registro conserva el importe, la moneda, el pedido y el pago de Stripe, sus
fechas y el estado de confirmación, devolución o disputa. Se vincula a la cuenta
solo si había una sesión iniciada. Los eventos repetidos no duplican el cobro ni
el registro. Una devolución previa no vuelve a contarse como un pago disponible
cuando llega después la confirmación de Checkout. Las disputas permanecen
retenidas para revisión en Stripe.

El panel privado `/account#admin-contributions` muestra las últimas 25
aportaciones y los importes confirmados, devueltos y en disputa. Sus cifras no
descuentan las comisiones de Stripe ni representan un saldo bancario. No se
ofrece una acción de cobro o de devolución desde este panel. Las cuentas con
historial de aportaciones pagadas se archivan para conservar la trazabilidad.

## Recorrido de fechas

El recorrido público muestra hasta 120 fechas por página. Incluye un calendario
inicial de 120 fechas, contando el día de activación, y continúa acumulando fechas
sin borrar las anteriores. Las páginas adicionales permiten recorrer todo el
historial. Al abrirlo se muestran las fechas más recientes dentro de la tabla.

Los calendarios anteriores de quince fechas se amplían usando su fecha de
activación original, una sola vez. Se conservan el total compartido entre
dispositivos, los recuentos diarios y las cantidades antiguas sin fecha. Ampliar
el calendario no genera visitas. Los días anteriores sin datos recuperables se
muestran como «Sin datos disponibles». El detalle personal sigue sujeto a sus
siete días de conservación y al consentimiento existente.
