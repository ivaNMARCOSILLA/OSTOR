# Entradas acumuladas · 9.28.9

La portada muestra un total persistente de entradas, con su fecha de inicio.
La actividad reciente se mantiene dentro de un desplegable independiente.

El total se inicia una sola vez con las sesiones consentidas que todavía estén
registradas desde el lunes a las 00:00 de la semana de activación, en la zona
Europe/Madrid. Después continúa acumulando nuevas sesiones: no se reinicia al
cambiar de semana ni baja cuando salen de la ventana de 24 horas.

Una actualización o un latido de una sesión en curso no suma otra entrada.
Una sesión nueva según las reglas existentes sí suma. No es un recuento de
personas únicas y no se añaden cifras simuladas ni visitas históricas que ya no
estén disponibles.

El detalle de las visitas conserva su plazo de siete días y la retirada de
consentimiento elimina los registros del navegador. El total se conserva como
una suma anónima: su tabla solo tiene la clave del contador, la fecha inicial y
el número acumulado, sin relaciones con usuarios, navegadores o conexiones.

La inicialización y los incrementos se realizan en transacciones para evitar
duplicados al coincidir peticiones. La migración SQLite/PostgreSQL incluye esta
tabla y el mantenimiento de administración comprueba su estructura. Si falla una
actualización, la interfaz conserva el último total real y muestra un aviso.
