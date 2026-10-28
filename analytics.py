"""Short-lived presence and factual administrator aggregates, without address tracking."""
import secrets
from datetime import timedelta
from flask import Blueprint, current_app, jsonify, request
from itsdangerous import URLSafeSerializer, BadSignature
from membership import database, get_user, now_utc, stamp, require_admin

bp = Blueprint('analytics', __name__)
WINDOW = 90
COOKIE = 'ol_presence'


def online(conn):
    cutoff = stamp(now_utc() - timedelta(seconds=WINDOW))
    row = conn.execute('SELECT COUNT(DISTINCT member_id) AS members,COUNT(DISTINCT CASE WHEN member_id IS NULL THEN visitor_id END) AS guests FROM online_presence WHERE seen_at>?', (cutoff,)).fetchone()
    return dict(total=row['members']+row['guests'], members=row['members'], guests=row['guests'], window_seconds=WINDOW)


@bp.post('/api/presence')
def heartbeat():
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
    response = jsonify(result)
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
        counts = conn.execute("SELECT COUNT(*) AS registered,COALESCE(SUM(CASE WHEN created_at>=? THEN 1 ELSE 0 END),0) AS new_week,COALESCE(SUM(CASE WHEN access_until>? THEN 1 ELSE 0 END),0) AS paid_active FROM members WHERE role!='admin' AND COALESCE(password_hash,'')!=''", (stamp(instant-timedelta(days=7)), stamp(instant))).fetchone()
        payments = conn.execute('SELECT COUNT(*) AS count,COALESCE(SUM(amount_cents),0) AS total_cents,COALESCE(SUM(CASE WHEN verified_at>=? THEN amount_cents ELSE 0 END),0) AS month_cents FROM payments', (month,)).fetchone()
        founders = conn.execute('SELECT COUNT(*) AS n FROM live_founders WHERE revoked_at IS NULL').fetchone()['n']
        friends = conn.execute("SELECT COUNT(*) AS n FROM friend_access f JOIN members m ON m.id=f.member_id WHERE f.revoked_at IS NULL AND COALESCE(m.password_hash,'')!=''").fetchone()['n']
        live = conn.execute('SELECT COUNT(*) AS n FROM streamer_channels WHERE live_until>?', (stamp(instant),)).fetchone()['n']
        channels = conn.execute('SELECT COUNT(*) AS n FROM streamer_channels').fetchone()['n']
        pending = conn.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE status IN ('pending','failed')").fetchone()['n']
        start = instant.replace(hour=0,minute=0,second=0)-timedelta(days=6)
        registrations = conn.execute("SELECT SUBSTR(created_at,1,10) AS day,COUNT(*) AS n FROM members WHERE role!='admin' AND COALESCE(password_hash,'')!='' AND created_at>=? GROUP BY SUBSTR(created_at,1,10)", (stamp(start),)).fetchall()
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
