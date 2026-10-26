# Ol 9.8.3 · cuentas, correo y revisión de accesos

El registro es público y no exige autorización administrativa ni pago. Correo y apodo son opcionales: el usuario único y la contraseña siguen permitiendo entrar a las cuentas existentes. El apodo se muestra en la cuenta y los comentarios; el correo es privado.

Al registrar un correo o cambiarlo con la contraseña actual se solicita confirmación. Para entrar con correo y contraseña o recuperar la contraseña, el correo debe estar confirmado. La confirmación caduca a las 24 horas; la recuperación, a los 30 minutos. Ambos enlaces son aleatorios, de un solo uso, vinculados a dirección y versión de seguridad; en la base solo se guarda su hash. Los enlaces usan el fragmento de la dirección y se retiran de la barra del navegador antes de enviar la confirmación por POST.

La recuperación requiere comprobación humana, aplica límites de intentos y devuelve el mismo mensaje para direcciones existentes y desconocidas. Cambiar la contraseña revoca las sesiones anteriores y no desactiva 2FA. Cambiar el perfil exige contraseña actual y, si corresponde, autenticador. El fallo del envío no elimina una cuenta recién creada. Nunca se envían contraseñas por correo ni se publican tokens en administración.

Los mensajes utilizan el SMTP o Resend existente y OL_EMAIL_FROM. Para clientes, Resend requiere un remitente de un dominio verificado; onboarding@resend.dev es un remitente de pruebas y no sirve como solución pública. El panel administrativo muestra el dominio y si existe configuración de cliente, sin revelar claves ni afirmar una entrega real no comprobada. Las pruebas de navegador capturan los correos únicamente en un directorio temporal local que se elimina al finalizar.

## Supervisión

- En cada página abierta, `assets/navigation.js` revisa enlaces cada cinco minutos. Corrige solo equivalencias conocidas y adapta los accesos al estado de próximo estreno. Abre secciones plegadas y sitúa el foco cuando se pulsa un acceso. Los problemas no reconocidos quedan pendientes; no se inventan destinos ni se ejecutan compras.
- GitHub Actions programa una revisión pública de solo lectura a los minutos 7 y 37 de cada hora. GitHub puede retrasar el comienzo. Comprueba las páginas, recursos y destinos internos; respeta el mantenimiento intencional. No inicia sesión ni crea cuentas o movimientos en producción. Guarda el informe durante 14 días.
- En cada push a main, pull request o ejecución manual, también se prueban navegación, registro, confirmación y recuperación de correo, 2FA, estudio y administración en bases temporales. Los escenarios de estreno y de servicio abierto se prueban por separado. PostgreSQL tiene un servicio efímero exclusivo de prueba.

El historial se abre desde Administración → Revisión automática de accesos y funciones. El flujo necesita que GitHub Actions esté habilitado en el repositorio. Las comprobaciones registran fallos; no cambian código ni publican modificaciones arbitrarias por sí solas. Los accesos antiguos conocidos sí se reparan en la interfaz con reglas explícitas.

Comprobación manual:

```sh
python tools/check_navigation.py --base-url https://electronicama.com --output navigation-health.json
python tests/run_browsers.py test_registration_browser.py test_email_browser.py test_shortcuts_browser.py
```

Los informes JSON de revisión local no se incluyen en Git. Los datos privados de cuentas, correos y enlaces capturados no se incorporan al ZIP de distribución.
