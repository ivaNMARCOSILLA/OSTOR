"""Access support stays available to guests and queues private owner notices."""
import hashlib
import hmac
import ipaddress
import os
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

import notifications
from email_security import clean_email
from membership import clean_username, database, get_user, now_utc, stamp


bp = Blueprint('access_help', __name__)
MAX_BODY_BYTES = 8192
FIELDS = frozenset({'identifier', 'contact_email', 'category', 'details'})
CATEGORIES = {
    'code': 'Código de acceso por correo',
    'password': 'Contraseña',
    'two_factor': 'Verificación en dos pasos',
    'payment': 'Pago o acceso después de pagar',
    'other': 'Otro problema de acceso',
}
GENERIC_MESSAGE = 'Hemos guardado tu solicitud de ayuda para revisión. No envíes contraseñas ni códigos de acceso.'


def _input():
    # Reject extra fields before recording anything. Authentication passwords,
    # tokens and codes never form part of this endpoint's accepted payload.
    if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
        raise RequestEntityTooLarge()
    request.max_content_length = MAX_BODY_BYTES
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not set(data) <= FIELDS:
        raise ValueError('Envía solo el usuario o correo, el correo de contacto y una descripción del problema, sin contraseñas ni códigos.')
    identifier = data.get('identifier')
    contact = data.get('contact_email', '')
    category = data.get('category')
    details = data.get('details', '')
    if not isinstance(identifier, str) or not 1 <= len(identifier) <= 254:
        raise ValueError('Indica tu usuario o correo electrónico.')
    if not isinstance(contact, str) or len(contact) > 254:
        raise ValueError('Indica un correo electrónico de contacto válido.')
    if not isinstance(category, str) or category not in CATEGORIES:
        raise ValueError('Selecciona el problema de acceso.')
    if not isinstance(details, str) or len(details) > 500 or any(ord(c) < 32 and c not in '\n\t' for c in details):
        raise ValueError('Describe el problema en un máximo de 500 caracteres, sin contraseñas ni códigos.')
    identifier = clean_email(identifier) if '@' in identifier else clean_username(identifier)
    if not identifier:
        raise ValueError('Indica tu usuario o correo electrónico.')
    return identifier, clean_email(contact), category, details.strip()


def _network_bucket():
    # ProxyFix may consume generic forwarded headers. Read the original peer
    # locally, or Vercel's edge-owned address header in that managed deployment.
    original = request.environ.get('werkzeug.proxy_fix.orig', {})
    value = request.headers.get('X-Vercel-Forwarded-For') if os.getenv('VERCEL') == '1' else original.get('REMOTE_ADDR', request.remote_addr)
    try:
        if not isinstance(value, str) or '%' in value:
            raise ValueError('address')
        address = ipaddress.ip_address(value)
        address = getattr(address, 'ipv4_mapped', None) or address
        network = address.compressed
    except ValueError:
        network = 'unknown'
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    return hmac.new(key, ('access-help-ip-v1:' + network).encode(), hashlib.sha256).hexdigest()


def _allow_request():
    instant = now_utc()
    cutoff = stamp(instant - timedelta(minutes=15))
    bucket = _network_bucket()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM login_attempts WHERE attempted_at<=?', (cutoff,))
        count = conn.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE bucket=? AND attempted_at>?',
                             (bucket, cutoff)).fetchone()['n']
        if count >= 3:
            return False
        conn.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)', (bucket, stamp(instant)))
    return True


@bp.post('/api/account/access-help')
def request_access_help():
    try:
        identifier, contact, category, details = _input()
        user = get_user()
        # An email identifier is a usable guest contact. A signed-in account can
        # omit it; only its own profile may supply the fallback address.
        contact = contact or (identifier if '@' in identifier else None)
        if not contact and user:
            contact = user['profile_email']
        if not contact and not user:
            raise ValueError('Indica un correo de contacto para poder revisar tu problema de acceso.')
    except RequestEntityTooLarge:
        return jsonify(error='La solicitud es demasiado larga. Describe el problema en un máximo de 500 caracteres.'), 413
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not _allow_request():
        return jsonify(error='Has enviado varias solicitudes de ayuda. Espera 15 minutos antes de enviar otra.'), 429

    detail = '\n'.join([
        'Solicitud de ayuda de acceso.',
        'Usuario o correo indicado: ' + identifier,
        'Correo de contacto: ' + (contact or 'No indicado; cuenta con sesión iniciada.'),
        'Problema: ' + CATEGORIES[category],
        'Descripción: ' + (details or 'Sin descripción adicional.'),
        'Este aviso no verifica la identidad ni autoriza cambios de cuenta o de pago.',
    ])
    # notify commits a durable admin record before attempting mail. Its False
    # result means pending/failed delivery, while True means mail was sent.
    # Do not call it while holding a database transaction or a rate-limit lock.
    try:
        sent = notifications.notify('access_help', 'Ayuda con el acceso de un cliente', detail,
                                    event_key='access-help:' + secrets.token_hex(16),
                                    member_ids=[user['id']] if user else ())
    except Exception:
        current_app.logger.warning('An access-help request could not be recorded.')
        return jsonify(error='No hemos podido guardar la solicitud. Conserva el formulario y vuelve a pulsar Enviar ayuda.'), 503
    return jsonify(ok=True, message=GENERIC_MESSAGE, delivery='sent' if sent is True else 'queued')


def install(app):
    if bp.name not in app.blueprints:
        app.register_blueprint(bp)
