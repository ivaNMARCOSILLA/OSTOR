"""Short-lived presence and factual administrator aggregates, without address tracking."""
import secrets
from datetime import timedelta
from flask import Blueprint, current_app, jsonify, request
from itsdangerous import URLSafeSerializer, URLSafeTimedSerializer, BadSignature
from membership import database, get_user, now_utc, stamp, require_admin

bp = Blueprint('analytics', __name__)
WINDOW = 90
COOKIE = 'ol_presence'


def online(conn):
    cutoff = stamp(now_utc() - timedelta(seconds=WINDOW))
    row = conn.execute('SELECT COUNT(DISTINCT member_id) AS members,COUNT(DISTINCT CASE WHEN member_id IS NULL THEN visitor_id END) AS guests FROM online_presence WHERE seen_at>?', (cutoff,)).fetchone()
    return dict(total=row['members']+row['guests'], members=row['members'], guests=row['guests'], window_seconds=WINDOW)


def forget_presence():
    try:
        ident=URLSafeSerializer(current_app.secret_key,salt='ol-presence').loads(request.cookies.get(COOKIE,''))
        if isinstance(ident,str) and len(ident)==32:
            with database() as conn:conn.execute('DELETE FROM online_presence WHERE visitor_id=?',(ident,))
    except BadSignature:pass


@bp.post('/api/presence')
def heartbeat():
    data=request.get_json(silent=True) or {}
    if not isinstance(data,dict) or data.get('consent') is not True or request.headers.get('Sec-GPC')=='1' or request.headers.get('DNT')=='1':
        forget_presence();response=jsonify(recorded=False,reason='consent_required');response.delete_cookie(COOKIE);return response
    limiter = current_app.extensions.get('streamer_rate_limiter')
    if limiter and not limiter('presence', 120):
        return jsonify(error='Espera un momento para actualizar el contador.'), 429
    signer = URLSafeSerializer(current_app.secret_key, salt='ol-presence')
    try:
        ident = signer.loads(request.cookies.get(COOKIE, ''))
        if not isinstance(ident, str) or len(ident) != 32: raise BadSignature('identity')
    except BadSignature:
        ident = secrets.token_hex(16)
    user = get_user()
    instant = now_utc()
    with database() as conn:
        conn.execute('DELETE FROM online_presence WHERE seen_at<=?', (stamp(instant-timedelta(seconds=WINDOW)),))
        conn.execute('INSERT INTO online_presence(visitor_id,member_id,seen_at) VALUES(?,?,?) ON CONFLICT(visitor_id) DO UPDATE SET member_id=excluded.member_id,seen_at=excluded.seen_at', (ident, user['id'] if user else None, stamp(instant)))
        result = online(conn)
    response = jsonify(result if user and user['role']=='admin' else {'recorded':True})
    response.set_cookie(COOKIE, signer.dumps(ident), max_age=86400, httponly=True,
                        secure=current_app.config['SESSION_COOKIE_SECURE'], samesite='Lax')
    return response


