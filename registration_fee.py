"""One-time account registration fee, separate from Ol Live and founder access."""
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import math
import os
import re
import secrets

from flask import Blueprint, current_app, has_request_context, jsonify, request, session

import payments
from contributions import checkout_url
from membership import database, get_user, now_utc, payload, stamp
from storage import INTEGRITY_ERRORS


bp = Blueprint('registration_fee', __name__)
PRICE_CENTS = 100
GRACE_SECONDS = 300


def enabled():
    return os.getenv('OL_REGISTRATION_FEE_ENABLED', '1') == '1'


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS registration_access (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
          origin TEXT NOT NULL,exempt_reason TEXT,grace_started_at TEXT,due_at TEXT,paid_at TEXT
        );CREATE TABLE IF NOT EXISTS registration_fee_orders (
          id TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id),
          amount_cents INTEGER NOT NULL CHECK(amount_cents=100),currency TEXT NOT NULL,
          created_at TEXT NOT NULL,checkout_id TEXT UNIQUE,payment_intent TEXT UNIQUE,
          paid_at TEXT,state TEXT NOT NULL,refunded_cents INTEGER NOT NULL DEFAULT 0
          CHECK(refunded_cents>=0 AND refunded_cents<=100)
        );CREATE INDEX IF NOT EXISTS registration_fee_member ON registration_fee_orders(member_id,created_at);''')


def enroll(conn, member_id, origin='self_service'):
    """Record trusted server-side provenance without replacing an exemption."""
    conn.execute('''INSERT INTO registration_access(member_id,origin,exempt_reason)
                    VALUES(?,?,?) ON CONFLICT(member_id) DO NOTHING''',
                 (member_id, origin, None))


def mark_owner(conn, member_id, reason='owner_command'):
    """Explicit owner exemptions remain bound to the same account ID."""
    reason = str(reason or 'owner_command')[:160]
    enroll(conn, member_id, origin='owner_command')
    conn.execute('UPDATE registration_access SET exempt_reason=COALESCE(exempt_reason,?) WHERE member_id=?',
                 (reason, member_id))


def payment_available():
    # This fee does not depend on Live's premiere, Connect, or annual sales.
    if (payments.provider() != 'stripe' or os.getenv('OL_PAYMENTS_ENABLED') != '1'
            or not os.getenv('STRIPE_SECRET_KEY', '').startswith(('sk_live_', 'rk_live_'))
            or not os.getenv('STRIPE_WEBHOOK_SECRET', '').startswith('whsec_')):
        return False
    if has_request_context() and session.get('ol_play_distribution', False):
        return False
    from operations import state as maintenance_state
    return maintenance_state()['scope'] not in {'all', 'payments'}


def _identity(value):
    if isinstance(value, str):
        return value
    return value['id'] if value is not None and 'id' in value.keys() else None


def _records(conn, member_id):
    member = conn.execute('''SELECT m.id,m.role,m.password_hash,
        CASE WHEN EXISTS(SELECT 1 FROM member_archives a WHERE a.member_id=m.id AND a.restored_at IS NULL)
        THEN 1 ELSE 0 END AS archived FROM members m WHERE m.id=?''', (member_id,)).fetchone()
    access = conn.execute('SELECT * FROM registration_access WHERE member_id=?', (member_id,)).fetchone() if member else None
    return member, access


def _deadline(value):
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(value)
        return instant if instant.tzinfo else instant.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def staff_exemption(conn, member_id):
    member = conn.execute('SELECT role FROM members WHERE id=?', (member_id,)).fetchone()
    if member and member['role'] == 'admin':
        return 'admin_account'
    if conn.execute('SELECT 1 FROM ol_supervisors WHERE member_id=? AND can_review=1 AND revoked_at IS NULL', (member_id,)).fetchone():
        return 'active_supervisor'
    if conn.execute('SELECT 1 FROM pricing_moderators WHERE member_id=? AND revoked_at IS NULL', (member_id,)).fetchone():
        return 'active_pricing_moderator'
    return None


def state(user_or_id, conn=None):
    """Read only: origin, exemptions, and grace are changed by explicit hooks."""
    if conn is None:
        with database() as owned:
            return state(user_or_id, owned)
    member, access = _records(conn, _identity(user_or_id))
    instant = now_utc()
    reason = ('guest' if not member else 'archived_account' if member['archived']
              else staff_exemption(conn, member['id']) or (access['exempt_reason'] if access else None))
    exempt = bool(reason)
    paid = bool(access and access['paid_at'])
    required = bool(enabled() and member and member['password_hash'] and not exempt and not paid)
    deadline = access['due_at'] if access else None
    due = _deadline(deadline)
    in_grace = bool(required and due and instant < due)
    remaining = max(0, min(GRACE_SECONDS, math.ceil((due-instant).total_seconds()))) if in_grace else 0
    return {'enabled': enabled(), 'required': required, 'exempt': exempt,
            'exempt_reason': reason, 'paid': paid, 'in_grace': in_grace,
            'grace_seconds': remaining, 'grace_duration_seconds': GRACE_SECONDS,
            'deadline': deadline, 'server_now': stamp(instant),
            'price_cents': PRICE_CENTS, 'currency': 'eur',
            'payment_available': payment_available()}


def _start_grace(conn, member_id):
    member, access = _records(conn, member_id)
    if (not enabled() or not member or member['archived'] or not member['password_hash']
            or staff_exemption(conn, member_id)
            or (access and (access['exempt_reason'] or access['paid_at'] or access['grace_started_at']))):
        return False
    if not access:
        enroll(conn, member_id, origin='legacy_unknown')
    instant = now_utc()
    conn.execute('''UPDATE registration_access SET grace_started_at=?,due_at=?
                    WHERE member_id=? AND grace_started_at IS NULL AND paid_at IS NULL AND exempt_reason IS NULL''',
                 (stamp(instant), stamp(instant+timedelta(seconds=GRACE_SECONDS)), member_id))
    return True


def activate(member_id, conn=None):
    """Begin the five minutes once, after the caller verifies a real login."""
    member_id = _identity(member_id)
    if conn is not None:
        return _start_grace(conn, member_id)
    with database() as owned:
        member, access = _records(owned, member_id)
        if (not enabled() or not member or member['archived'] or not member['password_hash']
                or staff_exemption(owned, member_id)
                or (access and (access['exempt_reason'] or access['paid_at'] or access['grace_started_at']))):
            return False
        owned.execute('BEGIN IMMEDIATE')
        return _start_grace(owned, member_id)


def is_due(user_or_id, conn=None):
    current = state(user_or_id, conn)
    return bool(current['required'] and current['deadline'] and not current['in_grace'])


def _rate_allowed(kind='checkout', limit=6, minutes=15):
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    identity = 'registration-fee:'+kind+':'+str(request.remote_addr or 'unknown')
    bucket = hmac.new(key, identity.encode(), hashlib.sha256).hexdigest()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        cutoff = stamp(now_utc()-timedelta(minutes=minutes))
        conn.execute('DELETE FROM login_attempts WHERE bucket=? AND attempted_at<?', (bucket, cutoff))
        count = conn.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE bucket=? AND attempted_at>=?', (bucket, cutoff)).fetchone()['n']
        if count >= limit:
            return False
        conn.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)', (bucket, stamp(now_utc())))
    return True


@bp.get('/api/account/registration-fee')
def account_state():
    user = get_user()
    if not user:
        return jsonify(error='Entra en tu cuenta.'), 401
    activate(user['id'])
    response = jsonify(state(user))
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.post('/api/account/registration-fee/checkout')
def checkout():
    user = get_user()
    if not user:
        return jsonify(error='Entra en tu cuenta.'), 401
    if payload().get('fee_terms') is not True:
        return jsonify(error='Confirma la cuota de alta única de 1 €. No incluye Ol Live ni insignias.'), 400
    activate(user['id'])
    current_state = state(user)
    if not current_state['required']:
        return jsonify(error='Esta cuenta no tiene una cuota de alta pendiente.'), 409
    if not current_state['payment_available']:
        return jsonify(error='El pago de alta no está disponible. No se ha confirmado ningún cargo.'), 503
    if not _rate_allowed():
        return jsonify(error='Espera unos minutos antes de volver a iniciar el pago.'), 429
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current_state = state(user, conn)
        if not current_state['required']:
            return jsonify(error='La cuota de alta ya no está pendiente.'), 409
        row = conn.execute("SELECT * FROM registration_fee_orders WHERE member_id=? AND state IN ('created','pending') AND created_at>? ORDER BY created_at DESC,id DESC LIMIT 1", (user['id'], stamp(now_utc()-timedelta(minutes=30)))).fetchone()
        if not row:
            ident = secrets.token_hex(16)
            conn.execute("INSERT INTO registration_fee_orders(id,member_id,amount_cents,currency,created_at,state) VALUES(?,?,100,'eur',?,'created')", (ident, user['id'], stamp(now_utc())))
            row = conn.execute('SELECT * FROM registration_fee_orders WHERE id=?', (ident,)).fetchone()
        ident, created_at = row['id'], row['created_at']
    details = {
        'mode': 'payment', 'managed_payments[enabled]': 'false',
        'success_url': payments.ORIGIN+'/account?registration_fee=processing#registration-payment',
        'cancel_url': payments.ORIGIN+'/account?registration_fee=cancelled#registration-payment',
        'client_reference_id': user['id'],
        'metadata[registration_fee_id]': ident, 'metadata[member_id]': user['id'],
        'payment_intent_data[metadata][registration_fee_id]': ident,
        'payment_intent_data[metadata][member_id]': user['id'],
        'line_items[0][quantity]': '1', 'line_items[0][price_data][currency]': 'eur',
        'line_items[0][price_data][unit_amount]': '100',
        'line_items[0][price_data][product_data][name]': 'electronicama · cuota de alta única',
        'custom_text[submit][message]': 'Alta de cuenta: pago único de 1 €. No compra Ol Live ni insignias de fundador.',
        'payment_method_types[0]': 'card',
        'expires_at': str(int(datetime.fromisoformat(created_at).timestamp())+1860),
    }
    try:
        result = payments.stripe('POST', '/checkout/sessions', details, idempotency='registration-fee-'+ident)
        checkout_id = result.get('id')
        if (not isinstance(checkout_id, str) or not checkout_id.startswith('cs_live_')
                or result.get('livemode') is not True or not checkout_url(result.get('url'))):
            raise payments.PaymentError('Stripe no devolvió una sesión válida de alta.')
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            order = conn.execute('SELECT * FROM registration_fee_orders WHERE id=?', (ident,)).fetchone()
            if (not state(user, conn)['required'] or not order or order['paid_at']
                    or order['state'] not in {'created', 'pending'}):
                return jsonify(error='La cuota anterior ya se ha procesado. Actualiza tu estado.'), 409
            if order['checkout_id'] and order['checkout_id'] != checkout_id:
                raise ValueError('Registration checkout mismatch')
            conn.execute("UPDATE registration_fee_orders SET checkout_id=?,state='pending' WHERE id=?", (checkout_id, ident))
        return jsonify(id=ident, url=result['url'], grants_access=False)
    except (payments.PaymentError, ValueError) + INTEGRITY_ERRORS:
        return jsonify(error='No se pudo abrir el pago. No se ha confirmado el alta; puedes reintentar.'), 502


@bp.post('/api/account/registration-fee/reconcile')
def reconcile():
    user = get_user()
    if not user:
        return jsonify(error='Entra en tu cuenta.'), 401
    activate(user['id'])
    current_state = state(user)
    if not current_state['required']:
        return jsonify(current_state)
    if not current_state['payment_available']:
        return jsonify(current_state | {'error': 'La consulta del pago no está disponible. Tu estado se conserva.'}), 503
    with database() as conn:
        order = conn.execute('''SELECT * FROM registration_fee_orders
            WHERE member_id=? AND checkout_id IS NOT NULL
            ORDER BY created_at DESC,id DESC LIMIT 1''', (user['id'],)).fetchone()
    if not order:
        return jsonify(current_state | {'error': 'Todavía no hay un pago de alta iniciado en esta cuenta.'}), 409
    if not _rate_allowed('reconcile', limit=3, minutes=5):
        return jsonify(current_state | {'error': 'Espera unos minutos antes de volver a consultar Stripe.'}), 429
    try:
        obj = payments.stripe('GET', '/checkout/sessions/'+order['checkout_id'])
        if not isinstance(obj, dict):
            raise ValueError('Invalid Stripe checkout response')
        metadata = obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}
        if (obj.get('id') != order['checkout_id'] or metadata.get('registration_fee_id') != order['id']
                or metadata.get('member_id') != user['id'] or obj.get('client_reference_id') != user['id']):
            raise ValueError('Stripe returned a checkout for another order/account')
        kind = 'checkout.session.expired' if obj.get('status') == 'expired' else 'checkout.session.completed'
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT * FROM registration_fee_orders WHERE id=? AND member_id=?', (order['id'], user['id'])).fetchone()
            if not current or current['checkout_id'] != order['checkout_id']:
                raise ValueError('Registration checkout changed during reconciliation')
            event = {'livemode': obj.get('livemode'), 'type': kind, 'data': {'object': obj}}
            if not handle_event(conn, event):
                raise ValueError('Stripe did not identify the registration fee')
    except (payments.PaymentError, ValueError, TypeError) + INTEGRITY_ERRORS:
        return jsonify(state(user) | {'error': 'No se ha podido verificar el pago con Stripe. El alta no se ha confirmado.'}), 502
    return jsonify(state(user))


def _refresh_paid(conn, member_id):
    paid = conn.execute("SELECT paid_at FROM registration_fee_orders WHERE member_id=? AND state='paid' AND paid_at IS NOT NULL AND refunded_cents=0 ORDER BY paid_at DESC LIMIT 1", (member_id,)).fetchone()
    conn.execute('UPDATE registration_access SET paid_at=? WHERE member_id=?', (paid['paid_at'] if paid else None, member_id))


def handle_event(conn, event):
    """Caller has verified the platform signature, owns locking and event dedupe."""
    if not isinstance(event, dict) or event.get('livemode') is not True or event.get('account'):
        return False
    kind = event.get('type')
    is_checkout = kind in {'checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.expired'}
    if not is_checkout and kind not in {'charge.refunded', 'charge.dispute.created', 'charge.dispute.closed'}:
        return False
    data = event.get('data')
    obj = data.get('object') if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return False
    metadata = obj.get('metadata') if isinstance(obj.get('metadata'), dict) else {}
    ident = metadata.get('registration_fee_id')
    if ident is not None and (not isinstance(ident, str) or not re.fullmatch('[a-f0-9]{32}', ident)):
        raise ValueError('Invalid registration fee metadata')
    intent = obj.get('payment_intent')
    by_intent = conn.execute('SELECT * FROM registration_fee_orders WHERE payment_intent=?', (intent,)).fetchone() if isinstance(intent, str) else None
    order = conn.execute('SELECT * FROM registration_fee_orders WHERE id=?', (ident,)).fetchone() if ident else by_intent
    if not order:
        known_checkout = conn.execute('SELECT 1 FROM registration_fee_orders WHERE checkout_id=?', (obj.get('id'),)).fetchone() if is_checkout else None
        if by_intent or known_checkout:
            raise ValueError('Registration fee metadata mismatch')
        return False
    if by_intent and by_intent['id'] != order['id']:
        raise ValueError('Registration fee intent belongs to another account')
    if (obj.get('livemode') is not True or obj.get('currency') != 'eur'
            or order['currency'] != 'eur' or order['amount_cents'] != PRICE_CENTS):
        raise ValueError('Registration fee mode/currency mismatch')
    if metadata.get('member_id') is not None and metadata['member_id'] != order['member_id']:
        raise ValueError('Registration fee account mismatch')
    if is_checkout:
        if (ident != order['id'] or metadata.get('member_id') != order['member_id']
                or obj.get('client_reference_id') != order['member_id']
                or obj.get('id') != order['checkout_id'] or obj.get('mode') != 'payment'
                or type(obj.get('amount_total')) is not int or obj['amount_total'] != PRICE_CENTS):
            raise ValueError('Registration fee checkout mismatch')
        if kind == 'checkout.session.expired':
            if order['state'] in {'created', 'pending'} and not order['paid_at']:
                conn.execute("UPDATE registration_fee_orders SET state='expired' WHERE id=?", (order['id'],))
            return True
        if obj.get('payment_status') != 'paid':
            return True
    if not isinstance(intent, str) or not re.fullmatch('pi_[A-Za-z0-9]+', intent):
        raise ValueError('Invalid registration fee payment intent')
    if order['payment_intent'] and order['payment_intent'] != intent:
        raise ValueError('Registration fee payment intent mismatch')
    if is_checkout:
        reversal = conn.execute('SELECT 1 FROM stripe_reversals WHERE payment_intent=? AND account_id=?', (intent, '')).fetchone()
        refunded = max(order['refunded_cents'], PRICE_CENTS if reversal else 0)
        status = 'disputed' if order['state'] == 'disputed' else 'refunded' if refunded else 'paid'
        conn.execute('UPDATE registration_fee_orders SET payment_intent=?,paid_at=COALESCE(paid_at,?),state=?,refunded_cents=? WHERE id=?', (intent, stamp(now_utc()), status, refunded, order['id']))
    else:
        if type(obj.get('amount')) is not int or not 0 < obj['amount'] <= PRICE_CENTS:
            raise ValueError('Registration fee reversal mismatch')
        if kind == 'charge.refunded':
            refunded = obj.get('amount_refunded')
            if obj['amount'] != PRICE_CENTS or type(refunded) is not int or not 0 <= refunded <= PRICE_CENTS:
                raise ValueError('Registration fee refund mismatch')
            refunded = max(order['refunded_cents'], refunded)
            status = 'disputed' if order['state'] == 'disputed' else 'refunded' if refunded else order['state']
            conn.execute('UPDATE registration_fee_orders SET payment_intent=?,refunded_cents=?,state=? WHERE id=?', (intent, refunded, status, order['id']))
        else:
            conn.execute("UPDATE registration_fee_orders SET payment_intent=?,state='disputed' WHERE id=?", (intent, order['id']))
    _refresh_paid(conn, order['member_id'])
    return True


def install(app):
    app.register_blueprint(bp)
