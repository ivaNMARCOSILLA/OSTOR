"""Read-only participant records assembled from existing account data."""
from datetime import datetime, timezone
import re

from flask import Blueprint, jsonify, request

from membership import database, now_utc, require_admin, stamp, user_public


bp = Blueprint('participants', __name__)
PAGE_SIZE = 25
VIDEO_STATES = ('uploading', 'quarantined', 'published', 'rejected', 'failed', 'deleted')
BASE_FROM = '''FROM members m
 LEFT JOIN member_profiles p ON p.member_id=m.id
 LEFT JOIN member_archives a ON a.member_id=m.id
 LEFT JOIN streamer_access s ON s.member_id=m.id
 LEFT JOIN friend_access f ON f.member_id=m.id
 LEFT JOIN live_founders l ON l.member_id=m.id
 LEFT JOIN live_entitlements e ON e.member_id=m.id
 LEFT JOIN community_roles cr ON cr.member_id=m.id
 LEFT JOIN annual_preferences ap ON ap.member_id=m.id
 LEFT JOIN service_grants sg ON sg.member_id=m.id
 LEFT JOIN founder_activity fa ON fa.member_id=m.id
 LEFT JOIN founder_ownership fo ON fo.member_id=m.id'''
BASE_SELECT = '''SELECT m.id,m.username,m.role,m.created_at,m.access_until,m.welcome_used,
 CASE WHEN COALESCE(m.password_hash,'')='' THEN 0 ELSE 1 END AS account_activated,
 p.nickname,a.archived_at,a.restored_at,s.until_at AS streamer_until,
 f.granted_at AS friend_granted_at,f.revoked_at AS friend_revoked_at,
 l.number AS founder_number,l.revoked_at AS founder_revoked_at,
 e.trial_until AS live_trial_until,e.paid_at AS live_paid_at,e.revoked_at AS live_revoked_at,
 cr.community_role,ap.cancelled_at AS annual_cancelled_at,
 sg.granted_at AS service_granted_at,sg.revoked_at AS service_revoked_at,
 fa.total_seconds AS verified_seconds,fa.last_verified_at,fa.qualification_until,
 fo.number AS ownership_number,fo.revoked_at AS ownership_revoked_at,
 (SELECT MAX(seen_at) FROM online_presence op WHERE op.member_id=m.id) AS presence_seen_at,
 (SELECT MAX(last_seen) FROM visitor_sessions vs WHERE vs.member_id=m.id) AS consented_seen_at,
 (SELECT MIN(used_at) FROM invitations i WHERE i.member_id=m.id AND i.used_at IS NOT NULL) AS invitation_accepted_at,
 (SELECT COUNT(*) FROM invitations i WHERE i.member_id=m.id) AS invitation_count
 ''' + BASE_FROM


