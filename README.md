# Ol · electronicama.com

Música gratuita desde Audius, Internet Archive, Wikimedia Commons y Radio Browser. Favoritos, historial, listas y temporizador gratuitos. La cuenta gratuita permite guardar el progreso de una colección base de 1.000 stickers con sonido.

**Ol Live · Ol del bueno** incluye vídeo, categorías, comentarios y regalos externos sin comisión de Ol. Acceso completo durante siete días de prueba y, después, 25 € en un único pago voluntario, sin renovación. La prueba no empieza mientras el vídeo no esté disponible. Las 100 plazas de fundador se reservan durante la prueba y requieren confirmar 25 € al final para conservar el número, además de un primer directo verificado de 30 minutos y 2 horas cada 30 días después. Solo la plaza n.º 1 podrá optar a una cesión futura; todavía no hay compraventa. La reserva exige comprobación visual de un solo uso.

Flask + PostgreSQL persistente en Vercel; SQLite para desarrollo local. Nunca guardar secretos ni datos de cuentas en Git. Consulta [la guía de administración](docs/ADMIN_OL.md) para configuración, correo, invitaciones y moderación.

## Desarrollo

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Para pruebas, instala también requirements-dev.txt y ejecuta `python -m unittest discover -s tests -p 'test_*.py'`. Las pruebas de PostgreSQL requieren una base independiente de pruebas en loopback. `tests/run_browsers.py` prepara cuentas y bases temporales para las comprobaciones de navegador; nunca se crean pagos de prueba en producción.

La transcripción de voz de Ol Live depende del navegador y puede fallar; la interfaz muestra su estado. Los documentos legales siguen siendo provisionales.

Las primeras 100 plazas disponibles se reservan con la prueba de siete días. Para conservar el número se debe confirmar un único pago de 25 €; se ofrece al finalizar los siete días de prueba. Al vencer sin pago, la plaza vuelve a estar disponible y su historial se archiva en privado. No se reinicia la prueba de la cuenta y pagar tarde no garantiza recuperar el número anterior. Si las 100 plazas están ocupadas, no se inicia una nueva prueba con plaza hasta que se libere una.

Las suscripciones a creadores siguen en preparación. Sus precios y beneficios requieren acuerdo entre creador, administración y Gref. La configuración de Stripe solo se muestra en administración; durante el próximo estreno no se ofrecen cobros, enlaces externos ni regalos monetarios.

La cuenta permite activar voluntariamente verificación de dos factores TOTP con una app autenticadora y ocho códigos de recuperación de un solo uso. No se activa automáticamente ni requiere SMS. Conserva el mismo secreto de servidor al migrar cuentas que tengan 2FA activa.


Pagos, mantenimiento, supervisión y preparación Android: [guía de activación](docs/PAGOS_Y_PLAY_STORE.md). La PWA ya se instala desde el navegador. No se afirma publicación en Google Play ni cobros reales sin completar la configuración del gestor.


Construir el paquete fuente: `python tools/build_release.py`. Comprobar su contenido y SHA-256: `python tools/verify_release.py ../artifacts/OL_9_8_2.zip`. El ZIP usa la carpeta `Ol`, excluye cuentas y secretos y sirve para web/PWA; la plantilla Android no es una publicación en Play Store.

Ol 9.8.2: [próximo estreno y preparación privada](docs/PREESTRENO_OL_LIVE.md). Nuevas pruebas de siete días; después, 25 € en un único pago. El modo estreno impide iniciar pruebas y cobros y oculta los paneles públicos de Ol Live.
