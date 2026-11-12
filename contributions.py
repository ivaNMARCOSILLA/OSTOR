"""Voluntary one-time platform contributions, confirmed only by signed Stripe events."""
from datetime import datetime, timedelta
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlparse

from flask import Blueprint, current_app, jsonify, request, session

import payments
from membership import database, get_user, now_utc, payload, require_admin, stamp
from storage import INTEGRITY_ERRORS


bp = Blueprint('contributions', __name__)
MIN_AMOUNT = 100
MAX_AMOUNT = 50000
RATE_LIMIT = 6


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS contribution_payments (
          id TEXT PRIMARY KEY,member_id TEXT REFERENCES members(id) ON DELETE SET NULL,
          amount_cents INTEGER NOT NULL CHECK(amount_cents>=100 AND amount_cents<=50000),
          currency TEXT NOT NULL,created_at TEXT NOT NULL,checkout_id TEXT UNIQUE,
          payment_intent TEXT UNIQUE,paid_at TEXT,state TEXT NOT NULL,
          refunded_cents INTEGER NOT NULL DEFAULT 0 CHECK(refunded_cents>=0 AND refunded_cents<=amount_cents)
        );CREATE INDEX IF NOT EXISTS contribution_payment_state ON contribution_payments(state,created_at);''')


def available():
    return payments.provider() == 'stripe' and bool(payments.ready())


def rate_allowed():
    # Ignore caller-supplied usernames/emails: they must not create new buckets.
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode()
    identity = 'platform-contribution:' + str(request.remote_addr or 'unknown')
    bucket = hmac.new(key, identity.encode(), hashlib.sha256).hexdigest()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        cutoff = stamp(now_utc()-timedelta(minutes=15))
        conn.execute('DELETE FROM login_attempts WHERE attempted_at<?', (cutoff,))
        count = conn.execute('SELECT COUNT(*) AS n FROM login_attempts WHERE bucket=? AND attempted_at>=?', (bucket, cutoff)).fetchone()['n']
        if count >= RATE_LIMIT:
            return False
        conn.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)', (bucket, stamp(now_utc())))
    return True


@bp.get('/api/contributions/config')
def configuration():
    return jsonify(available=available(), currency='eur', min_amount_cents=MIN_AMOUNT,
                   max_amount_cents=MAX_AMOUNT, presets=[300, 500, 1000],
                   one_time=True, grants_access=False)


def checkout_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return (parsed.scheme == 'https' and parsed.netloc == 'checkout.stripe.com'
            and not parsed.username and not parsed.password and parsed.path.startswith('/'))


@bp.post('/api/contributions/checkout')
def checkout():
    data = payload()
    amount = data.get('amount_cents')
    if type(amount) is not int or not MIN_AMOUNT <= amount <= MAX_AMOUNT or data.get('currency', 'eur') != 'eur':
        return jsonify(error='Elige una aportación de entre 1 y 500 €.'), 400
    if data.get('contributions_terms') is not True:
        return jsonify(error='Confirma que la aportación es voluntaria, única y no compra acceso ni insignias.'), 400
    if not available():
        return jsonify(error='Las aportaciones todavía no están disponibles.'), 503
    if not rate_allowed():
        return jsonify(error='Espera unos minutos antes de iniciar otra aportación.'), 429
    user = get_user()
    member_id = user['id'] if user else None
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = session.get('platform_contribution_attempt')
        row = conn.execute('SELECT * FROM contribution_payments WHERE id=?', (previous,)).fetchone() if isinstance(previous, str) else None
        recent = stamp(now_utc()-timedelta(minutes=30))
        if not (row and row['amount_cents'] == amount and row['member_id'] == member_id
                and row['state'] in {'created', 'pending'} and row['created_at'] > recent):
            ident = secrets.token_hex(16)
            conn.execute("INSERT INTO contribution_payments(id,member_id,amount_cents,currency,created_at,state) VALUES(?,?,?,'eur',?,'created')", (ident, member_id, amount, stamp(now_utc())))
            row = conn.execute('SELECT * FROM contribution_payments WHERE id=?', (ident,)).fetchone()
        ident, created_at = row['id'], row['created_at']
    session['platform_contribution_attempt'] = ident
    details = {
        'mode': 'payment', 'managed_payments[enabled]': 'false',
        'success_url': payments.ORIGIN+'/?contribution=processing#contributions',
        'cancel_url': payments.ORIGIN+'/?contribution=cancelled#contributions',
        'client_reference_id': ident, 'metadata[contribution_id]': ident,
        'payment_intent_data[metadata][contribution_id]': ident,
        'line_items[0][quantity]': '1', 'line_items[0][price_data][currency]': 'eur',
        'line_items[0][price_data][unit_amount]': str(amount),
        'line_items[0][price_data][product_data][name]': 'Aportación voluntaria a electronicama',
        'custom_text[submit][message]': 'Aportación única y voluntaria. No compra Ol Live, insignias ni otros servicios.',
        'payment_method_types[0]': 'card',
        'expires_at': str(int(datetime.fromisoformat(created_at).timestamp())+1860),
    }
    try:
        result = payments.stripe('POST', '/checkout/sessions', details, idempotency='contribution-'+ident)
        checkout_id = result.get('id')
        if (not isinstance(checkout_id, str) or not checkout_id.startswith('cs_live_')
                or result.get('livemode') is not True or not checkout_url(result.get('url'))):
            raise payments.PaymentError('Stripe no devolvió una sesión válida de aportación.')
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = conn.execute('SELECT * FROM contribution_payments WHERE id=?', (ident,)).fetchone()
            if not current or current['state'] not in {'created', 'pending'} or current['paid_at']:
                return jsonify(error='La aportación anterior ya ha sido procesada. Actualiza su estado antes de continuar.'), 409
            if current['checkout_id'] and current['checkout_id'] != checkout_id:
                raise ValueError('Checkout does not match the existing attempt')
            conn.execute("UPDATE contribution_payments SET checkout_id=?,state='pending' WHERE id=?", (checkout_id, ident))
        return jsonify(url=result['url'], id=ident, grants_access=False)
    except (payments.PaymentError, ValueError) + INTEGRITY_ERRORS:
        # Preserve the attempt/idempotency key when Stripe's result is ambiguous.
        return jsonify(error='No se pudo abrir el pago. No se ha confirmado ninguna aportación; puedes reintentar el mismo importe.'), 502


def _metadata_id(obj):
    metadata = obj.get('metadata')
    value = metadata.get('contribution_id') if isinstance(metadata, dict) else None
    if value is not None and (not isinstance(value, str) or not re.fullmatch('[a-f0-9]{32}', value)):
        raise ValueError('Invalid contribution metadata')
    return value


def _integer(value):
    return type(value) is int


def handle_event(conn, event):
    """Consume only verified live platform events; caller owns the transaction.

    The existing payments webhook verifies the signature and deduplicates event
    IDs. This helper additionally binds the actual object to its contribution.
    It never grants account access, founder ownership or other services.
    """
    if not isinstance(event, dict) or event.get('livemode') is not True or event.get('account'):
        return False
    kind = event.get('type')
    checkout_event = kind in {'checkout.session.completed', 'checkout.session.async_payment_succeeded', 'checkout.session.expired'}
    reversal_event = kind in {'charge.refunded', 'charge.dispute.created', 'charge.dispute.closed'}
    if not checkout_event and not reversal_event:
        return False
    data = event.get('data')
    obj = data.get('object') if isinstance(data, dict) else None
    if not isinstance(obj, dict):
        return False
    ident = _metadata_id(obj)
    intent = obj.get('payment_intent')
    by_intent = conn.execute('SELECT * FROM contribution_payments WHERE payment_intent=?', (intent,)).fetchone() if isinstance(intent, str) else None
    row = conn.execute('SELECT * FROM contribution_payments WHERE id=?', (ident,)).fetchone() if ident else by_intent
    if not row:
        known_checkout = conn.execute('SELECT 1 FROM contribution_payments WHERE checkout_id=?', (obj.get('id'),)).fetchone() if checkout_event else None
        if by_intent or known_checkout:
            raise ValueError('Contribution metadata mismatch')
        return False
    if by_intent and by_intent['id'] != row['id']:
        raise ValueError('Payment intent belongs to another contribution')
    if obj.get('livemode') is not True or obj.get('currency') != 'eur':
        raise ValueError('Contribution mode/currency mismatch')
    if checkout_event:
        if (ident != row['id'] or obj.get('id') != row['checkout_id']
                or obj.get('mode') != 'payment' or not _integer(obj.get('amount_total'))
                or obj['amount_total'] != row['amount_cents']):
            raise ValueError('Contribution checkout mismatch')
        if kind == 'checkout.session.expired':
            if row['state'] in {'created', 'pending'} and not row['paid_at'] and not row['refunded_cents']:
                conn.execute("UPDATE contribution_payments SET state='expired' WHERE id=?", (row['id'],))
            return True
        if obj.get('payment_status') != 'paid':
            return True
    if not isinstance(intent, str) or not re.fullmatch(r'pi_[A-Za-z0-9]+', intent):
        raise ValueError('Invalid contribution payment intent')
    if row['payment_intent'] and row['payment_intent'] != intent:
        raise ValueError('Contribution payment intent mismatch')
    if checkout_event:
        # A full reversal that arrived before Checkout may have been recorded
        # by the platform webhook before its metadata could identify this row.
        prior_reversal = conn.execute('SELECT 1 FROM stripe_reversals WHERE payment_intent=? AND account_id=?', (intent, '')).fetchone()
        refunded = max(row['refunded_cents'], row['amount_cents'] if prior_reversal else 0)
        state = 'disputed' if row['state'] == 'disputed' else 'refunded' if refunded else 'paid'
        conn.execute('UPDATE contribution_payments SET payment_intent=?,paid_at=COALESCE(paid_at,?),state=?,refunded_cents=? WHERE id=?', (intent, stamp(now_utc()), state, refunded, row['id']))
        return True
    amount = obj.get('amount')
    if not _integer(amount) or amount <= 0 or amount > row['amount_cents']:
        raise ValueError('Contribution reversal amount mismatch')
    if kind == 'charge.refunded':
        refunded = obj.get('amount_refunded')
        if amount != row['amount_cents'] or not _integer(refunded) or not 0 <= refunded <= amount:
            raise ValueError('Contribution refund mismatch')
        refunded = max(row['refunded_cents'], refunded)
        state = 'disputed' if row['state'] == 'disputed' else 'refunded' if refunded else row['state']
        conn.execute('UPDATE contribution_payments SET payment_intent=?,refunded_cents=?,state=? WHERE id=?', (intent, refunded, state, row['id']))
    else:
        # Disputes remain held for Stripe/operator review, even on late completion
        # or a won-dispute event. No automatic payment/access restoration occurs.
        conn.execute("UPDATE contribution_payments SET payment_intent=?,state='disputed' WHERE id=?", (intent, row['id']))
    return True


@bp.get('/api/admin/contributions')
@require_admin
def admin_summary():
    with database() as conn:
        summary = conn.execute('''SELECT
            COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN amount_cents ELSE 0 END),0) AS gross_cents,
            COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN refunded_cents ELSE 0 END),0) AS refunded_cents,
            COALESCE(SUM(CASE WHEN paid_at IS NOT NULL AND state='disputed' THEN amount_cents-refunded_cents ELSE 0 END),0) AS disputed_cents,
            COALESCE(SUM(CASE WHEN paid_at IS NOT NULL AND state!='disputed' AND refunded_cents<amount_cents THEN 1 ELSE 0 END),0) AS confirmed_count,
            COALESCE(SUM(CASE WHEN state IN ('created','pending') THEN 1 ELSE 0 END),0) AS pending_count,
            COALESCE(SUM(CASE WHEN state='disputed' THEN 1 ELSE 0 END),0) AS disputed_count
            FROM contribution_payments''').fetchone()
        summary = dict(summary)
        summary['net_cents'] = summary['gross_cents']-summary['refunded_cents']-summary['disputed_cents']
        rows = conn.execute('SELECT id,amount_cents,currency,created_at,paid_at,state,refunded_cents FROM contribution_payments ORDER BY created_at DESC,id DESC LIMIT 25').fetchall()
    response = jsonify(summary=summary, contributions=[dict(row) for row in rows])
    response.headers['Cache-Control'] = 'no-store'
    return response


def install(app):
    app.register_blueprint(bp)