@bp.get('/api/admin/statistics')
@require_admin
def statistics():
    from founder_slots import cleanup
    cleanup()
    instant = now_utc()
    month = stamp(instant.replace(day=1,hour=0,minute=0,second=0))
    with database() as conn:
        available="NOT EXISTS (SELECT 1 FROM member_archives a WHERE a.member_id=m.id AND a.restored_at IS NULL)"
        counts = conn.execute("SELECT COUNT(*) AS registered,COALESCE(SUM(CASE WHEN m.created_at>=? THEN 1 ELSE 0 END),0) AS new_week,COALESCE(SUM(CASE WHEN m.access_until>? THEN 1 ELSE 0 END),0) AS paid_active FROM members m WHERE m.role!='admin' AND COALESCE(m.password_hash,'')!='' AND "+available, (stamp(instant-timedelta(days=7)), stamp(instant))).fetchone()
        payments = conn.execute('SELECT COUNT(*) AS count,COALESCE(SUM(amount_cents),0) AS total_cents,COALESCE(SUM(CASE WHEN verified_at>=? THEN amount_cents ELSE 0 END),0) AS month_cents FROM payments', (month,)).fetchone()
        founders = conn.execute('SELECT COUNT(*) AS n FROM live_founders f JOIN members m ON m.id=f.member_id WHERE f.revoked_at IS NULL AND '+available).fetchone()['n']
        friends = conn.execute("SELECT COUNT(*) AS n FROM friend_access f JOIN members m ON m.id=f.member_id WHERE f.revoked_at IS NULL AND COALESCE(m.password_hash,'')!='' AND "+available).fetchone()['n']
        live = conn.execute('SELECT COUNT(*) AS n FROM streamer_channels c JOIN members m ON m.id=c.member_id WHERE c.live_until>? AND '+available, (stamp(instant),)).fetchone()['n']
        channels = conn.execute('SELECT COUNT(*) AS n FROM streamer_channels c JOIN members m ON m.id=c.member_id WHERE '+available).fetchone()['n']
        pending = conn.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE status IN ('pending','failed')").fetchone()['n']
        start = instant.replace(hour=0,minute=0,second=0)-timedelta(days=6)
        registrations = conn.execute("SELECT SUBSTR(m.created_at,1,10) AS day,COUNT(*) AS n FROM members m WHERE m.role!='admin' AND COALESCE(m.password_hash,'')!='' AND m.created_at>=? AND "+available+" GROUP BY SUBSTR(m.created_at,1,10)", (stamp(start),)).fetchall()
        revenue = conn.execute('SELECT SUBSTR(verified_at,1,10) AS day,COUNT(*) AS n,SUM(amount_cents) AS cents FROM payments WHERE verified_at>=? GROUP BY SUBSTR(verified_at,1,10)', (stamp(start),)).fetchall()
        promotion = conn.execute("SELECT event,SUM(amount) AS n FROM promotion_metrics GROUP BY event").fetchall()
        presence = online(conn)
    registrations = {row['day']:row['n'] for row in registrations}
    revenue = {row['day']:dict(row) for row in revenue}
    days = []
    for offset in range(7):
        day=(start+timedelta(days=offset)).date().isoformat(); paid=revenue.get(day,{})
        days.append(dict(day=day, registrations=registrations.get(day,0), payments=paid.get('n',0), cents=paid.get('cents',0)))
    return jsonify(online=presence, accounts=dict(counts), payments=dict(payments), founders=founders,
                   friends=friends, channels=channels, live=live, pending_notifications=pending,
                   days=days,promotion={row['event']:row['n'] for row in promotion}, updated_at=stamp(instant), timezone='UTC')


JOURNEY_COOKIE='electronicama_navigation'
JOURNEY_PAGES={'/','/live','/account','/legal/privacidad.html','/legal/cookies.html','/legal/aviso-legal.html'}
JOURNEY_TARGETS={'explorar','favoritos','historial','buscar-musica','reproducir-musica','guardar-favorito','reproducir-pausar','siguiente-cancion','anterior-cancion','ampliar-reproductor','cerrar-reproductor','crear-cuenta','iniciar-sesion','abrir-musica','abrir-ol-livis','abrir-cuenta','abrir-legal','abrir-fuente','fuente-audius','fuente-archive','fuente-youtube','fuente-mix','fuente-radio','ver-hologramas','abrir-estilos'}

def journey_identity():
    import hashlib
    signer=URLSafeTimedSerializer(current_app.secret_key,salt='guest-navigation-v1')
    try:raw=signer.loads(request.cookies.get(JOURNEY_COOKIE,''),max_age=1800)
    except BadSignature:raw=secrets.token_hex(16)
    if not isinstance(raw,str) or len(raw)!=32:raw=secrets.token_hex(16)
    return signer,raw,hashlib.sha256(raw.encode()).hexdigest()

