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

from werkzeug.security import check_password_hash, generate_password_hash

bp = Blueprint('membership', __name__)
UTC = timezone.utc
PLANS = {'welcome': {'cents': 100, 'days': 14}, 'monthly': {'cents': 600, 'months': 1}, 'streamer': {'cents': 800, 'months': 1}}


def now_utc():
    return datetime.now(UTC).replace(microsecond=0)


def stamp(value):
    return value.astimezone(UTC).isoformat()


def end_of_plan(start, plan):
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
        CREATE TABLE IF NOT EXISTS members (
          id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          password_hash TEXT, role TEXT NOT NULL DEFAULT 'member',
          created_at TEXT NOT NULL, access_until TEXT,
          welcome_used INTEGER NOT NULL DEFAULT 0, session_version INTEGER NOT NULL DEFAULT 0
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
        CREATE TABLE IF NOT EXISTS login_attempts (
          bucket TEXT NOT NULL, attempted_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS payment_member ON payments(member_id);
        CREATE INDEX IF NOT EXISTS login_attempt_time ON login_attempts(attempted_at);
        ''')


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
    return name


def validate_password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256:
        raise ValueError('La contraseña debe tener entre 12 y 256 caracteres.')


def user_public(user):
    active = user['role'] == 'admin' or bool(user['access_until'] and datetime.fromisoformat(user['access_until']) > now_utc())
    streamer_until=user['streamer_until'] if 'streamer_until' in user.keys() else None
    streamer_active=active and (user['role']=='admin' or bool(streamer_until and datetime.fromisoformat(streamer_until)>now_utc()))
    return {key: user[key] for key in ('id', 'username', 'role', 'access_until', 'welcome_used')} | {'active': active, 'streamer_until':streamer_until, 'streamer_active':streamer_active}


def get_user():
    if hasattr(g, 'member'):
        return g.member
    with database() as conn:
        row = conn.execute('SELECT m.*,s.until_at AS streamer_until FROM members m LEFT JOIN streamer_access s ON s.member_id=m.id WHERE m.id=?', (session.get('member_id', ''),)).fetchone()
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
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and request.path.startswith('/api/'):
        expected = session.get('csrf')
        if not expected or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), expected):
            return jsonify(error='La sesión ha caducado. Recarga la página.'), 403


def restrict_music():
    # Public storefront/catalogue; resolution and playback remain protected.
    if not request.path.startswith('/api/') or request.path.startswith(('/api/account/', '/api/admin/')) or request.path in {'/api/search', '/api/trending'}:
        return None
    user = get_user()
    if not user or not user_public(user)['active']:
        return jsonify(error='Desbloquea Ol para escuchar música.', code='membership_required'), 402 if user else 401


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
    from streamers import streamer_sales_ready
    return jsonify(user=user_public(user) if user else None, csrf=csrf_token(), payments=payments, payment_mode='manual_verified', streamer_available=streamer_sales_ready())


@bp.post('/api/account/register')
def register():
    if not allow_attempt('register', 8):
        return jsonify(error='Demasiados intentos. Espera 15 minutos.'), 429
    data = payload()
    try:
        name = clean_username(data.get('username'))
        validate_password(data.get('password'))
        with database() as conn:
            ident = secrets.token_hex(16)
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (ident, name, generate_password_hash(data['password']), stamp(now_utc())))
        session.clear()
        session.update(member_id=ident, session_version=0)
        session.permanent = True
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
    session.clear()
    session.update(member_id=user['id'], session_version=user['session_version'])
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
        users = [user_public(row) for row in conn.execute('SELECT m.*,s.until_at AS streamer_until FROM members m LEFT JOIN streamer_access s ON s.member_id=m.id ORDER BY m.created_at DESC')]
        payments = [dict(row) for row in conn.execute('SELECT p.*,m.username FROM payments p JOIN members m ON m.id=p.member_id ORDER BY verified_at DESC LIMIT 300')]
    return jsonify(members=users, payments=payments)


@bp.post('/api/admin/invite')
@require_admin
def invite():
    try:
        name = clean_username(payload().get('username'))
        with database() as conn:
            ident = secrets.token_hex(16)
            conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)', (ident, name, stamp(now_utc())))
            token = secrets.token_urlsafe(32)
            conn.execute('INSERT INTO invitations(token_hash,member_id,expires_at) VALUES(?,?,?)',
                         (hashlib.sha256(token.encode()).hexdigest(), ident, stamp(now_utc() + timedelta(hours=48))))
        # Token returned only to the authenticated admin, not logs or a repository.
        return jsonify(path='/account#invite=' + token, username=name), 201
    except (ValueError,) + INTEGRITY_ERRORS:
        return jsonify(error='Usuario inválido o ya existente.'), 400


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
        session.update(member_id=invitation['member_id'], session_version=0)
        session.permanent = True
        return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post('/api/admin/confirm-payment')
@require_admin
def confirm_payment():
    data = payload()
    plan = data.get('plan')
    reference = str(data.get('reference', '')).strip()
    if plan not in PLANS or not 4 <= len(reference) <= 120:
        return jsonify(error='Indica plan y referencia única del pago comprobado en PayPal.'), 400
    if plan == 'streamer':
        from streamers import streamer_sales_ready
        if not streamer_sales_ready(): return jsonify(error='No se puede activar ni cobrar el plan Streamer hasta conectar las emisiones.'),409
    try:
        with database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            user = conn.execute('SELECT * FROM members WHERE id=?', (str(data.get('member_id', '')),)).fetchone()
            if not user or user['role'] == 'admin':
                return jsonify(error='Selecciona una cuenta de cliente.'), 400
            if plan == 'welcome' and user['welcome_used']:
                return jsonify(error='La bienvenida de 14 días ya se utilizó en esta cuenta.'), 409
            if plan == 'streamer':
                old=conn.execute('SELECT until_at FROM streamer_access WHERE member_id=?',(user['id'],)).fetchone()
                start=max(now_utc(),datetime.fromisoformat(old['until_at'])) if old else now_utc()
            else:
                start=max(now_utc(),datetime.fromisoformat(user['access_until'])) if user['access_until'] else now_utc()
            end=end_of_plan(start,plan)
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),user['id'],plan,PLANS[plan]['cents'],stamp(start),stamp(end),stamp(now_utc()),get_user()['id'],reference))
            access_end=max(end,datetime.fromisoformat(user['access_until'])) if user['access_until'] else end
            conn.execute('UPDATE members SET access_until=?,welcome_used=MAX(welcome_used,?) WHERE id=?',(stamp(access_end),1,user['id']))
            if plan == 'streamer':
                conn.execute('INSERT INTO streamer_access(member_id,until_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET until_at=excluded.until_at',(user['id'],stamp(end)))
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
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=on_vercel or os.getenv('MAGGY_COOKIE_SECURE', '1') != '0',
                      PERMANENT_SESSION_LIFETIME=timedelta(days=30), MAX_CONTENT_LENGTH=65536)
    with app.app_context():
        init_database()
    app.register_blueprint(bp)
    app.before_request(verify_csrf)
    app.before_request(restrict_music)
    @app.after_request
    def private_pages(response):
        if request.path in {'/', '/account'} or request.path.startswith(('/api/account/', '/api/admin/')):
            response.headers['Cache-Control'] = 'no-store'
        return response