def instant(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def last_activity(row):
    candidates = [value for value in (row['presence_seen_at'], row['consented_seen_at'], row['last_verified_at']) if instant(value)]
    return max(candidates, key=instant) if candidates else None


def summary(row, conn):
    founder_state = None
    if row['founder_number']:
        from live_access import founder_activity
        founder_state = founder_activity(row['id'], conn)
    access = user_public(row, founder_state=founder_state)
    activated = bool(row['account_activated'])
    registered = row['invitation_accepted_at'] if activated else None
    if activated and not row['invitation_count']:
        registered = row['created_at']
    return {
        'id': row['id'], 'username': row['username'],
        'nickname': row['nickname'] or row['username'], 'role': row['role'],
        'created_at': row['created_at'], 'registered_at': registered,
        'account_activated': activated, 'archived': access['archived'],
        'last_activity_at': last_activity(row), 'access_active': access['active'],
        'streamer_active': access['streamer_active'], 'live_annual': access['live_annual'],
        'access_until': access['access_until'],
        'founder_number': row['ownership_number'] or row['founder_number'],
        'access': access,
    }


def private_json(**values):
    response = jsonify(values)
    response.headers['Cache-Control'] = 'no-store'
    return response


@bp.get('/api/admin/participants')
@require_admin
def listing():
    query = request.args.get('q', '').strip()
    archived = request.args.get('archived', '0')
    raw_page = request.args.get('page', '1')
    if len(query) > 120 or archived not in {'0', '1'} or not re.fullmatch(r'[1-9][0-9]{0,9}', raw_page):
        return jsonify(error='Revisa la búsqueda y la página de participantes.'), 400
    page = int(raw_page)
    conditions, params = [], []
    if archived == '0':
        conditions.append('(a.member_id IS NULL OR a.restored_at IS NOT NULL)')
    if query:
        pattern = '%' + query.casefold().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        conditions.append("(LOWER(m.username) LIKE ? ESCAPE '\\' OR LOWER(COALESCE(p.nickname,'')) LIKE ? ESCAPE '\\')")
        params.extend([pattern, pattern])
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with database() as conn:
        total = conn.execute('SELECT COUNT(*) AS n ' + BASE_FROM + where, params).fetchone()['n']
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        page = min(page, pages)
        rows = conn.execute(BASE_SELECT + where + ' ORDER BY m.created_at DESC,m.id DESC LIMIT ? OFFSET ?',
                            params + [PAGE_SIZE, (page - 1) * PAGE_SIZE]).fetchall()
        participants = [summary(row, conn) for row in rows]
    return private_json(participants=participants, total=total, page=page, pages=pages, page_size=PAGE_SIZE)


@bp.get('/api/admin/participants/<ident>')
@require_admin
def detail(ident):
    if not re.fullmatch(r'[a-f0-9]{32}', ident):
        return jsonify(error='Participante no encontrado.'), 404
    with database() as conn:
        row = conn.execute(BASE_SELECT + ' WHERE m.id=?', (ident,)).fetchone()
        if not row:
            return jsonify(error='Participante no encontrado.'), 404
        participant = summary(row, conn)
        channels = []
        for channel in conn.execute('SELECT id,title,live_until,updated_at FROM streamer_channels WHERE member_id=? ORDER BY updated_at DESC,id LIMIT 10', (ident,)).fetchall():
            item = dict(channel)
            item['live'] = bool(not participant['archived'] and channel['live_until'] and channel['live_until'] > stamp(now_utc()))
            channels.append(item)
        counts = dict.fromkeys(VIDEO_STATES, 0)
        for count in conn.execute('SELECT state,COUNT(*) AS n FROM community_videos WHERE owner_id=? GROUP BY state', (ident,)).fetchall():
            if count['state'] in counts:
                counts[count['state']] = count['n']
        video_rows = conn.execute('SELECT id,title,state,category,created_at,updated_at,published_at FROM community_videos WHERE owner_id=? ORDER BY created_at DESC,id DESC LIMIT 20', (ident,)).fetchall()
        videos = [dict(video) for video in video_rows]
        payments = [dict(payment) for payment in conn.execute('SELECT id,plan,amount_cents,starts_at,ends_at,verified_at FROM payments WHERE member_id=? ORDER BY verified_at DESC,id DESC LIMIT 10', (ident,)).fetchall()]
        ownership = None
        number = row['ownership_number'] or row['founder_number']
        if number:
            ownership = {'number': number, 'permanent': bool(row['ownership_number']),
                         'revoked': bool(row['ownership_revoked_at'] or row['founder_revoked_at'])}
        timeline = []

        def event(kind, label, at, description=''):
            if instant(at):
                timeline.append({'kind': kind, 'label': label, 'at': at, 'detail': description})

        event('account', 'Alta de la cuenta', row['created_at'])
        if participant['registered_at'] and participant['registered_at'] != row['created_at']:
            event('registration', 'Cuenta activada', participant['registered_at'])
        for payment in payments:
            event('payment', 'Pago verificado', payment['verified_at'],
                  str(payment['amount_cents'] / 100) + ' € · ' + payment['plan'])
        for change in conn.execute('SELECT former_username,new_username,changed_at FROM member_name_history WHERE member_id=? ORDER BY changed_at DESC,id DESC LIMIT 20', (ident,)).fetchall():
            event('rename', 'Usuario cambiado', change['changed_at'], change['former_username'] + ' → ' + change['new_username'])
        for change in conn.execute('SELECT action,created_at FROM member_archive_events WHERE member_id=? ORDER BY created_at DESC,id DESC LIMIT 20', (ident,)).fetchall():
            event('archive' if change['action'] == 'archive' else 'restore',
                  'Cuenta dada de baja' if change['action'] == 'archive' else 'Cuenta restaurada', change['created_at'])
        for video in videos:
            event('upload', 'Vídeo enviado', video['created_at'], video['title'])
        review_labels = {'published': 'Vídeo publicado', 'quarantined': 'Vídeo en cuarentena', 'rejected': 'Vídeo rechazado', 'deleted': 'Vídeo retirado'}
        for review in conn.execute('''SELECT r.new_state,r.created_at,v.title
            FROM community_video_reviews r JOIN community_videos v ON v.id=r.video_id
            WHERE v.owner_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT 20''', (ident,)).fetchall():
            event('video_review', review_labels.get(review['new_state'], 'Revisión de vídeo'), review['created_at'], review['title'])
        for access in conn.execute('SELECT event,result,created_at FROM security_login_events WHERE member_id=? ORDER BY created_at DESC,id DESC LIMIT 20', (ident,)).fetchall():
            labels = {'login_attempt':'Intento de acceso','email_code_verification':'Verificación del código','email_code_resend':'Reenvío del código','email_confirmation':'Verificación del correo','password_reset':'Restablecimiento de contraseña','logout':'Sesión cerrada'}
            results = {'success':'Completado','denied':'No autorizado','rate_limited':'Límite de seguridad','email_code_required':'Código de correo pendiente'}
            event('access', labels.get(access['event'], 'Evento de acceso'), access['created_at'], results.get(access['result'], access['result']))
        timeline.sort(key=lambda item: instant(item['at']), reverse=True)
    return private_json(participant=participant,
                        activity={'last_activity_at': participant['last_activity_at'],
                                  'verified_seconds': row['verified_seconds'],
                                  'last_verified_at': row['last_verified_at'],
                                  'qualification_until': row['qualification_until']},
                        founder_ownership=ownership, channels=channels,
                        videos={'counts': counts, 'latest': videos[:10]}, payments=payments,
                        timeline=timeline[:50])


def install(app):
    app.register_blueprint(bp)
