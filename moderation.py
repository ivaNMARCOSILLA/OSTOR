"""Rule-based Spanish moderation for public comments, profiles and captions."""
import re
import unicodedata


def normalized(value):
    text=unicodedata.normalize('NFKD',str(value)).casefold()
    text=''.join(c for c in text if not unicodedata.combining(c) and unicodedata.category(c)!='Cf')
    return ' '.join(re.sub(r'[_\W]+',' ',text).split())


INSULTS=re.compile(r'\b(?:gilipollas|cabron(?:a|es|as)?|hij[oa]s? de puta|put[ao]s?|subnormales?|maricones?|sudacas?)\b')
SEXUAL_MINOR=re.compile(r'\b(?:pederastas?|pedofilos?|pedofilas?|porno(?:grafia)? infantil|(?:sexo|desnudos|contenido sexual) (?:con |de )?menores)\b')
ILLICIT=re.compile(r'\b(?:vendo|vendemos|compro|compramos|venta de|trafico de|se venden)\b.{0,70}\b(?:cocaina|heroina|drogas|armas ilegales|armas sin licencia|tarjetas robadas|datos robados|pornografia infantil)\b')
THREATS=re.compile(r'\b(?:te voy a matar|voy a matarte|os voy a matar|te voy a violar)\b')


def classify(value):
    text=normalized(value)
    for category,rule in [('sexual_minors',SEXUAL_MINOR),('threat',THREATS),('illicit_trade',ILLICIT),('insult',INSULTS)]:
        if rule.search(text):return category
    return ''


def is_abusive(value):return bool(classify(value))


def validate_public_text(value):
    if is_abusive(value):
        raise ValueError('Revisa el texto: no se permiten insultos graves, acoso, amenazas, expresiones sexuales sobre menores ni ofertas de actividades ilegales.')
