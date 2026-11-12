"""Single-use email login codes and a private, durable access audit.

Codes are delivered only after the password and existing authenticator check.
The administrator's digest contains masked event metadata, never login codes.
"""
from __future__ import annotations

from datetime import timedelta
import hashlib
import hmac
import os
import re
import secrets

from flask import Blueprint, current_app, g, jsonify, request, session
from werkzeug.exceptions import RequestEntityTooLarge

from membership import database, get_user, now_utc, payload, require_admin, stamp
from storage import INTEGRITY_ERRORS

bp = Blueprint('login_security', __name__)
CODE_SECONDS = 600
RESEND_SECONDS = 60
MAX_CODE_ATTEMPTS = 5
RETENTION_DAYS = 90


def required():
    return os.getenv('OL_LOGIN_EMAIL_REQUIRED', '1').strip() == '1'


def mail_ready():
    # Resolve dynamically so provider configuration and isolated mail fixtures
    # use the same delivery function as account verification and recovery.
    import email_security
    return email_security.mail_ready()


def init_database():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS security_login_challenges (
          id TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
          email TEXT NOT NULL,session_version INTEGER NOT NULL,binding_hash TEXT NOT NULL,
          code_hash TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,
          last_sent_at TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,
          sends INTEGER NOT NULL DEFAULT 1,delivery_state TEXT NOT NULL,
          delivery_token TEXT NOT NULL,used_at TEXT,profile_email_present INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS security_challenges_member ON security_login_challenges(member_id,created_at);
        CREATE INDEX IF NOT EXISTS security_challenges_expiry ON security_login_challenges(expires_at);
        CREATE TABLE IF NOT EXISTS security_login_events (
          id TEXT PRIMARY KEY,member_id TEXT REFERENCES members(id) ON DELETE SET NULL,
          identifier TEXT NOT NULL,event TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,
          network_id TEXT NOT NULL,browser TEXT NOT NULL,mail_status TEXT NOT NULL DEFAULT 'pending',
          mail_attempted_at TEXT,mail_sent_at TEXT,mail_batch_id TEXT
        );
        CREATE INDEX IF NOT EXISTS security_events_created ON security_login_events(created_at,id);
        CREATE INDEX IF NOT EXISTS security_events_mail ON security_login_events(mail_status,created_at);
        CREATE TABLE IF NOT EXISTS security_login_mail_clock (
          id TEXT PRIMARY KEY,attempted_at TEXT,lease_until TEXT,lease_token TEXT
        );
        INSERT INTO security_login_mail_clock(id) VALUES('administrator') ON CONFLICT(id) DO NOTHING;
        ''')
        conn.execute('BEGIN IMMEDIATE')
        if current_app.config.get('MEMBERSHIP_DATABASE_URL'):
            names={row['column_name'] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='security_login_challenges'").fetchall()}
        else:
            names={row['name'] for row in conn.execute('PRAGMA table_info(security_login_challenges)').fetchall()}
        if 'profile_email_present' not in names:
            conn.execute('ALTER TABLE security_login_challenges ADD COLUMN profile_email_present INTEGER NOT NULL DEFAULT 0')


def _digest(value):
    key = str(current_app.secret_key).encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def _binding():
    value = session.get('login_email_binding')
    return hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else ''


def _code_hash(ident, binding, code):
    return _digest('email-code:' + ident + ':' + binding + ':' + code)


def masked_identity(value):
    value = str(value or '').strip().lower()[:254]
    if '@' in value:
        local, domain = value.rsplit('@', 1)
        if re.fullmatch(r'[a-z0-9.-]+', domain or ''):
            return (local[:2] or '*') + '***@' + domain
    if not value:
        return 'No indicado'
    return value[:2] + '***' + (value[-1:] if len(value) > 3 else '')


def subject(member_id=None, identifier=None):
    if member_id:
        g.login_security_member_id = member_id
    if identifier:
        g.login_security_identifier = masked_identity(identifier)


def validate_enrollment(member_id=None, supplied=None, existing_email=None):
    """Validate before account/invitation writes; never replace a stored email."""
    if not required():
        return None
    import email_security
    email = existing_email
    if member_id:
        with database() as conn:
            profile = conn.execute('SELECT email FROM member_profiles WHERE member_id=?', (member_id,)).fetchone()
            email = profile['email'] if profile and profile['email'] else email
    if not email:
        email = email_security.clean_email(supplied)
    if not email:
        raise ValueError('Indica un correo para recibir el código de acceso.')
    with database() as conn:
        owner = conn.execute('SELECT member_id FROM member_profiles WHERE email=?', (email,)).fetchone()
        if owner and owner['member_id'] != member_id:
            raise ValueError('Ese correo no está disponible para esta cuenta.')
    return email


def unavailable():
    return jsonify(error='No se pueden enviar códigos de acceso en este momento. Inténtalo más tarde o contacta con administración.', code='email_delivery_unavailable'), 503


def _challenge_response(row):
    return jsonify(ok=False, code='email_code_required', challenge_id=row['id'],
                   email_hint=masked_identity(row['email']), login_identifier=row.get('username',''), expires_in=CODE_SECONDS,
                   resend_after=RESEND_SECONDS, csrf=session.get('csrf')), 202


def establish(member_id, version):
    session.clear()
    session.update(member_id=member_id, session_version=version, csrf=secrets.token_urlsafe(32))
    session.permanent = True
    from registration_fee import activate
    activate(member_id)
    subject(member_id)
    return jsonify(ok=True, csrf=session['csrf'])


def begin(user, supplied_email=None, purpose='login'):
    """Return a challenge instead of a member session, or a fail-closed error."""
    subject(user['id'], user['username'])
    if not mail_ready():
        return unavailable()
    try:
        email = validate_enrollment(user['id'], supplied_email)
    except ValueError as exc:
        return jsonify(error=str(exc), code='verification_email_required'), 400
    ident, code = secrets.token_hex(16), f'{secrets.randbelow(1000000):06d}'
    instant = now_utc(); delivery_token = secrets.token_hex(16)
    # A new pre-authentication session has no member authority.
    old_challenge = session.get('pending_login_challenge')
    old_binding = _binding()
    session.clear()
    session.update(csrf=secrets.token_urlsafe(32), pending_login_challenge=ident,
                   login_email_binding=secrets.token_urlsafe(32))
    binding = _binding()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        fresh = conn.execute('SELECT session_version FROM members WHERE id=? AND NOT EXISTS(SELECT 1 FROM member_archives a WHERE a.member_id=members.id AND a.restored_at IS NULL) AND NOT EXISTS(SELECT 1 FROM account_blocks b WHERE b.member_id=members.id)', (user['id'],)).fetchone()
        if not fresh or fresh['session_version'] != user['session_version']:
            return jsonify(error='La cuenta ha cambiado. Inicia sesión de nuevo.', code='login_changed'), 401
        profile=conn.execute('SELECT email FROM member_profiles WHERE member_id=?',(user['id'],)).fetchone()
        had_email=bool(profile and profile['email'])
        if had_email and profile['email']!=email:
            return jsonify(error='El correo de la cuenta ha cambiado. Inicia sesión de nuevo.',code='login_changed'),409
        conn.execute('DELETE FROM security_login_challenges WHERE expires_at<?', (stamp(instant-timedelta(days=1)),))
        if old_challenge and old_binding:
            conn.execute('UPDATE security_login_challenges SET used_at=? WHERE id=? AND binding_hash=? AND used_at IS NULL', (stamp(instant), old_challenge, old_binding))
        recent = conn.execute('SELECT COUNT(*) AS n FROM security_login_challenges WHERE member_id=? AND created_at>?', (user['id'], stamp(instant-timedelta(minutes=15)))).fetchone()['n']
        if recent >= 8:
            return jsonify(error='Espera unos minutos antes de solicitar más códigos.', code='email_code_rate_limited'), 429
        conn.execute('''INSERT INTO security_login_challenges(id,member_id,email,session_version,binding_hash,code_hash,
            created_at,expires_at,last_sent_at,delivery_state,delivery_token,profile_email_present) VALUES(?,?,?,?,?,?,?,?,?,'sending',?,?)''',
                     (ident, user['id'], email, user['session_version'], binding, _code_hash(ident,binding,code),
                      stamp(instant), stamp(instant+timedelta(seconds=CODE_SECONDS)), stamp(instant), delivery_token, int(had_email)))
    sent = _deliver_code(email, code)
    with database() as conn:
        conn.execute("UPDATE security_login_challenges SET delivery_state=?,used_at=? WHERE id=? AND delivery_token=?",
                     ('sent' if sent else 'failed', None if sent else stamp(now_utc()), ident, delivery_token))
    if not sent:
        note = ' Tu cuenta está creada; entra con tu usuario y contraseña para pedir otro código.' if purpose in {'register','invite'} else ''
        return jsonify(error='No se pudo enviar el código.'+note, code='email_delivery_unavailable', account_created=purpose in {'register','invite'}, login_identifier=user['username'], csrf=session.get('csrf')), 503
    return _challenge_response({'id':ident,'email':email,'username':user['username']})


def _deliver_code(email, code):
    import email_security
    try:
        email_security.deliver_to(email, 'Tu código para entrar',
            'Tu código de acceso a electronicama es: '+code+'\n\nCaduca en 10 minutos y solo puede usarse una vez en el navegador que lo solicitó. No lo compartas.\nSi no has solicitado este acceso, ignora este correo y revisa la seguridad de tu cuenta.')
        return True
    except Exception:
        return False


def _bound(conn, data):
    ident = data.get('challenge_id')
    if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}', ident) or ident != session.get('pending_login_challenge'):
        return None
    row = conn.execute('''SELECT c.*,m.session_version AS current_version,m.username,
        p.email AS current_email FROM security_login_challenges c JOIN members m ON m.id=c.member_id
        LEFT JOIN member_profiles p ON p.member_id=m.id WHERE c.id=? AND NOT EXISTS(
          SELECT 1 FROM member_archives a WHERE a.member_id=m.id AND a.restored_at IS NULL) AND NOT EXISTS(SELECT 1 FROM account_blocks b WHERE b.member_id=m.id)''', (ident,)).fetchone()
    if not row:
        return None
    subject(row['member_id'], row['username'])
    if row['binding_hash'] != _binding() or row['used_at'] or row['expires_at'] <= stamp(now_utc()) or row['session_version'] != row['current_version'] or row['attempts'] >= MAX_CODE_ATTEMPTS:
        return None
    if row['profile_email_present'] and not row['current_email']:
        return None
    if row['current_email'] and row['current_email'] != row['email']:
        return None
    return row


@bp.get('/api/account/login-security')
def capabilities():
    return jsonify(email_code_required=required(), email_delivery_configured=bool(mail_ready()))


@bp.post('/api/account/login/verify')
def verify():
    data=payload(); code=data.get('code')
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');row=_bound(conn,data)
        if not row or row['delivery_state'] != 'sent':
            return jsonify(error='El código no es válido o ha caducado. Inicia sesión de nuevo.', code='email_code_invalid'),401
        valid = isinstance(code,str) and bool(re.fullmatch(r'\d{6}',code)) and hmac.compare_digest(row['code_hash'],_code_hash(row['id'],row['binding_hash'],code))
        attempts=row['attempts']+1
        if not valid:
            if attempts>=MAX_CODE_ATTEMPTS:g.login_security_result='email_code_exhausted'
            conn.execute('UPDATE security_login_challenges SET attempts=?,used_at=? WHERE id=?',
                         (attempts, stamp(now_utc()) if attempts>=MAX_CODE_ATTEMPTS else None,row['id']))
            return jsonify(error='El código no es válido o ha caducado.',code='email_code_invalid'),401
        try:
            conn.execute('INSERT INTO member_profiles(member_id,email,email_verified,updated_at) VALUES(?,?,1,?) ON CONFLICT(member_id) DO UPDATE SET email=excluded.email,email_verified=1,updated_at=excluded.updated_at', (row['member_id'],row['email'],stamp(now_utc())))
        except INTEGRITY_ERRORS:
            return jsonify(error='No se puede confirmar ese correo para esta cuenta.',code='email_code_invalid'),409
        if not row['profile_email_present']:
            from account_reports import queue_account
            queue_account(conn,row['member_id'],event='email_added')
        conn.execute('UPDATE security_login_challenges SET used_at=?,attempts=? WHERE id=?',(stamp(now_utc()),attempts,row['id']))
        member_id,version=row['member_id'],row['current_version']
    return establish(member_id,version)


@bp.post('/api/account/login/resend')
def resend():
    if not mail_ready():return unavailable()
    data=payload(); code=f'{secrets.randbelow(1000000):06d}'; token=secrets.token_hex(16)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');row=_bound(conn,data)
        if not row:return jsonify(error='La solicitud ha caducado. Inicia sesión de nuevo.',code='email_code_invalid'),401
        if row['sends']>=4 or row['last_sent_at']>stamp(now_utc()-timedelta(seconds=RESEND_SECONDS)):
            return jsonify(error='Espera un minuto antes de solicitar otro código.',code='email_code_rate_limited',resend_after=RESEND_SECONDS),429
        conn.execute("UPDATE security_login_challenges SET code_hash=?,delivery_state='sending',delivery_token=?,last_sent_at=?,expires_at=?,sends=sends+1 WHERE id=?",
                     (_code_hash(row['id'],row['binding_hash'],code),token,stamp(now_utc()),stamp(now_utc()+timedelta(seconds=CODE_SECONDS)),row['id']))
        ident,email,username=row['id'],row['email'],row['username']
    sent=_deliver_code(email,code)
    with database() as conn:conn.execute('UPDATE security_login_challenges SET delivery_state=? WHERE id=? AND delivery_token=?',('sent' if sent else 'failed',ident,token))
    if not sent:return unavailable()
    return _challenge_response({'id':ident,'email':email,'username':username})


@bp.post('/api/account/login/cancel')
def cancel():
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE security_login_challenges SET used_at=? WHERE id=? AND binding_hash=? AND used_at IS NULL', (stamp(now_utc()),session.get('pending_login_challenge',''),_binding()))
    session.pop('pending_login_challenge',None);session.pop('login_email_binding',None)
    return jsonify(ok=True)


def audit(event, result, member_id=None, identifier=None):
    instant=now_utc();ident=secrets.token_hex(16)
    ua=request.user_agent.string.lower()
    browser='automated' if any(word in ua for word in ['bot','crawler','spider']) else 'mobile' if any(word in ua for word in ['mobile','android','iphone']) else 'browser'
    network=_digest('login-network:'+instant.date().isoformat()+':'+str(request.remote_addr or 'unknown'))
    with database() as conn:
        conn.execute('DELETE FROM security_login_events WHERE created_at<?',(stamp(instant-timedelta(days=RETENTION_DAYS)),))
        if member_id and not conn.execute('SELECT 1 FROM members WHERE id=?',(member_id,)).fetchone():member_id=None
        conn.execute('INSERT INTO security_login_events(id,member_id,identifier,event,result,created_at,network_id,browser,mail_status) VALUES(?,?,?,?,?,?,?,?,?)',
                     (ident,member_id,identifier or 'No indicado',event,result,stamp(instant),network,browser,'pending'))
    return ident


def flush_audit_mail(force=False):
    import notifications
    if not notifications.mail_ready():return {'sent':0,'failed':0}
    instant=now_utc();token=secrets.token_hex(16)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        clock=conn.execute("SELECT * FROM security_login_mail_clock WHERE id='administrator'").fetchone()
        if clock['lease_until'] and clock['lease_until']>stamp(instant):return {'sent':0,'failed':0}
        if not force and clock['attempted_at'] and clock['attempted_at']>stamp(instant-timedelta(seconds=60)):return {'sent':0,'failed':0}
        conn.execute("UPDATE security_login_events SET mail_status='failed',mail_batch_id=NULL WHERE mail_status='sending' AND mail_attempted_at<?",(stamp(instant-timedelta(minutes=5)),))
        rows=conn.execute("SELECT id,identifier,event,result,created_at FROM security_login_events WHERE mail_status IN ('pending','failed') ORDER BY created_at,id LIMIT 100").fetchall()
        if not rows:return {'sent':0,'failed':0}
        conn.execute("UPDATE security_login_mail_clock SET attempted_at=?,lease_until=?,lease_token=? WHERE id='administrator'",(stamp(instant),stamp(instant+timedelta(minutes=5)),token))
        for row in rows:conn.execute("UPDATE security_login_events SET mail_status='sending',mail_batch_id=?,mail_attempted_at=? WHERE id=?",(token,stamp(instant),row['id']))
    body='Registro privado de accesos de electronicama. Cada línea es un evento; los identificadores están ocultos parcialmente.\n\n'
    body+='\n'.join(row['created_at']+' · '+row['identifier']+' · '+row['event']+' · '+row['result'] for row in rows)
    body+='\n\nNo se incluyen contraseñas, códigos, enlaces de acceso ni direcciones IP. Consulta el panel privado para revisar el historial.'
    try:notifications.deliver('Auditoría de accesos · '+str(len(rows))+' eventos',body);sent=True
    except Exception:sent=False
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE security_login_events SET mail_status=?,mail_sent_at=?,mail_batch_id=NULL WHERE mail_batch_id=?',('sent' if sent else 'failed',stamp(now_utc()) if sent else None,token))
        conn.execute("UPDATE security_login_mail_clock SET lease_until=NULL,lease_token=NULL WHERE id='administrator' AND lease_token=?",(token,))
    return {'sent':len(rows) if sent else 0,'failed':0 if sent else len(rows)}


@bp.get('/api/admin/login-audit')
@require_admin
def listing():
    try:page=max(1,int(request.args.get('page','1')))
    except (ValueError,TypeError):return jsonify(error='Página no válida.'),400
    q=request.args.get('q','').strip()[:100]
    where=' WHERE (identifier LIKE ? OR event LIKE ? OR result LIKE ?)' if q else ''
    params=['%'+q+'%']*3 if q else []
    with database() as conn:
        total=conn.execute('SELECT COUNT(*) AS n FROM security_login_events'+where,params).fetchone()['n'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT id,member_id,identifier,event,result,created_at,mail_status,mail_sent_at FROM security_login_events'+where+' ORDER BY created_at DESC,id DESC LIMIT 25 OFFSET ?',params+[(page-1)*25]).fetchall()
        pending=conn.execute("SELECT COUNT(*) AS n FROM security_login_events WHERE mail_status!='sent'").fetchone()['n']
    return jsonify(events=[dict(row) for row in rows],page=page,pages=pages,total=total,pending_email=pending,retention_days=RETENTION_DAYS,email_code_required=required(),email_delivery_configured=bool(mail_ready()))


@bp.post('/api/admin/login-audit/retry-email')
@require_admin
def retry_mail():
    if not mail_ready():return unavailable()
    from membership import allow_attempt
    if not allow_attempt('login-audit-retry',6):return jsonify(error='Espera unos minutos antes de reintentar los avisos.'),429
    result=flush_audit_mail(force=True)
    with database() as conn:pending=conn.execute("SELECT COUNT(*) AS n FROM security_login_events WHERE mail_status!='sent'").fetchone()['n']
    return jsonify(ok=True,**result,pending=pending,email_delivery_configured=bool(mail_ready()))


SECURITY_ROUTES={
 '/api/account/login':'login_attempt','/api/account/login/verify':'email_code_verification',
 '/api/account/login/resend':'email_code_resend','/api/account/login/cancel':'email_code_cancel',
 '/api/account/register':'registration','/api/account/accept-invite':'invitation_access',
 '/api/account/email/confirm':'email_confirmation','/api/account/email/resend':'email_confirmation_resend',
 '/api/account/password/request':'password_recovery_request','/api/account/password/reset':'password_reset',
 '/api/account/profile':'profile_update','/api/account/logout':'logout'
}


def after_security_request(response):
    event=SECURITY_ROUTES.get(request.path)
    if request.method!='POST' or not event:return response
    data=response.get_json(silent=True)
    code=data.get('code') if isinstance(data,dict) else None
    code=getattr(g,'login_security_result',None) or code
    result=code if isinstance(code,str) and re.fullmatch('[a-z0-9_]{1,60}',code) else 'success' if response.status_code<300 else 'rate_limited' if response.status_code==429 else 'denied'
    member_id=getattr(g,'login_security_member_id',None)
    identifier=getattr(g,'login_security_identifier',None)
    if not identifier:
        try:data=payload()
        except RequestEntityTooLarge:data={}
        identifier=masked_identity(data.get('username') or data.get('email'))
    if not member_id and event in {'profile_update','logout','email_confirmation_resend'}:
        user=get_user();member_id=user['id'] if user else None
    audit(event,result,member_id,identifier)
    enabled=os.getenv('OL_LOGIN_AUDIT_EMAILS','1' if required() else '0')=='1'
    if enabled:
        force=(result=='success' and event in {'email_code_verification','password_reset','email_confirmation'}) or result=='email_code_exhausted'
        # Administrator mail failures stay queued and never grant access or
        # turn a successfully verified login into an authentication bypass.
        try:flush_audit_mail(force=force)
        except Exception:pass
    return response


def install(app):
    if bp.name not in app.blueprints:
        app.register_blueprint(bp)
        app.after_request(after_security_request)
