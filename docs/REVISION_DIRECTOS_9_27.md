# Revisión de directos 9.27

## Correcciones comprobadas

- Invitaciones para seis creadores además del anfitrión; lista privada y retirada que libera la plaza. El invitado no inicia ni finaliza su propio canal al entrar o salir de otro.
- Sala nueva por emisión para que los tokens antiguos no alcancen la siguiente; una interrupción del listado no elimina la sesión ni las invitaciones.
- Los invitados autorizados entran también en canales exclusivos; el control de suscripciones reconoce sus identidades y conserva al grabador Egress.
- Cámara múltiple en mosaico; pantalla compartida principal y cámaras pequeñas. Si hay varias pantallas, el espectador escoge cuál ver.
- Controles con espacio propio, botón de cierre accesible y chat con altura mínima en móviles. Los controles esenciales permanecen dentro de pantalla completa.
- El espectador se reconecta a la nueva sala al cambiar de emisión; el invitado necesita otra invitación.
- Comentarios ligados a la emisión, votos idempotentes por cuenta, contadores reales y protección ante respuestas atrasadas.
- Miniaturas JPEG del vídeo publicado: se prioriza la pantalla compartida; sin pantalla se usa cámara. Captura de 320×180 cada 20 segundos, sin iniciar medios ni tomar la vista privada. El servidor valida formato, cuenta y sesión, recodifica sin metadatos y limita cuatro subidas por minuto. Las vistas adultas/exclusivas respetan sus permisos. La miniatura se retira al terminar o cambiar de sesión y deja de servirse si lleva más de 90 segundos sin actualizar.

## Verificación y límites

La revisión de servidor ejecutó 282 pruebas: 263 correctas y 19 omitidas por ser específicas de PostgreSQL. Las 19 pruebas de PostgreSQL se ejecutaron por separado con éxito, en una base temporal sin datos reales. Las pruebas de Chromium verifican siete vídeos de canvas en movimiento, cinco tamaños de pantalla incluyendo orientación horizontal, clics sobre controles, chat visible, dos pantallas compartidas, consentimiento y salida del invitado, miniaturas sin F5, continuidad ante errores temporales, y texto oscuro sobre dorado en estados visitado/foco/pulsado.

La señalización LiveKit está simulada en las pruebas de interfaz. El diagnóstico adicional de WebRTC local no obtuvo candidatos ICE en este entorno; no equivale a haber transmitido desde siete dispositivos ni verifica el ancho de banda, la acústica o la grabación de siete participantes en producción. No se enviaron cobros, correos ni grabaciones reales en estas pruebas. La prueba R2 previa fue confirmada por el usuario desde su panel.

El mantenimiento privado se revisa cada 30 minutos con la pestaña del administrador abierta y visible. El flujo público existente de GitHub Actions tiene programación a los minutos 7 y 37 de cada hora, sujeto a que GitHub mantenga habilitadas las acciones programadas. Las pruebas funcionales aisladas se ejecutan en cambios de código; no publican emisiones ni abren cámaras.
