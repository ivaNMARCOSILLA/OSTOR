"""Native live video and direct, external gifts. No custody or gift commissions."""
from __future__ import annotations
from moderation import is_abusive, validate_public_text
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import requests
from datetime import timedelta
from urllib.parse import urlparse
from flask import Blueprint, current_app, jsonify, request
from membership import database, get_user, now_utc, stamp, user_public

bp=Blueprint('streamers',__name__)
LIVE_PRICE_CENTS=2500
GIFT_COMMISSION_BPS=0
LIVE_CATEGORIES={'videojuegos':'Videojuegos','musica':'Música','entretenimiento':'Entretenimiento','actualidad':'Actualidad'}


def video_configuration_checks():
    try:
        parsed=urlparse(os.getenv('LIVEKIT_URL','').strip())
        port=parsed.port
        url_ok=bool(parsed.scheme=='wss' and parsed.hostname and (port is None or 1<=port<=65535)
                    and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment)
    except (ValueError,TypeError):
        url_ok=False
    key=os.getenv('LIVEKIT_API_KEY','').strip();secret=os.getenv('LIVEKIT_API_SECRET','').strip()
    return {'LIVEKIT_URL':url_ok,'LIVEKIT_API_KEY':bool(key and not key.startswith(('wss:','https:'))),
            'LIVEKIT_API_SECRET':bool(len(secret)>=32 and secret!=key and not secret.startswith(('wss:','https:'))),
            'MAGGY_STREAMERS_ENABLED':os.getenv('MAGGY_STREAMERS_ENABLED')=='1'}


def live_ready():
    return all(video_configuration_checks().values())