@bp.post('/api/navigation/events')
def navigation_events():
    from membership import payload,allow_attempt
    import re
    data=payload()
    if get_user():
        response=jsonify(recorded=False,reason='signed_in');response.delete_cookie(JOURNEY_COOKIE);return response
    if data.get('consent') is not True or request.headers.get('Sec-GPC')=='1':return jsonify(recorded=False,reason='consent_required'),200
    events=data.get('events')
    if not isinstance(events,list) or not 1<=len(events)<=20:return jsonify(error='Lote de navegación no válido.'),400
    validated=[]
    for event in events:
        if not isinstance(event,dict) or event.get('page') not in JOURNEY_PAGES or event.get('kind') not in {'page','click'}:return jsonify(error='Evento no válido.'),400
        target=event.get('target','')
        if not isinstance(target,str) or (event['kind']=='click' and target not in JOURNEY_TARGETS) or (event['kind']=='page' and target):return jsonify(error='Destino no válido.'),400
        validated.append((event['kind'],event['page'],target))
    if not allow_attempt('guest-navigation',limit=120):return jsonify(error='Espera antes de enviar más eventos.'),429
    signer,raw,ident=journey_identity();instant=stamp(now_utc())
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        conn.execute('DELETE FROM guest_visits WHERE last_seen<?',(stamp(now_utc()-timedelta(days=7)),))
        previous=conn.execute('SELECT last_seen FROM guest_visits WHERE id=?',(ident,)).fetchone()
        if previous and previous['last_seen']<stamp(now_utc()-timedelta(minutes=30)):
            import hashlib
            raw=secrets.token_hex(16);ident=hashlib.sha256(raw.encode()).hexdigest()
        conn.execute('INSERT INTO guest_visits VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen',(ident,instant,instant))
        seq=conn.execute('SELECT COALESCE(MAX(sequence),0) AS n FROM guest_navigation_events WHERE visit_id=?',(ident,)).fetchone()['n']
        for kind,page,target in validated:
            if seq>=500:break
            seq+=1;conn.execute('INSERT INTO guest_navigation_events VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),ident,seq,kind,page,target,instant))
    response=jsonify(recorded=True)
    response.set_cookie(JOURNEY_COOKIE,signer.dumps(raw),max_age=1800,httponly=True,secure=current_app.config['SESSION_COOKIE_SECURE'],samesite='Lax')
    response.headers['Cache-Control']='no-store';return response

@bp.post('/api/navigation/consent')
def navigation_consent():
    from membership import payload
    if payload().get('allowed') is not False:return jsonify(error='Elección no válida.'),400
    _,_,ident=journey_identity()
    with database() as conn:conn.execute('DELETE FROM guest_visits WHERE id=?',(ident,))
    response=jsonify(ok=True);response.delete_cookie(JOURNEY_COOKIE);response.headers['Cache-Control']='no-store';return response

@bp.get('/api/admin/guest-journeys')
@require_admin
def guest_journeys():
    import re
    try:page=max(1,int(request.args.get('page',1)));event_page=max(1,int(request.args.get('event_page',1)))
    except ValueError:return jsonify(error='Página no válida.'),400
    ident=request.args.get('visit')
    if ident and not re.fullmatch('[a-f0-9]{64}',ident):return jsonify(error='Sesión no válida.'),400
    with database() as conn:
        conn.execute('DELETE FROM guest_visits WHERE last_seen<?',(stamp(now_utc()-timedelta(days=7)),))
        if ident:
            total=conn.execute('SELECT COUNT(*) AS n FROM guest_navigation_events WHERE visit_id=?',(ident,)).fetchone()['n']
            rows=conn.execute('SELECT sequence,kind,page,target,created_at FROM guest_navigation_events WHERE visit_id=? ORDER BY sequence LIMIT 50 OFFSET ?',(ident,(event_page-1)*50)).fetchall()
            return jsonify(visit=ident,events=[dict(row) for row in rows],page=event_page,pages=max(1,(total+49)//50),total=total)
        total=conn.execute('SELECT COUNT(*) AS n FROM guest_visits').fetchone()['n']
        rows=conn.execute('SELECT v.id,v.started_at,v.last_seen,COUNT(e.id) AS events FROM guest_visits v LEFT JOIN guest_navigation_events e ON e.visit_id=v.id GROUP BY v.id,v.started_at,v.last_seen ORDER BY v.last_seen DESC,v.id LIMIT 25 OFFSET ?',(25*(page-1),)).fetchall()
    return jsonify(visits=[dict(row) for row in rows],page=page,pages=max(1,(total+24)//25),total=total,retention_days=7,consented_only=True)


def install(app):
    app.register_blueprint(bp)

@bp.post('/api/promotion/event')
def promotion_event():
    from membership import payload,allow_attempt
    event=payload().get('event')
    if event not in {'shown','next','skip','complete'}:return jsonify(error='Evento no válido.'),400
    if not allow_attempt('promotion',60):return jsonify(error='Espera antes de volver a actualizar.'),429
    with database() as conn:
        conn.execute('INSERT INTO promotion_metrics(day,event,amount) VALUES(?,?,1) ON CONFLICT(day,event) DO UPDATE SET amount=promotion_metrics.amount+1',(now_utc().date().isoformat(),event))
    return jsonify(ok=True)
