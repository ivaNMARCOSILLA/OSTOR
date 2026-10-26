"""Server-side membership, manual PayPal verification and multi-device sessions."""
from __future__ import annotations

import calendar
import tempfile
import hashlib
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path

from flask import Blueprint, current_app, g, jsonify, redirect, request, session
from storage import open_database, INTEGRITY_ERRORS
from moderation import validate_public_text
from notifications import notify

from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('membership', __name__)
UTC = timezone.utc
PLANS = {'lifetime': {'cents': 2500}}


def now_utc():
    return datetime.now(UTC).replace(microsecond=0)


def stamp(value):
    return value.astimezone(UTC).isoformat()


def end_of_plan(start, plan):
    if plan == 'lifetime':return datetime.max.replace(tzinfo=UTC,microsecond=0)
    if plan == 'welcome':
        return start + timedelta(days=14)
    month = start.month % 12 + 1
    year = start.year + (start.month == 12)
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


@contextmanager
def database():
    with open_database(current_app.config) as connection:
        yield connection


def init_database():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS live_launch (
          id TEXT PRIMARY KEY,started_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS promotion_metrics (
          day TEXT NOT NULL,event TEXT NOT NULL,amount INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(day,event)
        );
        CREATE TABLE IF NOT EXISTS human_challenges (
          id TEXT PRIMARY KEY,answer_hash TEXT NOT NULL,session_hash TEXT NOT NULL,expires_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS human_challenges_expiry ON human_challenges(expires_at);
        CREATE TABLE IF NOT EXISTS online_presence (
          visitor_id TEXT PRIMARY KEY,member_id TEXT,seen_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS online_presence_time ON online_presence(seen_at);
        CREATE TABLE IF NOT EXISTS members (
          id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          password_hash TEXT, role TEXT NOT NULL DEFAULT 'member',
          created_at TEXT NOT NULL, access_until TEXT,
          welcome_used INTEGER NOT NULL DEFAULT 0, session_version INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS member_two_factor (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,nonce TEXT,enabled_at TEXT,key_id TEXT,
          last_counter INTEGER NOT NULL DEFAULT -1,pending_nonce TEXT,pending_until TEXT
        );
        CREATE TABLE IF NOT EXISTS two_factor_recovery (
          member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,code_hash TEXT NOT NULL,used_at TEXT,
          PRIMARY KEY(member_id,code_hash)
        );
        CREATE TABLE IF NOT EXISTS pricing_moderators (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
          assigned_by TEXT NOT NULL REFERENCES members(id),assigned_at TEXT NOT NULL,revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS live_entitlements (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,trial_started_at TEXT,trial_until TEXT,paid_at TEXT,revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS founder_activity (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,total_seconds INTEGER NOT NULL DEFAULT 0,
          session_seconds INTEGER NOT NULL DEFAULT 0,last_verified_at TEXT,qualification_until TEXT,first_completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS creator_daily_activity (
          member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,day TEXT NOT NULL,seconds INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(member_id,day)
        );
        CREATE TABLE IF NOT EXISTS live_founders (
          member_id TEXT PRIMARY KEY REFERENCES members(id),number INTEGER NOT NULL UNIQUE CHECK(number>=1 AND number<=100),
          claimed_at TEXT NOT NULL,revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS founder_slot_history (
          id TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,number INTEGER NOT NULL,
          claimed_at TEXT NOT NULL,trial_until TEXT NOT NULL,released_at TEXT NOT NULL,reason TEXT NOT NULL,signature_json TEXT
        );
        CREATE INDEX IF NOT EXISTS founder_slot_history_member ON founder_slot_history(member_id);
        CREATE TABLE IF NOT EXISTS founder_signatures (
          member_id TEXT PRIMARY KEY REFERENCES live_founders(member_id) ON DELETE CASCADE,
          mode TEXT NOT NULL,letter TEXT NOT NULL DEFAULT '',caption TEXT NOT NULL DEFAULT '',audio_json TEXT,updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS friend_access (
          member_id TEXT PRIMARY KEY REFERENCES members(id), granted_at TEXT NOT NULL,
          granted_by TEXT REFERENCES members(id), revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS streamer_access (
          member_id TEXT PRIMARY KEY REFERENCES members(id), until_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS payments (
          id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
          plan TEXT NOT NULL, amount_cents INTEGER NOT NULL,
          starts_at TEXT NOT NULL, ends_at TEXT NOT NULL,
          verified_at TEXT NOT NULL, verified_by TEXT NOT NULL REFERENCES members(id),
          reference TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS invitations (
          token_hash TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
          expires_at TEXT NOT NULL, used_at TEXT
        );
        CREATE TABLE IF NOT EXISTS admin_notifications (
          id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,detail TEXT NOT NULL,event_key TEXT UNIQUE,
          created_at TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,last_attempt TEXT,sent_at TEXT
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
          bucket TEXT NOT NULL, attempted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS payment_member ON payments(member_id);
        CREATE INDEX IF NOT EXISTS login_attempt_time ON login_attempts(attempted_at);
        ''')
        # Earlier administrative invitations were explicitly for friends. Restore
        # those grants without changing paid periods or re-enabling revoked users.
        conn.execute('''INSERT INTO friend_access(member_id,granted_at)
          SELECT m.id,MIN(COALESCE(i.used_at,m.created_at)) FROM members m
          JOIN invitations i ON i.member_id=m.id
          WHERE m.role='member' AND m.session_version=0
          AND NOT EXISTS (SELECT 1 FROM friend_access f WHERE f.member_id=m.id)
          GROUP BY m.id ON CONFLICT(member_id) DO NOTHING''')


    from operations import init_database as init_operations
    init_operations()

def create_admin(username, password):
    username = clean_username(username)
    validate_password(password)
    with database() as conn:
        conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                     (secrets.token_hex(16), username, generate_password_hash(password), 'admin', stamp(now_utc())))


def prepare_admin_invitation(username='admin'):
    """Trusted operator-only bootstrap. Never exposed as a public HTTP endpoint."""
    username = clean_username(username)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        user = conn.execute('SELECT * FROM members WHERE username=?', (username,)).fetchone()
        if user and (user['role'] != 'admin' or user['password_hash']):
            raise ValueError('La cuenta ya existe y no se modificará. Usa el restablecimiento de contraseña autorizado.')
        ident = user['id'] if user else secrets.token_hex(16)
        if not user:
            conn.execute('INSERT INTO members(id,username,role,created_at) VALUES(?,?,?,?)', (ident, username, 'admin', stamp(now_utc())))
        conn.execute('DELETE FROM invitations WHERE member_id=?', (ident,))
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO invitations(token_hash,member_id,expires_at) VALUES(?,?,?)',
                     (hashlib.sha256(token.encode()).hexdigest(), ident, stamp(now_utc() + timedelta(hours=48))))
    return '/account#invite=' + token


def clean_username(value):
    name = str(value or '').strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,60}', name):
        raise ValueError('Usa entre 3 y 60 letras, números, puntos o guiones para el usuario.')
    validate_public_text(name)
    return name


def validate_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256:
        raise ValueError('La contraseña debe tener entre 12 y 256 caracteres.')


def user_public(user,founder_state=None):
    complimentary = bool('friend_granted_at' in user.keys() and user['friend_granted_at'] and not user['friend_revoked_at'])
    founder_number=user['founder_number'] if 'founder_number' in user.keys() else None
    founder_active=bool(founder_number and not user['founder_revoked_at']) if 'founder_revoked_at' in user.keys() else False
    trial_until=user['live_trial_until'] if 'live_trial_until' in user.keys() else None
    paid_at=user['live_paid_at'] if 'live_paid_at' in user.keys() else None
    live_revoked=user['live_revoked_at'] if 'live_revoked_at' in user.keys() else None
    live_lifetime=bool(paid_at and not live_revoked)
    trial_active=bool(trial_until and not live_revoked and trial_until>stamp(now_utc()))
    if founder_active:
        from live_access import founder_activity
        if founder_state is None:
            with database() as conn:founder_state=founder_activity(user['id'],conn)
        founder_active=founder_state['eligible'] and (live_lifetime or not trial_until or trial_until>stamp(now_utc()))
    active = user['role'] == 'admin' or complimentary or founder_active or live_lifetime or trial_active or bool(user['access_until'] and datetime.fromisoformat(user['access_until']) > now_utc())
    streamer_until=user['streamer_until'] if 'streamer_until' in user.keys() else None
    streamer_active=active and (user['role']=='admin' or founder_active or live_lifetime or trial_active or bool(streamer_until and datetime.fromisoformat(streamer_until)>now_utc()))
    return {key: user[key] for key in ('id', 'username', 'role', 'access_until', 'welcome_used')} | {'active': active, 'complimentary':complimentary,'founder_number':founder_number,'founder_active':founder_active,'live_lifetime':live_lifetime,'live_trial_until':trial_until,'trial_active':trial_active, 'streamer_until':streamer_until, 'streamer_active':streamer_active}


def get_user():
    if hasattr(g, 'member'):
        return g.member
    with database() as conn:
        row = conn.execute('SELECT m.*,s.until_at AS streamer_until,f.granted_at AS friend_granted_at,f.revoked_at AS friend_revoked_at,l.number AS founder_number,l.revoked_at AS founder_revoked_at,e.trial_until AS live_trial_until,e.paid_at AS live_paid_at,e.revoked_at AS live_revoked_at FROM members m LEFT JOIN streamer_access s ON s.member_id=m.id LEFT JOIN friend_access f ON f.member_id=m.id LEFT JOIN live_founders l ON l.member_id=m.id LEFT JOIN live_entitlements e ON e.member_id=m.id WHERE m.id=?', (session.get('member_id', ''),)).fetchone()
    g.member = row if row and row['session_version'] == session.get('session_version') else None
    return g.member


def require_admin(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        user = get_user()
        if not user or user['role'] != 'admin':
            return jsonify(error='Se requiere una cuenta de administrador.'), 403
        return fn(*args, **kwargs)
    return wrapped


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def verify_csrf():
    if request.path in {'/api/payments/webhook/platform','/api/payments/webhook/connect','/api/payments/webhook/test'}:return  # Verified by timestamped Stripe signature; never session auth.
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.path.startswith('/api/'):
        expected = session.get('csrf')
        if not expected or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), expected):
            return jsonify(error='La sesión ha caducado. Recarga la página.',code='csrf_expired'), 403


def restrict_music():
    # Music is free. Account collections require login; Ol Live requires premium.
    path=request.path
    if not path.startswith('/api/') or path.startswith(('/api/account/','/api/admin/','/api/play/','/api/resolve/','/api/channel-subscriptions/','/api/payments/')) or path in {'/api/status','/api/search','/api/trending','/api/proxy','/api/promotion/event','/api/presence','/api/live/catalogue','/api/live/founders','/api/live/founders/claim'}:
        return None
    if path.startswith('/api/stickers/') and path.endswith('/phrase'):return None
    if path.endswith('/sound.wav') and path.startswith(('/api/stickers/','/api/live/founders/')):return None
    user=get_user()
    if path.startswith(('/api/rewards','/api/stickers/')):
        if not user:return jsonify(error='Inicia sesión con una cuenta gratuita para guardar tu colección.',code='login_required'),401
        return None
    if not user or not user_public(user)['active']:
        return jsonify(error='Ver y participar en Ol Live requiere acceso premium. La música sigue siendo gratuita.',code='premium_required'),402 if user else 401


def payload():
    value = request.get_json(silent=True)
    return value if isinstance(value, dict) else {}


def allow_attempt(kind, limit=12):
    # Persisted across workers; no raw addresses in the attempt log.
    identity = f'{kind}:{request.remote_addr}:{str(payload().get("username", "")).lower()}'
    bucket = hashlib.sha256(identity.encode()).hexdigest()
    cutoff = stamp(now_utc() - timedelta(minutes=15))
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM login_attempts WHERE attempted_at < ?', (cutoff,))
        count = conn.execute('SELECT COUNT(*) AS attempts FROM login_attempts WHERE bucket=?', (bucket,)).fetchone()['attempts']
        if count >= limit:
            return False
        conn.execute('INSERT INTO login_attempts VALUES(?,?)', (bucket, stamp(now_utc())))
    return True


@bp.get('/account')
def account_page():
    return current_app.send_static_file('account.html')


@bp.get('/api/account/me')
def account_me():
    user = get_user()
    with database() as conn:
        payments = [dict(row) for row in conn.execute('SELECT plan,amount_cents,starts_at,ends_at,verified_at FROM payments WHERE member_id=? ORDER BY ends_at DESC', (user['id'] if user else '',))]
    from streamers import streamer_sales_ready,live_ready
    from operations import premiere
    from founder_slots import cleanup,reservation
    cleanup()
    if user:
        from flask import g
        if hasattr(g,'member'):del g.member
        user=get_user()
    with database() as conn:
        slot=reservation(conn,user['id']) if user else None
        last_release=conn.execute('SELECT number,trial_until,released_at FROM founder_slot_history WHERE member_id=? ORDER BY released_at DESC,id DESC LIMIT 1',(user['id'],)).fetchone() if user else None
    return jsonify(user=user_public(user) if user else None, csrf=csrf_token(), payments=payments, payment_mode='manual_verified', streamer_available=streamer_sales_ready(),premium_available=streamer_sales_ready(),founder_reservation=slot,founder_last_release=dict(last_release) if last_release else None,live_video_ready=live_ready(),music_free=True,live_price_cents=2500,live_trial_months=0,live_trial_days=7,live_premiere=premiere())


@bp.post('/api/account/register')
def register():
    if not allow_attempt('register', 8):
        return jsonify(error='Demasiados intentos. Espera 15 minutos.'), 429
    data = payload()
    try:
        name = clean_username(data.get('username'))
        validate_password(data.get('password'))
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            from human_check import verify
            if not verify(conn):
                return jsonify(error='Completa la comprobación humana con el código de la imagen. Si ha caducado, pide otro.',code='human_required'),400
            ident = secrets.token_hex(16)
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (ident, name, generate_password_hash(data['password']), stamp(now_utc())))
        session.clear()
        session.update(member_id=ident, session_version=0,csrf=secrets.token_urlsafe(32))
        session.permanent = True
        notify('registration','Nueva cuenta registrada','Se ha registrado una cuenta de cliente. El registro no activa acceso de pago.',event_key='registration:'+ident)
        return jsonify(ok=True), 201
    except (ValueError,) + INTEGRITY_ERRORS as exc:
        return jsonify(error=str(exc) if isinstance(exc, ValueError) else 'Ese usuario no está disponible.'), 400


@bp.post('/api/account/login')
def login():
    if not allow_attempt('login'):
        return jsonify(error='Demasiados intentos. Espera 15 minutos.'), 429
    data = payload()
    with database() as conn:
        user = conn.execute('SELECT * FROM members WHERE username=?', (str(data.get('username', '')).strip().lower(),)).fetchone()
    password = data.get('password')
    valid_password = password if isinstance(password, str) and len(password) <= 256 else ''
    # Verify a dummy hash too, avoiding a fast response for unknown accounts.
    encoded = user['password_hash'] if user and user['password_hash'] else current_app.config['MEMBERSHIP_DUMMY_HASH']
    if not check_password_hash(encoded, valid_password) or not user or not user['password_hash']:
        return jsonify(error='Usuario o contraseña incorrectos.'), 401
    from two_factor import login_factor
    if not login_factor(user,data):return jsonify(error='Introduce un código nuevo de la app autenticadora o un código de recuperación.',code='two_factor_required'),401
    session.clear()
    session.update(member_id=user['id'], session_version=user['session_version'],csrf=secrets.token_urlsafe(32))
    session.permanent = True
    return jsonify(ok=True)


@bp.post('/api/account/logout')
def logout():
    session.clear()
    return jsonify(ok=True)


@bp.get('/api/admin/members')
@require_admin
def list_members():
    with database() as conn:
        from live_access import founder_activity
        users = [user_public(row,founder_state=founder_activity(row['id'],conn) if row['founder_number'] else None) for row in conn.execute('SELECT m.*,s.until_at AS streamer_until,f.granted_at AS friend_granted_at,f.revoked_at AS friend_revoked_at,l.number AS founder_number,l.revoked_at AS founder_revoked_at,e.trial_until AS live_trial_until,e.paid_at AS live_paid_at,e.revoked_at AS live_revoked_at FROM members m LEFT JOIN streamer_access s ON s.member_id=m.id LEFT JOIN friend_access f ON f.member_id=m.id LEFT JOIN live_founders l ON l.member_id=m.id LEFT JOIN live_entitlements e ON e.member_id=m.id ORDER BY m.created_at DESC')]
        payments = [dict(row) for row in conn.execute('SELECT p.*,m.username FROM payments p JOIN members m ON m.id=p.member_id ORDER BY verified_at DESC LIMIT 300')]
    return jsonify(members=users, payments=payments)


@bp.get('/api/admin/invitations')
@require_admin
def invitation_history():
    try: page=max(1,int(request.args.get('page','1')))
    except ValueError: page=1
    with database() as conn:
        total=conn.execute("SELECT COUNT(*) AS n FROM invitations i JOIN members m ON m.id=i.member_id WHERE m.role='member'").fetchone()['n']
        pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute("SELECT i.member_id,m.username,i.expires_at,i.used_at FROM invitations i JOIN members m ON m.id=i.member_id WHERE m.role='member' ORDER BY i.expires_at DESC LIMIT 25 OFFSET ?",((page-1)*25,)).fetchall()
    return jsonify(invitations=[dict(row) for row in rows],total=total,page=page,pages=pages)


@bp.post('/api/admin/invitations/clear')
@require_admin
def clear_invitation_history():
    data=payload()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if data.get('member_id'):
            conn.execute("DELETE FROM invitations WHERE member_id IN (SELECT id FROM members WHERE id=? AND role='member')",(str(data['member_id']),))
        elif data.get('completed') is True:
            conn.execute("DELETE FROM invitations WHERE (used_at IS NOT NULL OR expires_at<=?) AND member_id IN (SELECT id FROM members WHERE role='member')",(stamp(now_utc()),))
        else: return jsonify(error='Selecciona una invitación o el historial usado y caducado.'),400
    return jsonify(ok=True)


@bp.post('/api/admin/invite')
@require_admin
def invite():
    try:
        name = clean_username(payload().get('username'))
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing=conn.execute('SELECT id,role,password_hash FROM members WHERE username=?',(name,)).fetchone()
            if existing and (existing['role']!='member' or existing['password_hash']):
                return jsonify(error='Esta cuenta ya está activada. Usa «Dar acceso gratuito» en el listado de clientes.'),409
            ident=existing['id'] if existing else secrets.token_hex(16)
            if not existing:conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,name,stamp(now_utc())))
            conn.execute('DELETE FROM invitations WHERE member_id=?',(ident,))
            token = secrets.token_urlsafe(32)
            conn.execute('INSERT INTO invitations(token_hash,member_id,expires_at) VALUES(?,?,?)',
                         (hashlib.sha256(token.encode()).hexdigest(), ident, stamp(now_utc() + timedelta(hours=48))))
            conn.execute('INSERT INTO friend_access(member_id,granted_at,granted_by) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET granted_at=excluded.granted_at,granted_by=excluded.granted_by,revoked_at=NULL',(ident,stamp(now_utc()),get_user()['id']))
        # Token returned only to the authenticated admin, not logs or a repository.
        return jsonify(path='/account#invite=' + token, username=name, complimentary=True), 201
    except (ValueError,) + INTEGRITY_ERRORS:
        return jsonify(error='Usuario inválido o ya existente.'), 400


@bp.post('/api/admin/friend-access')
@require_admin
def friend_access():
    data=payload()
    if not isinstance(data.get('active'),bool):
        return jsonify(error='Indica si deseas dar o retirar el acceso gratuito.'),400
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        user=conn.execute('SELECT id,role FROM members WHERE id=?',(str(data.get('member_id','')),)).fetchone()
        if not user or user['role']=='admin':
            return jsonify(error='Selecciona una cuenta de cliente.'),400
        if data['active']:
            conn.execute('INSERT INTO friend_access(member_id,granted_at,granted_by,revoked_at) VALUES(?,?,?,NULL) ON CONFLICT(member_id) DO UPDATE SET granted_at=excluded.granted_at,granted_by=excluded.granted_by,revoked_at=NULL',(user['id'],stamp(now_utc()),get_user()['id']))
        else:
            conn.execute('UPDATE friend_access SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),user['id']))
            conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?',(user['id'],))
    return jsonify(ok=True,complimentary=data['active'])


@bp.post('/api/account/accept-invite')
def accept_invite():
    if not allow_attempt('invite'):
        return jsonify(error='Demasiados intentos.'), 429
    data = payload()
    try:
        validate_password(data.get('password'))
        token = str(data.get('token', ''))
        if not 20 <= len(token) <= 100:
            raise ValueError('Invitación no válida o caducada.')
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            invitation = conn.execute('SELECT * FROM invitations WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if not invitation or invitation['used_at'] or invitation['expires_at'] <= stamp(now_utc()):
                raise ValueError('Invitación no válida o caducada.')
            conn.execute('UPDATE members SET password_hash=? WHERE id=?', (generate_password_hash(data['password']), invitation['member_id']))
            conn.execute('UPDATE invitations SET used_at=? WHERE token_hash=?', (stamp(now_utc()), invitation['token_hash']))
        session.clear()
        session.update(member_id=invitation['member_id'], session_version=0,csrf=secrets.token_urlsafe(32))
        session.permanent = True
        notify('invitation','Invitación aceptada','Un invitado ha activado su cuenta. Revisa su acceso gratuito en administración.',event_key='invite:'+invitation['member_id'])
        return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post('/api/admin/confirm-payment')
@require_admin
def confirm_payment():
    from payments import provider
    if provider()=='stripe':return jsonify(error='Los pagos nuevos se confirman automáticamente mediante Stripe. Consulta allí los cobros; no se activan manualmente.'),409
    data = payload()
    plan = data.get('plan')
    reference = str(data.get('reference', '')).strip()
    if plan not in PLANS or not 4 <= len(reference) <= 120:
        return jsonify(error='Indica plan y referencia única del pago comprobado en PayPal.'), 400
    from payments import ready
    if not ready():return jsonify(error='Los cobros de Ol Live están bloqueados hasta que la emisión esté disponible. Escuchar música es gratuito.'),409
    try:
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            from founder_slots import release_expired,reservation,payment_allowed
            release_expired(conn)
            user = conn.execute('SELECT * FROM members WHERE id=?', (str(data.get('member_id', '')),)).fetchone()
            if not user or user['role'] == 'admin':
                return jsonify(error='Selecciona una cuenta de cliente.'), 400
            from live_access import details,founder_activity
            friend=conn.execute('SELECT revoked_at FROM friend_access WHERE member_id=?',(user['id'],)).fetchone()
            if friend and not friend['revoked_at']:return jsonify(error='Esta cuenta tiene acceso especial activo. No corresponde registrar un cobro.'),409
            entitlement=details(user['id'],conn)
            if entitlement.get('paid_at'):return jsonify(error='Esta cuenta ya tiene el pago único de Ol Live.'),409
            slot=reservation(conn,user['id'])
            if not payment_allowed(entitlement,slot):return jsonify(error='El pago único se habilita al terminar la prueba de siete días. Los plazos históricos ya iniciados se conservan.'),409
            start=now_utc();end=end_of_plan(start,plan)
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),user['id'],plan,PLANS[plan]['cents'],stamp(start),stamp(end),stamp(now_utc()),get_user()['id'],reference))
            access_end=max(end,datetime.fromisoformat(user['access_until'])) if user['access_until'] else end
            conn.execute('UPDATE members SET access_until=?,welcome_used=MAX(welcome_used,?) WHERE id=?',(stamp(access_end),1,user['id']))
            conn.execute('INSERT INTO live_entitlements(member_id,trial_until,paid_at) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET paid_at=excluded.paid_at,revoked_at=NULL',(user['id'],entitlement.get('trial_until') or (slot or {}).get('trial_until'),stamp(now_utc())))
            conn.execute('INSERT INTO streamer_access(member_id,until_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET until_at=excluded.until_at',(user['id'],stamp(end)))
        notify('payment','Pago registrado',f'Se ha registrado un pago comprobado de {PLANS[plan]["cents"]/100:.2f} € para el plan {plan}. Consulta usuario, referencia y fechas en el panel privado.',event_key='payment:'+reference)
        return jsonify(ok=True, access_until=stamp(access_end))
    except INTEGRITY_ERRORS:
        return jsonify(error='Esta referencia de pago ya se ha utilizado.'), 409


@bp.post('/api/admin/revoke')
@require_admin
def revoke():
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('UPDATE members SET access_until=?,session_version=session_version+1 WHERE id=? AND role!=?',
                     (stamp(now_utc()), str(payload().get('member_id', '')), 'admin'))
        conn.execute('UPDATE pricing_moderators SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),str(payload().get('member_id',''))))
        conn.execute('UPDATE ol_supervisors SET revoked_at=?,can_review=0 WHERE member_id=?',(stamp(now_utc()),str(payload().get('member_id',''))))
        conn.execute('UPDATE live_entitlements SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),str(payload().get('member_id',''))))
        conn.execute('UPDATE live_founders SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),str(payload().get('member_id',''))))
        conn.execute('UPDATE friend_access SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),str(payload().get('member_id',''))))
        conn.execute('DELETE FROM streamer_access WHERE member_id IN (SELECT id FROM members WHERE id=? AND role!=?)',(str(payload().get('member_id','')),'admin'))
    return jsonify(ok=True)


def install(app):
    remote_database = os.getenv('DATABASE_URL')
    on_vercel = os.getenv('VERCEL') == '1'
    external_key = os.getenv('MAGGY_SESSION_SECRET') or os.getenv('SECRET_KEY')
    if on_vercel and not remote_database:
        raise RuntimeError('Configura DATABASE_URL con PostgreSQL persistente antes de desplegar en Vercel.')
    if external_key and len(external_key) < 32:
        raise RuntimeError('La clave de sesión debe tener al menos 32 caracteres aleatorios.')
    if on_vercel and not external_key:
        raise RuntimeError('Configura MAGGY_SESSION_SECRET como secreto estable en Vercel.')
    state_dir = Path(os.getenv('MAGGY_DATA_DIR', str(Path(__file__).parent / '.instance')))
    if external_key:
        app.secret_key = external_key
    else:
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        key_file = state_dir / 'session.key'
        if not key_file.exists():
            with tempfile.NamedTemporaryFile(mode='w', dir=state_dir, delete=False) as stream:
                temporary_key = Path(stream.name)
                stream.write(secrets.token_hex(32)); stream.flush(); os.fsync(stream.fileno())
            try:
                os.link(temporary_key, key_file)
            except FileExistsError:
                pass
            finally:
                temporary_key.unlink()
        app.secret_key = key_file.read_text().strip()
    app.config.update(MEMBERSHIP_DATABASE=str(state_dir / 'members.sqlite3'), MEMBERSHIP_DATABASE_URL=remote_database,
                      MEMBERSHIP_DUMMY_HASH=generate_password_hash(secrets.token_urlsafe(32)),
                      SESSION_REFRESH_EACH_REQUEST=False, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=on_vercel or os.getenv('MAGGY_COOKIE_SECURE', '1') != '0',
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30), MAX_CONTENT_LENGTH=65536)
    with app.app_context():
        init_database()
    app.register_blueprint(bp)
    from human_check import install as install_human_check
    install_human_check(app)
    app.before_request(verify_csrf)
    app.before_request(restrict_music)
    @app.after_request
    def private_pages(response):
        if request.path in {'/', '/account'} or request.path.startswith(('/api/account/', '/api/admin/')):
            response.headers['Cache-Control'] = 'no-store'
        return response