def streamer_sales_ready():
    return live_ready() and os.getenv('MAGGY_STREAMER_SALES_ENABLED')=='1'


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS streamer_channels (
            id TEXT PRIMARY KEY, member_id TEXT NOT NULL UNIQUE REFERENCES members(id),
            title TEXT NOT NULL, bio TEXT NOT NULL DEFAULT '', paypal_url TEXT NOT NULL DEFAULT '',
            room_name TEXT NOT NULL UNIQUE, live_until TEXT, updated_at TEXT NOT NULL
        ); CREATE TABLE IF NOT EXISTS live_channel_settings (
            channel_id TEXT PRIMARY KEY REFERENCES streamer_channels(id) ON DELETE CASCADE,
            category TEXT NOT NULL DEFAULT 'entretenimiento',featured INTEGER NOT NULL DEFAULT 0
        )''')
    from community import init_database as init_community_database
    init_community_database()
    from rewards import init_database as init_rewards_database
    init_rewards_database()


def paypal_link(value):
    if not value: return ''
    parsed=urlparse(str(value).strip())
    handle=parsed.path.strip('/')
    if parsed.scheme!='https' or parsed.hostname not in {'paypal.me','www.paypal.me'} or parsed.username or parsed.password or parsed.port not in {None,443} or not re.fullmatch(r'[A-Za-z0-9]{3,64}',handle):
        raise ValueError('Utiliza tu enlace completo https://paypal.me/TuNombre, sin importe.')
    return 'https://paypal.me/'+handle


def channel_public(row):
    from founders import signature_from_row
    return {key:row[key] for key in ['id','title','bio','username']} | {'paypal_url':'' if os.getenv('VERCEL_ENV') in {'production','preview'} or os.getenv('OL_PAYMENT_PROVIDER','stripe')=='stripe' else row['paypal_url']} | {'live':bool(row['live_until'] and row['live_until']>stamp(now_utc())),'category':row['category'] if 'category' in row.keys() and row['category'] else 'entretenimiento','featured':bool(row['featured']) if 'featured' in row.keys() else False,'founder_number':row['founder_number'] if 'founder_number' in row.keys() else None,'founder_signature':signature_from_row(row) if 'founder_number' in row.keys() and row['founder_number'] else None}


def own_channel():
    with database() as conn:
        row=conn.execute('SELECT c.*,m.username,o.category,o.featured,f.number AS founder_number,sg.mode AS badge_mode,sg.letter AS badge_letter,sg.caption AS badge_caption,sg.audio_json AS badge_audio FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN live_channel_settings o ON o.channel_id=c.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN founder_signatures sg ON sg.member_id=m.id WHERE c.member_id=?',(get_user()['id'],)).fetchone()
    return row


def publisher_allowed():
    return bool(user_public(get_user())['streamer_active'])


def mint_token(user,channel,publish):
    now=int(time.time())
    grant={'roomJoin':True,'room':channel['room_name'],'canPublish':publish,'canSubscribe':True,'canPublishData':False}
    if publish: grant['canPublishSources']=['camera','microphone','screen_share','screen_share_audio']
    claims={'iss':os.environ['LIVEKIT_API_KEY'].strip(),'sub':f"maggy-{user['id']}-{secrets.token_hex(5)}",'name':user['username'],
            'iat':now,'nbf':now-5,'exp':now+300,'video':grant}
    return sign_token(claims)


def sign_token(claims):
    def encode(value): return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).rstrip(b'=')
    message=encode({'alg':'HS256','typ':'JWT'})+b'.'+encode(claims)
    signature=base64.urlsafe_b64encode(hmac.new(os.environ['LIVEKIT_API_SECRET'].strip().encode(),message,hashlib.sha256).digest()).rstrip(b'=')
    return (message+b'.'+signature).decode()


@bp.post('/api/streamers/admin/check-video')
def check_video():
    if get_user()['role']!='admin': return jsonify(error='Se requiere administración.'),403
    checks=video_configuration_checks()
    if not all(checks.values()): return jsonify(connected=False,checks=checks,message='Revisa las variables pendientes en Vercel '+('Production para electronicama.com.' if os.getenv('VERCEL_ENV')=='production' else 'Preview para esta vista de pruebas.' if os.getenv('VERCEL_ENV')=='preview' else 'o en el entorno local.')),409
    parsed=urlparse(os.environ['LIVEKIT_URL'].strip())
    now=int(time.time())
    token=sign_token({'iss':os.environ['LIVEKIT_API_KEY'].strip(),'sub':'maggy-connection-check','iat':now,'nbf':now-5,'exp':now+60,'video':{'roomList':True}})
    try:
        response=requests.post('https://'+parsed.netloc+'/twirp/livekit.RoomService/ListRooms',json={},
                               headers={'Authorization':'Bearer '+token,'User-Agent':'Maggy video connection check'},
                               timeout=(3,8),allow_redirects=False)
        try:
            if response.status_code==200:
                try: payload=response.json()
                except ValueError: payload=None
                if not isinstance(payload,dict) or (payload and not isinstance(payload.get('rooms'),list)):
                    return jsonify(connected=False,checks=checks,message='La URL no devolvió una respuesta válida de LiveKit. Comprueba la URL WebSocket del proyecto.'),502
                return jsonify(connected=True,checks=checks,message='Conexión con LiveKit correcta. Puedes probar cámara y micrófono. Los cobros siguen bloqueados hasta habilitarlos por separado.')
            if response.status_code in (401,403):
                return jsonify(connected=False,checks=checks,message='LiveKit no acepta la pareja de API Key y API Secret. Comprueba que pertenecen a la misma clave y al proyecto de esa URL.'),502
            return jsonify(connected=False,checks=checks,message='LiveKit no respondió correctamente. Vuelve a intentarlo.'),502
        finally:
            response.close()
    except requests.RequestException:
        return jsonify(connected=False,checks=checks,message='No se pudo conectar con la URL de LiveKit. Comprueba la URL WebSocket del proyecto.'),502


@bp.before_request
def rate_limit():
    from operations import premiere
    if premiere() and request.path.startswith('/api/streamers') and '/admin/' not in request.path:
        user=get_user()
        if not user or user['role']!='admin':return jsonify(error='Ol Livis · próximo estreno.',code='live_premiere'),409
    limiter=current_app.extensions.get('streamer_rate_limiter')
    if request.path.startswith('/api/') and limiter and not limiter('streamers',240):
        return jsonify(error='Espera un momento antes de volver a intentarlo.'),429


@bp.get('/live')
@bp.get('/streamers')
def page():
    return current_app.send_static_file('streamers.html')


@bp.get('/api/live/catalogue')
def public_directory():
    from operations import premiere
    if premiere():return jsonify(video_ready=False,channels=[],categories=LIVE_CATEGORIES,premiere=True)
    with database() as conn:
        rows=conn.execute('SELECT c.*,m.username,o.category,o.featured,f.number AS founder_number,sg.mode AS badge_mode,sg.letter AS badge_letter,sg.caption AS badge_caption,sg.audio_json AS badge_audio FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN live_channel_settings o ON o.channel_id=c.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN founder_signatures sg ON sg.member_id=m.id WHERE c.live_until>? ORDER BY COALESCE(o.featured,0) DESC,c.updated_at DESC LIMIT 100',(stamp(now_utc()),)).fetchall()
    from subscriptions import decorate
    return jsonify(video_ready=live_ready(),channels=decorate([channel_public(row) for row in rows if not is_abusive(row['title']+' '+row['bio']+' '+row['username'])]),categories=LIVE_CATEGORIES)


@bp.get('/api/admin/live-channels')
def admin_live_channels():
    from membership import require_admin
    return require_admin(_admin_live_channels)()


def _admin_live_channels():
    try:page=max(1,int(request.args.get('page','1')))
    except ValueError:page=1
    with database() as conn:
        total=conn.execute('SELECT COUNT(*) AS n FROM streamer_channels').fetchone()['n'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT c.*,m.username,o.category,o.featured,f.number AS founder_number,sg.mode AS badge_mode,sg.letter AS badge_letter,sg.caption AS badge_caption,sg.audio_json AS badge_audio FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN live_channel_settings o ON o.channel_id=c.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN founder_signatures sg ON sg.member_id=m.id ORDER BY c.updated_at DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
    return jsonify(channels=[channel_public(row) for row in rows],page=page,pages=pages,total=total,categories=LIVE_CATEGORIES)


@bp.post('/api/admin/live-channels/feature')
def feature_channel():
    from membership import require_admin
    return require_admin(_feature_channel)()


def _feature_channel():
    data=request.get_json(silent=True) or {}
    if not isinstance(data.get('featured'),bool):return jsonify(error='Indica si deseas destacar el canal.'),400
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT id FROM streamer_channels WHERE id=?',(str(data.get('channel_id','')),)).fetchone():return jsonify(error='El canal no existe.'),404
        conn.execute("INSERT INTO live_channel_settings(channel_id,category,featured) VALUES(?,'entretenimiento',?) ON CONFLICT(channel_id) DO UPDATE SET featured=excluded.featured",(data['channel_id'],int(data['featured'])))
    return jsonify(ok=True)


@bp.get('/api/streamers')
def channels():
    user=get_user()
    with database() as conn:
        rows=conn.execute('SELECT c.*,m.username,o.category,o.featured,f.number AS founder_number,sg.mode AS badge_mode,sg.letter AS badge_letter,sg.caption AS badge_caption,sg.audio_json AS badge_audio FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN live_channel_settings o ON o.channel_id=c.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN founder_signatures sg ON sg.member_id=m.id WHERE c.live_until>? ORDER BY COALESCE(o.featured,0) DESC,c.updated_at DESC LIMIT 60',(stamp(now_utc()),)).fetchall()
    own=own_channel()
    from subscriptions import decorate
    return jsonify(video_ready=live_ready(),streamer_active=publisher_allowed(),live_price_cents=2500,live_trial_months=0,live_trial_days=7,gift_commission_bps=0,
                   channels=decorate([channel_public(row) for row in rows if not is_abusive(row['title']+' '+row['bio']+' '+row['username'])]),mine=channel_public(own) if own else None,
                   user={'id':user['id'],'username':user['username']},
                   setup_checks=video_configuration_checks() if user['role']=='admin' else None,
                   streamer_sales_available=streamer_sales_ready(),
                   setup_environment=os.getenv('VERCEL_ENV','local') if user['role']=='admin' else None)


@bp.post('/api/streamers/me')
def save_channel():
    if not publisher_allowed(): return jsonify(error='Activa tu prueba de Ol Livis o revisa tu acceso completo desde tu cuenta.'),403
    data=request.get_json(silent=True) or {}
    title=str(data.get('title','')).strip();bio=str(data.get('bio','')).strip();category=data.get('category','entretenimiento')
    if category not in LIVE_CATEGORIES:return jsonify(error='Elige una categoría válida para Ol Livis.'),400
    if not 3<=len(title)<=80 or len(bio)>400: return jsonify(error='Indica un título de 3 a 80 caracteres y una presentación de hasta 400.'),400
    try: validate_public_text(title+' '+bio)
    except ValueError as exc: return jsonify(error=str(exc)),400
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
        own=conn.execute('SELECT id FROM streamer_channels WHERE member_id=?',(user['id'],)).fetchone()
        conn.execute('INSERT INTO live_channel_settings(channel_id,category) VALUES(?,?) ON CONFLICT(channel_id) DO UPDATE SET category=excluded.category',(own['id'],category))
    return jsonify(ok=True,channel=channel_public(own_channel()))


@bp.post('/api/streamers/<channel_id>/token')
def token(channel_id):
    if not live_ready(): return jsonify(error='Las emisiones todavía no están activadas. No se ha cobrado ningún alta de Ol Livis Creador.',code='live_not_configured'),503
    with database() as conn:
        channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
    if channel and is_abusive(channel['title']+' '+channel['bio']): return jsonify(error='El canal debe corregir su título o presentación antes de emitir.'),409
    if not channel: return jsonify(error='Este canal no existe.'),404
    publish=(request.get_json(silent=True) or {}).get('publish') is True
    user=get_user()
    if publish and (channel['member_id']!=user['id'] or not publisher_allowed()): return jsonify(error='Solo el creador con plan Ol Livis Creador activo puede emitir en este canal.'),403
    if not publish and not (channel['live_until'] and channel['live_until']>stamp(now_utc())): return jsonify(error='Este canal no está en directo.'),404
    if not publish:
        from subscriptions import watch_allowed
        with database() as conn:
            if not watch_allowed(conn,channel,user):return jsonify(error='Este directo está reservado a suscriptores del creador.',code='creator_subscription_required'),403
    return jsonify(url=os.environ['LIVEKIT_URL'].strip(),token=mint_token(user,channel,publish))


@bp.post('/api/streamers/me/live')
def presence():
    if not publisher_allowed(): return jsonify(error='Tu plan Ol Livis Creador no está activo.'),403
    live=(request.get_json(silent=True) or {}).get('live') is True
    if live and not live_ready(): return jsonify(error='Las emisiones no están activadas.'),503
    channel=own_channel()
    if live:
        from live_access import verified_broadcast
        if not channel or not verified_broadcast(channel,get_user()):return jsonify(error='No hemos podido verificar una emisión de vídeo en LiveKit. Tu tiempo aún no se acredita.'),409
    with database() as conn:
        conn.execute('UPDATE streamer_channels SET live_until=?,updated_at=? WHERE member_id=?',
                     (stamp(now_utc()+timedelta(seconds=75)) if live else None,stamp(now_utc()),get_user()['id']))
        if live:
            from live_access import credit_activity
            credit_activity(conn,get_user()['id'])
        else:conn.execute('UPDATE founder_activity SET last_verified_at=NULL,session_seconds=0 WHERE member_id=?',(get_user()['id'],))
    return jsonify(ok=True)


@bp.post('/api/streamers/<channel_id>/gift-link')
def gift_link(channel_id):
    from payments import provider
    if provider()=='stripe':return jsonify(error='Los regalos y pagos externos no están disponibles.'),410
    amount=(request.get_json(silent=True) or {}).get('amount_cents')
    if isinstance(amount,bool) or not isinstance(amount,int) or not 100<=amount<=100000: return jsonify(error='Introduce entre 1 y 1.000 €, con un máximo de dos decimales.'),400
    with database() as conn:
        row=conn.execute('SELECT c.*,m.username,m.role,m.access_until,s.until_at AS streamer_until,f.number AS founder_number,f.revoked_at AS founder_revoked_at,e.trial_until AS live_trial_until,e.paid_at AS live_paid_at,e.revoked_at AS live_revoked_at FROM streamer_channels c JOIN members m ON m.id=c.member_id LEFT JOIN streamer_access s ON s.member_id=m.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN live_entitlements e ON e.member_id=m.id WHERE c.id=?',(channel_id,)).fetchone()
    if not row or not row['paypal_url']: return jsonify(error='Este creador no tiene enlace para recibir regalos.'),404
    founder_ok=False
    if row['founder_number'] and not row['founder_revoked_at']:
        from live_access import founder_activity
        with database() as conn:founder_ok=founder_activity(row['member_id'],conn)['eligible']
    active_creator=row['role']=='admin' or founder_ok or bool(not row['live_revoked_at'] and (row['live_paid_at'] or (row['live_trial_until'] and row['live_trial_until']>stamp(now_utc())))) or bool(row['access_until'] and row['access_until']>stamp(now_utc()) and row['streamer_until'] and row['streamer_until']>stamp(now_utc()))
    if not active_creator: return jsonify(error='Este canal no tiene plan Ol Livis Creador activo.'),409
    return jsonify(url=paypal_link(row['paypal_url'])+f'/{amount//100}.{amount%100:02d}EUR',creator=row['username'],amount_cents=amount,
                   maggy_commission_cents=0,mode='external_paypal_link',payment_confirmed=False)


def install(app,rate_limiter=None):
    if rate_limiter: app.extensions['streamer_rate_limiter']=rate_limiter
    with app.app_context(): init_database()
    app.register_blueprint(bp)
