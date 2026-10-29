# Revisión funcional de electronicama · 29 de octubre de 2026

Informe cerrado: 2026-10-29T19:19:12+01:00. Código de producto: 9.13.7.

## Resultado

| Comprobación | Resultado |
| --- | --- |
| Servidor con SQLite aislado | 213 pruebas superadas; 19 reservadas para PostgreSQL |
| PostgreSQL 17 aislado | Las 19 pruebas superadas |
| Total de pruebas de servidor ejecutadas | 232 superadas |
| Interfaz en Chromium | 37 recorridos superados, incluidos los modos abierto y próximo estreno |
| Peticiones concurrentes locales | 240 peticiones, 12 trabajadores, cero fallos |
| Navegación estática | 7 páginas, 185 enlaces, cero destinos rotos |
| JavaScript de cuenta, operaciones y fundadores | Sintaxis comprobada |

Las cifras cuentan comprobaciones, no personas ni usuarios de la plataforma. El tiempo
local de respuesta no estima la capacidad o latencia de Vercel en producción.

## Recorridos comprobados

- Registro libre con comprobación humana, errores recuperables, aislamiento de cuentas,
  correo verificado, inicio por correo, recuperación de contraseña y doble factor.
- Compra anual: aceptar condiciones, crear Checkout de 25 EUR, volver sin conceder
  acceso por esa vuelta, recibir el webhook firmado, activar un solo año, enviar un
  único correo de solicitud de fundador y solicitar después la insignia disponible.
- OAuth de Stripe: estado ligado a la sesión, caducidad, uso único, rechazo de cuenta
  de pruebas, conservación solo del identificador de cuenta y retorno al borrador.
- Correo de acceso: fallo de entrega conserva el acceso pagado y permite reintento;
  no se envía a una dirección sin verificar ni tras una reversión pendiente de aviso.
- 32 webhooks simultáneos de un mismo pago: un recibo y un solo año de acceso.
- Seis registros simultáneos con el mismo nombre: una sola cuenta creada.
- Última insignia en concurrencia, liberación por vencimiento anual y acceso ordinario
  después de agotar las 100 insignias.
- Precio mensual de canal 3–4 EUR, precio anterior protegido, meses y cambios horarios,
  aprobaciones expresas y retirada de permisos del moderador.
- Administración privada, clientes e invitaciones, historial, roles de comunidad,
  mantenimiento, recorridos opcionales de visitantes y retirada del consentimiento.
- Catálogo y controles de música, YouTube oficial con proveedor simulado, favoritos,
  controles multimedia, pantalla compartida y cámara privada con dispositivos simulados.
- Continuidad del directo ante fallos transitorios de 25/30/60 segundos, cierre por
  revocación real, aviso de descanso a las dos horas y aplazamiento cuatro horas.
- Hologramas, colección de stickers, diseño personalizado, sonido manual y movimiento
  reducido. Diseños móviles y escritorio; varios recorridos incluyen 320–1440 píxeles.

## Ajustes realizados durante la revisión

Se actualizaron pruebas que todavía esperaban el nombre Ol, antiguas pruebas gratuitas
o acceso de por vida. Las pruebas PostgreSQL comprueban ahora el pago anual firmado.
Se conservan por separado las pruebas de lectura de compras históricas.

Cada recorrido de navegador usa ahora una base temporal propia. De ese modo las cuentas,
invitaciones, puntos y permisos creados en una prueba no alteran la siguiente.
El recorrido de acuerdos heredados se ejecuta explícitamente con su gestor de prueba;
esto no cambia el gestor Stripe de la web desplegada.

Se añadieron a la revisión automática los botones de Stripe y contratación, el recorrido
anual completo y la carga local. Las pruebas funcionales se ejecutan en cada cambio;
la revisión pública programada conserva su frecuencia de media hora.

## Límites de la verificación

Todo se ejecutó con bases temporales y sin cobros reales. Stripe y el correo se simulan
solo en sus conexiones externas; los pedidos, firmas de webhook, cuentas, acceso y
solicitudes se procesan en el servidor local real. No se enviaron correos a clientes.

El entorno no tiene acceso autorizado de red a electronicama.com, Stripe, Resend o Vercel.
Por ello este informe no certifica el estado del despliegue público, la entrega externa
real del correo, un cargo real ni la calidad de LiveKit entre dos dispositivos físicos.
Las pruebas de navegador se hicieron con Chromium; no equivalen a una prueba física en
Safari/iPhone. Tampoco certifican reproducción de YouTube con el teléfono bloqueado.

La copia ZIP es código fuente revisado, no una IPA ni un paquete firmado para tiendas.
