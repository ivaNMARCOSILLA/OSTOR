# Revisión de mantenimiento · 9.24.0

## Cambios

- Diagnóstico de LiveKit protegido con `require_admin` en servidor y oculto por
  atributo `hidden` para las demás cuentas, también para concesiones gratuitas.
- El vídeo de cámara llena el reproductor incluso si quedó elegida una vista de
  pantalla que ya no existe. Pantalla compartida grande y cámara pequeña.
- Comentarios siempre visibles, sin botón para ocultarlos, dentro del reproductor y también en pantalla completa: máximo del
  75 % de altura para el panel y desplazamiento del historial reciente.
- Se corrige el estado visitado de los enlaces con aspecto de botón: no heredan texto dorado sobre fondo dorado. Se comprueba el texto realmente dibujado mediante captura de píxeles en los estados visitado, hover, foco y pulsado.
- Botones dorados estáticos, contraste comprobado usando el relleno real de texto
  del navegador. Se conservan negro de fondo y movimiento decorativo independiente.
- Más comprobaciones del mantenimiento: revisiones compartidas, edades, clasificación,
  almacenamiento del chat, visitas, protección de diagnósticos y límites de verificación.
- Frecuencia local de mantenimiento configurable: 15, 30 (predeterminada), 60 minutos
  o solo manual. Contraste y enlaces son opcionales; permisos del servidor siempre
  se revisan. Las preferencias se guardan por cuenta administrativa y navegador.

## Contenido adulto

Tabaco/vapeo/alcohol es una clasificación del canal, no una etiqueta del hábito
personal del creador. Exige aceptación expresa de las reglas. Administración puede
imponer la clasificación y el creador no puede retirarla por su cuenta.

Hay control de declaración de edad antes de token de vídeo, continuidad, comentarios
 y pago de suscripción del canal. Se prohíbe promover, ofrecer, regalar o compartir
productos entre protagonistas o con suscriptores, así como participación de menores.
La fecha de nacimiento se usa para el cálculo y no se guarda; la declaración caduca
tras 24 horas y cambia si cambian país/evaluación/contexto de clasificación.

La IP no acredita edad ni detecta toda VPN. El mínimo es 21 cuando falta evaluación
fiable; un evaluador de servidor de confianza podría aplicar 18 para España sin VPN.
No se ha conectado un proveedor de evaluación de VPN ni verificación documental.
Por eso la interfaz no afirma identidad verificada ni cumplimiento legal universal.
No hay detección visual automática de fumar o beber: clasificación, denuncias y
revisión administrativa siguen siendo necesarias.

## Verificación

La batería cubre registro/correo/contraseñas/2FA, administración, pagos simulados,
plazas, permisos, reproducción, buscador, sincronización, chat, voces, hologramas,
recordatorios y estilos. PostgreSQL se prueba en una base temporal de bucle local.
Se actualizaron expectativas antiguas: espectadores gratuitos ya pueden consultar
canales y el título de Hologramas incluye su distintivo Geometría viva.

El seguimiento prolongado usa vídeo generado por canvas y LiveKit simulado,
con cuentas aisladas. Comprueba cada minuto vídeo en avance, rechazos de permisos,
botón Acceso estable, anchos 320/390/768/1440 y edición desde otro contexto.
No mide una emisión real, facturación real, identidad de personas ni carga distribuida.

La grabación de vídeos no está activa. Se ha propuesto almacenamiento privado
en Cloudflare R2 conectado a LiveKit Egress, con acceso administrativo temporal
y borrado a los 30 días. Falta elegir/configurar el almacenamiento y la grabación;
el panel de mantenimiento lo señala como pendiente. No existe aún una carpeta
real de grabaciones que se pueda enlazar.
El resultado y la duración reales se incorporan tras terminar el seguimiento.

## Resultado del seguimiento

Completado: 1.800 segundos reales, 31 rondas, sin interrupción observada del vídeo
de canvas. Todas las rondas comprobaron permisos administrativos rechazados para
visitante y cuenta gratuita, texto de Acceso sobre dorado y recepción de cambios
remotos en anchos de 320, 390, 768 y 1440. La prueba específica de enlaces visitados
y las peticiones posteriores de grabación/denuncias se validaron por separado.
