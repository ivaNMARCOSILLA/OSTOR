"""Private account summaries with durable delivery and no authentication secrets."""
import json
import os
import re
import secrets
from datetime import timedelta

from flask import Blueprint, current_app, g, has_request_context, jsonify, request, session

import notifications
from membership import allow_attempt, database, get_user, now_utc, require_admin, stamp


bp = Blueprint('account_reports', __name__)
INITIAL_REPORT = 'existing-accounts-v1'
BATCH_SIZE = 100


def init_database():
    """Create storage only; account snapshots and delivery require a real request."""
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS account_report_queue (
          event_key TEXT PRIMARY KEY,title TEXT NOT NULL,body TEXT NOT NULL,
          created_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0,last_attempt TEXT,sent_at TEXT,lease_token TEXT
        );CREATE INDEX IF NOT EXISTS account_reports_pending ON account_report_queue(status,created_at);
        CREATE TABLE IF NOT EXISTS account_report_members (
          member_id TEXT NOT NULL,event TEXT NOT NULL,event_key TEXT NOT NULL,
          PRIMARY KEY(member_id,event)
        );CREATE TABLE IF NOT EXISTS account_report_batches (
          id TEXT PRIMARY KEY,created_at TEXT NOT NULL,total_accounts INTEGER NOT NULL,batches INTEGER NOT NULL
        );''')


def _summary(conn, member_id):
    # Explicit selection is intentional: never load passwords, hashes or tokens.
    row = conn.execute('''SELECT m.id,m.username,m.role,m.created_at,m.access_until,
        p.email,p.email_verified,p.nickname,n.legal_name FROM members m
        LEFT JOIN member_profiles p ON p.member_id=m.id
        LEFT JOIN member_legal_names n ON n.member_id=m.id WHERE m.id=?''', (member_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result['alta_1_eur'] = {'estado': 'sin_registro', 'importe_centimos': 100}
    if notifications._table_exists(conn, 'registration_access'):
        access = conn.execute('SELECT origin,exempt_reason,due_at,paid_at FROM registration_access WHERE member_id=?', (member_id,)).fetchone()
        from registration_fee import staff_exemption
        reason = staff_exemption(conn, member_id) or (access['exempt_reason'] if access else None)
        result['alta_1_eur'] = {
            'estado': 'pagada' if access and access['paid_at'] else 'exenta' if reason else 'pendiente',
            'importe_centimos': 100, 'origen': access['origin'] if access else None,
            'exencion': reason, 'vence': access['due_at'] if access else None,
            'pagada_el': access['paid_at'] if access else None,
        }
    annual = conn.execute('''SELECT amount_cents,starts_at,ends_at,verified_at FROM payments
        WHERE member_id=? AND plan='annual' ORDER BY verified_at DESC,id DESC LIMIT 1''', (member_id,)).fetchone()
    result['ultimo_pago_anual'] = dict(annual) if annual else None
    return result


def _insert(conn, key, title, accounts):
    body = ('Resumen privado de cuentas de electronicama. Datos registrados en el momento de preparar el informe.\n'
            'No incluye contraseñas, hashes, códigos ni tokens de acceso.\n\n'
            + json.dumps(accounts, ensure_ascii=False, indent=2))
    return conn.execute('''INSERT INTO account_report_queue(event_key,title,body,created_at)
        VALUES(?,?,?,?) ON CONFLICT(event_key) DO NOTHING''', (key, title, body, stamp(now_utc()))).rowcount


def queue_initial(conn):
    """Snapshot existing IDs once. Caller holds BEGIN IMMEDIATE; no mail is sent."""
    if conn.execute('SELECT 1 FROM account_report_batches WHERE id=?', (INITIAL_REPORT,)).fetchone():
        return 0
    rows = conn.execute("SELECT m.id FROM members m WHERE NOT EXISTS(SELECT 1 FROM account_report_members r WHERE r.member_id=m.id AND r.event='registration') ORDER BY m.created_at,m.id").fetchall()
    batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
    queued = 0
    for index in range(batches):
        part = rows[index * BATCH_SIZE:(index + 1) * BATCH_SIZE]
        key = INITIAL_REPORT + ':' + str(index + 1)
        queued += _insert(conn, key, 'Resumen de cuentas existentes (' + str(index + 1) + '/' + str(batches) + ')',
                          [_summary(conn, row['id']) for row in part])
        for row in part:
            conn.execute('''INSERT INTO account_report_members(member_id,event,event_key) VALUES(?,?,?)
                ON CONFLICT(member_id,event) DO NOTHING''', (row['id'], INITIAL_REPORT, key))
    conn.execute('INSERT INTO account_report_batches(id,created_at,total_accounts,batches) VALUES(?,?,?,?)',
                 (INITIAL_REPORT, stamp(now_utc()), len(rows), batches))
    return queued


def queue_account(conn, member_id, event='registration'):
    """Queue an allowlisted snapshot once per account ID and server-side event."""
    if not isinstance(event, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', event):
        raise ValueError('Tipo de informe no válido.')
    if conn.execute('SELECT 1 FROM account_report_members WHERE member_id=? AND event=?', (member_id, event)).fetchone():
        return False
    summary = _summary(conn, member_id)
    if not summary:
        return False
    key = 'account:' + event + ':' + member_id
    inserted = _insert(conn, key, 'Datos de nueva cuenta · ' + event, [summary])
    conn.execute('''INSERT INTO account_report_members(member_id,event,event_key) VALUES(?,?,?)
        ON CONFLICT(member_id,event) DO NOTHING''', (member_id, event, key))
    if inserted and has_request_context():
        g.account_reports_queued = True
    return bool(inserted)


def status():
    with database() as conn:
        counts = {row['status']: row['n'] for row in conn.execute('SELECT status,COUNT(*) AS n FROM account_report_queue GROUP BY status').fetchall()}
        initial = conn.execute('SELECT total_accounts,batches FROM account_report_batches WHERE id=?', (INITIAL_REPORT,)).fetchone()
    return {'email_ready': notifications.mail_ready(), 'total': sum(counts.values()),
            'queued': counts.get('pending', 0), 'pending': sum(counts.get(key, 0) for key in ('pending', 'failed', 'sending')),
            'sent': counts.get('sent', 0), 'failed': counts.get('failed', 0), 'sending': counts.get('sending', 0),
            'initial_queued': bool(initial), 'initial_accounts': initial['total_accounts'] if initial else 0,
            'initial_batches': initial['batches'] if initial else 0}


def flush_pending(limit=2, retry_failed=False):
    """Deliver at most two messages outside transactions; provider failure stays queued."""
    result = {'email_ready': notifications.mail_ready(), 'attempted': 0, 'sent': 0, 'failed': 0}
    if not result['email_ready']:
        return result | {'pending': status()['pending']}
    limit = max(0, min(2, int(limit)))
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        instant = now_utc()
        conn.execute("UPDATE account_report_queue SET status='failed',lease_token=NULL WHERE status='sending' AND last_attempt<?",
                     (stamp(instant - timedelta(minutes=10)),))
        cutoff = stamp(instant if retry_failed else instant - timedelta(minutes=1))
        rows = conn.execute('''SELECT event_key FROM account_report_queue WHERE status='pending'
            OR (status='failed' AND last_attempt<=?) ORDER BY created_at,event_key LIMIT ?''', (cutoff, limit)).fetchall()
    for row in rows:
        token = secrets.token_hex(16)
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            claimed = conn.execute('''UPDATE account_report_queue SET status='sending',attempts=attempts+1,
                last_attempt=?,lease_token=? WHERE event_key=? AND (status='pending' OR (status='failed' AND last_attempt<=?))''',
                (stamp(now_utc()), token, row['event_key'], cutoff)).rowcount
            message = conn.execute('SELECT title,body FROM account_report_queue WHERE event_key=? AND lease_token=?', (row['event_key'], token)).fetchone() if claimed else None
        if not message:
            continue
        result['attempted'] += 1
        try:
            # Existing wrapper pins the destination to notifications.RECIPIENT.
            notifications.deliver(message['title'], message['body'])
        except Exception:
            with database() as conn:
                conn.execute("UPDATE account_report_queue SET status='failed',lease_token=NULL WHERE event_key=? AND lease_token=?", (row['event_key'], token))
            result['failed'] += 1
        else:
            with database() as conn:
                # Keep delivery/deduplication metadata, discard the delivered PII copy.
                conn.execute("UPDATE account_report_queue SET status='sent',sent_at=?,body='',lease_token=NULL WHERE event_key=? AND lease_token=?", (stamp(now_utc()), row['event_key'], token))
            result['sent'] += 1
    return result | {'pending': status()['pending']}


@bp.get('/api/admin/account-reports')
@require_admin
def report_status():
    return jsonify(status())


@bp.post('/api/admin/account-reports/send')
@require_admin
def send_reports():
    from membership import verify_csrf
    denied = verify_csrf()
    if denied:
        return denied
    if not allow_attempt('account-reports-send', 4):
        return jsonify(error='Espera unos minutos antes de volver a enviar los informes.'), 429
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        queued = queue_initial(conn)
    result = flush_pending(retry_failed=True)
    return jsonify(result | {'queued': queued, 'initial_queued': True})


def after_request(response):
    if os.getenv('OL_ACCOUNT_REPORT_EMAILS','1')!='1':return response
    if request.path.startswith('/api/admin/account-reports') or response.status_code >= 400:
        return response
    queued_here=getattr(g,'account_reports_queued',False)
    admin_path=request.path.startswith('/api/admin/') or request.path in {'/','/account','/api/account/me'}
    if not queued_here and (not admin_path or not session.get('member_id')):return response
    try:
        user = get_user() if admin_path and session.get('member_id') else None
        admin_request = bool(user and user['role']=='admin' and admin_path)
        if admin_request:
            with database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                queue_initial(conn)
        if admin_request or queued_here:
            flush_pending()
    except Exception:
        current_app.logger.warning('Account reports remain queued; processing could not complete')
    return response


def install(app):
    if bp.name not in app.blueprints:
        app.register_blueprint(bp)
        app.after_request(after_request)
