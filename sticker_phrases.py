"""Positive original sticker phrases; spoken locally by the device on demand."""
import hashlib
PHRASES = (
 '¡Oh, qué bueno!', '¡Ol del bueno!', '¡Este es nuestro momento!',
 '¡Qué alegría verte!', '¡Viejo, qué grande!', '¡Te ha quedado genial!',
 '¡Un aplauso para ti!', '¡Esto suena muy bien!', '¡Vamos a por otra sonrisa!',
 '¡Compartir sienta bien!', '¡Me encanta esa idea!', '¡Qué buena energía!',
 '¡Un abrazo de lejitos!', '¡Brillas con luz propia!', '¡Así da gusto!',
 '¡Ol Live, tu mejor momento!', '¡Hoy toca disfrutar!', '¡Tú pones la chispa!',
 '¡Menudo descubrimiento!', '¡Esto merece un sticker!', '¡Vamos, equipo!',
 '¡Qué gusto coincidir!', '¡Buen ritmo, viejo!', '¡Lo bueno se comparte!',
 '¡Pequeños momentos, grandes sonrisas!', '¡Qué bonito te sale!',
 '¡A tu ritmo, siempre!', '¡Traes Ol del bueno!', '¡Una más y sonreímos!',
 '¡Bienvenido a tu espacio!', '¡Me has alegrado el día!', '¡Nos vemos en Ol Live!'
)
ENDINGS=(
 '', 'Ol del bueno.', 'Tu momento es ahora.', 'A tu ritmo.', 'Con una sonrisa.',
 'Lo bueno se comparte.', 'Gracias por estar aquí.', 'En buena compañía.',
 'Un instante para recordar.', 'Hoy creamos juntos.', 'Tu chispa se nota.',
 'Vamos por otro buen momento.', 'Nos vemos en Ol Live.', 'Siempre sumando.',
 'Hay mucho por descubrir.', 'Qué gusto tenerte cerca.', 'Un poquito de alegría.',
 'Que siga la buena onda.', 'Eso merece celebrarse.', 'De lejitos, con cariño.',
 'Viejo, va por ti.', 'Este espacio también es tuyo.', 'Celebremos las pequeñas cosas.',
 'Hoy suena a felicidad.', 'La próxima sonrisa es tuya.', 'Qué bien coincidir.',
 'Un nuevo día para crear.', 'Tu energía cuenta.', 'Un paso a la vez.',
 'Vamos a disfrutarlo.', 'Un abrazo desde Ol.', 'Sigamos conectando.'
)
LEGACY=['hello','spark','wave','heart','star','planet','leaf','compass','moon','bolt','infinity','crown']
def phrase_for(ident):
 if ident in LEGACY:index=LEGACY.index(ident)
 elif ident.startswith('emoji_') and ident[6:].isdigit():index=int(ident[6:])
 else:index=int.from_bytes(hashlib.sha256(ident.encode()).digest()[:4],'big')%1024
 return (PHRASES[index%32]+' '+ENDINGS[(index//32)%32]).strip()
