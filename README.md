# Ol · electronicama.com

Música gratuita desde Audius, Internet Archive, Wikimedia Commons y Radio Browser. Favoritos, historial, listas y temporizador gratuitos. La cuenta gratuita permite guardar el progreso de una colección base de 1.000 stickers con sonido.

**Ol Live** reúne vídeo en directo, categorías, comentarios moderados y regalos externos sin comisión de Ol. Los pagos solo corresponden a ver o emitir Ol Live: 1 € de bienvenida por 14 días, 6 €/mes para espectadores y 8 €/mes para creadores. Las primeras 100 reservas de fundador incluyen acceso de creador gratuito sin vencimiento e insignia numerada personalizable. Los cobros siguen bloqueados hasta que el vídeo esté disponible.

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
