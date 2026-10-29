# Perfil profesional: recorridos de visitantes y descansos

## Recorrido de visitantes sin cuenta

Mi cuenta → Perfil profesional · Administración → Recorrido de visitantes sin cuenta.

La lista contiene sesiones anónimas consentidas, no identidades de personas. Cada sesión muestra páginas y acciones permitidas, ordenadas por recepción. No incluye cuentas conectadas, valores de formularios, consultas musicales, contraseñas, parámetros/fracciones de URL, IP ni huellas digitales. No se registran usuarios o movimientos inventados. Los identificadores se firman en una cookie HttpOnly y solo se guarda su hash en las tablas del recorrido.

El visitante elige Solo necesarias o Permitir métricas opcionales en la información de privacidad. Rechazar no afecta a la música. Retirar el permiso para la cookie actual detiene el registro y borra su recorrido. Se respetan GPC y la señal Do Not Track en el cliente. Las señales de privacidad o los bloqueadores pueden impedir registrar eventos; no se afirma que la lista represente a todas las visitas.

La cookie caduca tras 30 minutos de inactividad y los recorridos tras siete días. Se limita cada lote a 20 eventos, cada sesión a 500 y se aplican límites de peticiones, CSRF y una lista cerrada de páginas y acciones. Solo administración puede consultar secuencias, con paginación de sesiones y pasos. No se sincroniza la cookie con la identidad al crear una cuenta.

## Recordatorios locales de descanso

Tras dos horas conectado a una sala se muestra un aviso adecuado para emisor o espectador. Tanto posponer como cerrar el aviso programa el siguiente recordatorio cuatro horas después. No se pausa el vídeo, no se finaliza una emisión, no se enfoca ni se abre cámara o micrófono. El aviso está dentro del reproductor y también puede verse en pantalla completa. Terminar la conexión cancela su temporizador y una nueva sesión inicia su propio intervalo.

No se envían eventos de salud ni descansos a administración. Las pruebas de navegador usan reloj acelerado; no se crean visitas ni emisiones ficticias en producción.
