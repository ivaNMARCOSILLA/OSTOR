"""Native live video and direct, external gifts. No custody or gift commissions."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlparse
from flask import Blueprint, current_app, jsonify, request
from membership import database, get_user, now_utc, stamp, user_public

bp=Blueprint('streamers',__name__)
STREAMER_MONTHLY_CENTS=800
GIFT_COMMISSION_BPS=0


def live_ready():
    try:
        parsed=urlparse(os.getenv('LIVEKIT_URL','').strip())
        port=parsed.port
        return bool(os.getenv('MAGGY_STREAMERS_ENABLED')=='1' and parsed.scheme=='wss' and parsed.hostname
                    and (port is None or 1<=port<=65535) and not parsed.username and not parsed.password
                    and not parsed.query and not parsed.fragment and os.getenv('LIVEKIT_API_KEY')
                    and len(os.getenv('LIVEKIT_API_SECRET',''))>=32)
    except (ValueError,TypeError):
        return False


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS streamer_channels (
            id TEXT PRIMARY KEY, member_id TEXT NOT NULL UNIQUE REFERENCES members(id),
            title TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '', paypal_url TEXT NOT NULL DEFAULT '',
            room_name TEXT NOT NULL UNIQUE, live_until TEXT, updated_at TEXT NOT NULL
        )''')


def paypal_link(value):
    if not value: return ''
    parsed=urlparse(str(value).strip())
    handle=parsed.path.strip('/')
    if parsed.scheme!='https' or parsed.hostname not in {'paypal.me','www.paypal.me'} or parsed.username or parsed.password or parsed.port not in {None,443} or not re.fullmatch(r'[A-Za-z0-9]{3,64}',handle):
        raise ValueError('Utiliza tu enlace completo https://paypal.me/TuNombre, sin importe.')
    return 'https://paypal.me/'+handle


def channel_public(row):
    return {key:row[key] for key in ['id','title','bio','username','paypal_url']} | {'live':bool(row['live_until'] and row['live_until']>stamp(now_utc()))}


def own_channel():
    with database() as conn:
        row=conn.execute('SELECT c.*,m.username FROM streamer_channels c JOIN members m ON m.id=c.member_id WHERE c.member_id=?',(get_user()['id'],)).fetchone()
    return row


def publisher_allowed():
    return bool(user_public(get_user())['streamer_active'])


def mint_token(user,channel,publish):
    now=int(time.time())
    grant={'roomJoin':True,'room':channel['room_name'],'canPublish':publish,'canSubscribe':True,'canPublishData':False}
    if publish: grant['canPublishSources']=['camera','microphone']
    claims={'iss':os.environ['LIVEKIT_API_KEY'],'sub':f"maggy-{user['id']}-{secrets.token_hex(5)}",'name':user['username'],
            'iat':now,'nbf':now-5,'exp':now+300,'video':grant}
    def encode(value): return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=')
    message=encode({'alg':'HS256','typ':'JWT'})+b'.'+encode(claims)
    signature=base64.urlsafe_b64encode(hmac.new(os.environ['LIVEKIT_API_SECRET'].encode(),message,hashlib.sha256).digest()).rstrip(b'=')
    return (message+b'.'+signature).decode()


@bp.before_request
def rate_limit():
    limiter=current_app.extensions.get('streamer_rate_limiter')
    if request.path.startswith('/api/') and limiter and not limiter('streamers',240):
        return jsonify(error='Espera un momento antes de volver a intentarlo.'),429


@bp.get('/streamers')
def page():
    return current_app.send_static_file('streamers.html')


@bp.get('/api/streamers')
def channels():
    user=get_user()
    with database() as conn:
        rows=conn.execute('SELECT c.*,m.username FROM streamer_channels c JOIN members m ON m.id=c.member_id WHERE c.live_until>? ORDER BY c.updated_at DESC LIMIT 60',(stamp(now_utc()),)).fetchall()
    own=own_channel()
    return jsonify(video_ready=live_ready(),streamer_active=publisher_allowed(),streamer_monthly_cents=800,gift_commission_bps=0,
                   channels=[channel_public(row) for row in rows],mine=channel_public(own) if own else None,
                   user={'id':user['id'],'username':user['username']})


@bp.post('/api/streamers/me')
def save_channel():
    if not publisher_allowed(): return jsonify(error='Emitir requiere el plan Streamer de 8 € por un mes.'),403
    data=request.get_json(silent=True) or {}
    title=str(data.get('title','')).strip();bio=str(data.get('bio','')).strip()
    if not 3<=len(title)<=80 or len(bio)>400: return jsonify(error='Indica un título de 3 a 80 caracteres y una presentación de hasta 400.'),400
    try: paypal=paypal_link(data.get('paypal_url',''))
    except (ValueError,TypeError): return jsonify(error='El enlace PayPal.me no es válido.'),400
    if paypal and data.get('owns_paypal') is not True: return jsonify(error='Confirma que el enlace de PayPal te pertenece.'),400
    user=get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT id FROM streamer_channels WHERE member_id=?',(user['id'],)).fetchone()
        if row:
            conn.execute('UPDATE streamer_channels SET title=?,bio=?,paypal_url=?,updated_at=? WHERE member_id=?',(title,bio,paypal,stamp(now_utc()),user['id']))
        else:
            ident=secrets.token_hex(16)
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,bio,paypal_url,room_name,updated_at) VALUES(?,?,?,?,?,?,?)',
                         (ident,user['id'],title,bio,paypal,'maggy-'+ident,stamp(now_utc())))
    return jsonify(ok=True,channel=channel_public(own_channel()))


@bp.post('/api/streamers/<channel_id>/token')
def token(channel_id):
    if not live_ready(): return jsonify(error='Las emisiones todavía no están activadas. No se ha cobrado ningún alta de streamer.',code='live_not_configured'),503
    with database() as conn:
        channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
    if not channel: return jsonify(error='Este canal no existe.'),404
    publish=(request.get_json(silent=True) or {}).get('publish') is True
    user=get_user()
    if publish and (channel['member_id']!=user['id'] or not publisher_allowed()): return jsonify(error='Solo el creador con plan Streamer activo puede emitir en este canal.'),403
    if not publish and not (channel['live_until'] and channel['live_until']>stamp(now_utc())): return jsonify(error='Este canal no está en directo.'),404
    return jsonify(url=os.environ['LIVEKIT_URL'],token=mint_token(user,channel,publish))


@bp.post('/api/streamers/me/live')
def presence():
    if not publisher_allowed(): return jsonify(error='Tu plan Streamer no está activo.'),403
    live=(request.get_json(silent=True) or {}).get('live') is True
    if live and not live_ready(): return jsonify(error='Las emisiones no están activadas.'),503
    with database() as conn:
        conn.execute('UPDATE streamer_channels SET live_until=?,updated_at=? WHERE member_id=?',
                     (stamp(now_utc()+timedelta(seconds=75)) if live else None,stamp(now_utc()),get_user()['id']))
    return jsonify(ok=True)


@bp.post('/api/streamers/<channel_id>/gift-link')
def gift_link(channel_id):
    amount=(request.get_json(silent=True) or {}).get('amount_cents')
    if isinstance(amount,bool) or not isinstance(amount,int) or not 100<=amount<=100000: return jsonify(error='Introduce entre 1 y 1.000 €, con un máximo de dos decimales.'),400
    with database() as conn:
        row=conn.execute('SELECT c.*,m.username,m.role,m.access_until,s.until_at AS streamer_until FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN streamer_access s ON s.member_id=m.id WHERE c.id=?',(channel_id,)).fetchone()
    if not row or not row['paypal_url']: return jsonify(error='Este creador no tiene enlace para recibir regalos.'),404
    active_creator=row['role']=='admin' or bool(row['access_until'] and row['access_until']>stamp(now_utc()) and row['streamer_until'] and row['streamer_until']>stamp(now_utc()))
    if not active_creator: return jsonify(error='Este canal no tiene plan Streamer activo.'),409
    return jsonify(url=paypal_link(row['paypal_url'])+f'/{amount//100}.{amount%100:02d}EUR',creator=row['username'],amount_cents=amount,
                   maggy_commission_cents=0,mode='external_paypal_link',payment_confirmed=False)


def install(app,rate_limiter=None):
    if rate_limiter: app.extensions['streamer_rate_limiter']=rate_limiter
    with app.app_context(): init_database()
    app.register_blueprint(bp)
