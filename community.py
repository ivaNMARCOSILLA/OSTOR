"""Member-only live comments, text moderation and private transcript review."""
import secrets
from datetime import timedelta
from flask import Blueprint, jsonify, request
from membership import database, get_user, now_utc, stamp, require_admin
from moderation import classify
from notifications import notify

bp=Blueprint('community',__name__)
RETENTION_DAYS=30


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS community_messages (
          id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES streamer_channels(id) ON DELETE CASCADE,
          member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
          kind TEXT NOT NULL,body TEXT NOT NULL,category TEXT NOT NULL DEFAULT '',blocked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL
        ); CREATE INDEX IF NOT EXISTS community_channel ON community_messages(channel_id,created_at);
        CREATE INDEX IF NOT EXISTS community_retention ON community_messages(created_at)''')


def purge(conn):
    conn.execute('DELETE FROM community_messages WHERE created_at<?',(stamp(now_utc()-timedelta(days=RETENTION_DAYS)),))


def live_channel(conn,ident):
    return conn.execute('SELECT * FROM streamer_channels WHERE id=? AND live_until>?',(ident,stamp(now_utc()))).fetchone()


@bp.get('/api/streamers/<channel_id>/comments')
def comments(channel_id):
    with database() as conn:
        if not live_channel(conn,channel_id):return jsonify(error='Este canal no está en directo.'),404
        purge(conn)
        rows=conn.execute("SELECT c.id,c.body,c.created_at,m.username FROM community_messages c JOIN members m ON m.id=c.member_id WHERE c.channel_id=? AND c.kind='comment' AND c.blocked=0 ORDER BY c.created_at DESC,c.id DESC LIMIT 50",(channel_id,)).fetchall()
    return jsonify(comments=[dict(row) for row in reversed(rows)])


@bp.post('/api/streamers/<channel_id>/comments')
def post_text(channel_id):
    data=request.get_json(silent=True) or {};kind=data.get('kind','comment');body=data.get('text')
    if kind not in {'comment','transcript','report'} or not isinstance(body,str) or not 1<=len(body.strip())<=1000:
        return jsonify(error='Escribe un comentario o fragmento de hasta 1000 caracteres.'),400
    body=body.strip();user=get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');channel=live_channel(conn,channel_id)
        if not channel:return jsonify(error='Este canal no está en directo.'),404
        if kind=='transcript':
            from streamers import publisher_allowed
            if channel['member_id']!=user['id'] or not publisher_allowed():return jsonify(error='Solo el creador puede enviar la transcripción de su micrófono.'),403
        purge(conn)
        recent=conn.execute('SELECT COUNT(*) AS n FROM community_messages WHERE member_id=? AND created_at>?',(user['id'],stamp(now_utc()-timedelta(seconds=60)))).fetchone()['n']
        if recent>=60:return jsonify(error='Demasiados mensajes. Espera un momento.'),429
        category='report' if kind=='report' else classify(body);blocked=bool(category and kind!='report')
        conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,category,blocked,created_at) VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),channel_id,user['id'],kind,body,category,int(blocked),stamp(now_utc())))
        strikes=conn.execute("SELECT COUNT(*) AS n FROM community_messages WHERE channel_id=? AND member_id=? AND blocked=1 AND created_at>?",(channel_id,user['id'],stamp(now_utc()-timedelta(hours=24)))).fetchone()['n']
    if blocked or kind=='report':notify('moderation','Aviso de moderación' if blocked else 'Nueva denuncia','Hay un nuevo aviso o denuncia en un directo. Revisa el contexto en administración; los correos no incluyen conversaciones completas.')
    warning=('Aviso de moderación: se ha detectado una expresión no permitida. La reiteración puede dar lugar a suspensión tras revisión de administración.' if strikes<3 else 'Avisos reiterados: el caso queda señalado para revisión de una posible suspensión por administración.') if blocked else ''
    return jsonify(accepted=not blocked,blocked=blocked,warning=warning,warnings_24h=strikes,review_required=bool(blocked and (strikes>=3 or category in {'sexual_minors','threat','illicit_trade'})),reported=kind=='report')


@bp.get('/api/admin/moderation')
@require_admin
def moderation_log():
    try:page=max(1,int(request.args.get('page','1')))
    except ValueError:page=1
    flagged=request.args.get('flagged','1')!='0'
    where="WHERE c.category!=''" if flagged else ''
    with database() as conn:
        purge(conn);total=conn.execute('SELECT COUNT(*) AS n FROM community_messages c '+where).fetchone()['n'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT c.id,c.kind,c.body,c.category,c.blocked,c.created_at,m.username,s.title AS channel FROM community_messages c JOIN members m ON m.id=c.member_id JOIN streamer_channels s ON s.id=c.channel_id '+where+' ORDER BY c.created_at DESC,c.id DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
    return jsonify(records=[dict(row) for row in rows],total=total,page=page,pages=pages,retention_days=RETENTION_DAYS)


def install(app):app.register_blueprint(bp)
