# Espectadores gratuitos y fundador n.º 1

Una cuenta registrada sin acceso anual puede consultar el catálogo privado,
obtener un token LiveKit con canPublish=false y comprobar el acceso a un directo
público. La cuenta sigue sin acceso de creador: crear canal, emitir y publicar
permanecen protegidos por el plan o una concesión administrativa existente.
La sesión, CSRF, límites, mantenimiento y comprobación de suscripción de canales
exclusivos siguen aplicándose. No se abre acceso anónimo a las salas.

El fundador n.º 1 no tiene obligación inicial ni mensual de emitir. Su actividad
real no se inventa: qualified y los segundos verificados conservan su significado.
La vigencia del pago y las revocaciones no cambian. Otros fundadores mantienen
su requisito de actividad. Administración y el estado de fundador indican la exención.

Validación: suite de 249 pruebas (19 PostgreSQL omitidas en SQLite); cuatro
expectativas anteriores de bloqueo de espectador se actualizaron a comprobar
el bloqueo de emisión y sus 33 pruebas relacionadas pasaron. Prueba de navegador
específica: cuenta no premium abre un directo y actualiza sin desconectarse,
sin mostrar el estudio. Servicios externos de vídeo y cobros no se usaron.
