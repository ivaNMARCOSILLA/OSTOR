# electronicama · identidad compartida y stickers 9.18.0

Música, cuenta, administración, Ol Livis y páginas legales usan la misma hoja de
estilo: tinta mineral, marfil, champán, verde mar y azul de atardecer, con acentos
rosados puntuales. Se retiraron las ramas visibles y la sección de fondo de pantalla,
incluidos los enlaces de navegación y el acceso rápido del manifiesto PWA.

Los stickers tienen escenas vectoriales originales y estables por identificador,
con composiciones de órbitas, olas, constelaciones, jardín, cristales y auroras.
El álbum y el chat usan la misma escena de cada sticker. Se generan solo para los
stickers visibles, conservan el movimiento anterior y respetan la pausa/reducción
de movimiento. Las etiquetas llevan una superficie legible propia.

## Voz

Se puede elegir perfil femenino/masculino y una voz española instalada. Se usa la
voz real ofrecida por el dispositivo, con tono sin alterar; si no se identifica el
perfil solicitado, la interfaz lo indica. La preferencia se guarda por cuenta y
navegador. La voz solo comienza con un clic y no activa el micrófono.

La voz neuronal admite ElevenLabs y Azure Speech. Está desactivada mientras no se
configure un proveedor: los cambios no crean ninguna cuenta ni generan cargos.
El servicio tiene sus propias tarifas. La integración envía únicamente la frase
predeterminada del sticker; no admite texto libre ni datos personales del usuario.
El audio generado se guarda para reutilizarlo entre reproducciones. Se limitan las
peticiones y las nuevas generaciones por cuenta; una generación concurrente devuelve
«pendiente». No se clonan voces ni se presenta audio sintético como grabación humana.

Para ElevenLabs, el operador debe crear su cuenta en https://elevenlabs.io/ y elegir
dos voces de su catálogo. En Vercel Production, usando sus valores privados:

- OL_STICKER_VOICE_PROVIDER=elevenlabs
- OL_ELEVENLABS_API_KEY: clave privada del proveedor.
- OL_ELEVENLABS_FEMALE_VOICE_ID: identificador de la voz femenina elegida.
- OL_ELEVENLABS_MALE_VOICE_ID: identificador de la voz masculina elegida.
- OL_STICKER_NEURAL_VOICES=1: habilitar solo tras completar la configuración.

Alternativa Azure: proveedor azure, OL_AZURE_SPEECH_KEY y OL_AZURE_SPEECH_REGION,
con la misma bandera de activación. Las voces españolas son Elvira y Álvaro.
Las claves nunca se ponen en variables públicas ni en el chat.

Este chat no tiene instalado un conector vocal. Se pueden preparar aquí guiones y
estilos, trabajar la generación en la aplicación del proveedor y conectar después
la API a electronicama. La configuración y la síntesis real externas no se han
verificado desde este entorno; las pruebas usan un proveedor simulado.

## Comprobaciones

228 pruebas de servidor con SQLite y 19 de PostgreSQL aislado superadas. Pruebas de
motor vocal: autenticación, CSRF, servicio desactivado, dos voces, reutilización de
audio, exclusión de texto libre, fallo recuperable y concurrencia.

En navegador: voces instaladas femeninas/masculinas, tono sin modificar, preferencias,
sin reproducción automática y escenas diferentes. Estilo compartido verificado en
seis páginas a 320/390/1440 px; contraste del título contra todas las paradas de su
degradado superior a 4,5:1. También se revisaron registro, navegación, reproductor,
álbum, administración y sello postal. Las pruebas locales no certifican el despliegue
de producción ni la síntesis externa real.
