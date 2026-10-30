"""Member-only live comments, text moderation and private transcript review."""
import secrets,re,json
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
        CREATE TABLE IF NOT EXISTS community_likes(message_id TEXT NOT NULL REFERENCES community_messages(id) ON DELETE CASCADE,member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,PRIMARY KEY(message_id,member_id)); CREATE TABLE IF NOT EXISTS community_report_details(message_id TEXT PRIMARY KEY REFERENCES community_messages(id) ON DELETE CASCADE,snapshot_json TEXT NOT NULL); CREATE INDEX IF NOT EXISTS community_retention ON community_messages(created_at); CREATE INDEX IF NOT EXISTS community_live_feed ON community_messages(channel_id,blocked,created_at,id); CREATE INDEX IF NOT EXISTS community_member_time ON community_messages(member_id,created_at); CREATE TABLE IF NOT EXISTS community_retention_clock (id INTEGER PRIMARY KEY,last_run TEXT NOT NULL)''')
    from subscriptions import init_database as init_subscriptions
    init_subscriptions()


def purge(conn):
    instant=stamp(now_utc())
    conn.execute("INSERT INTO community_retention_clock(id,last_run) VALUES(1,'') ON CONFLICT(id) DO NOTHING")
    changed=conn.execute('UPDATE community_retention_clock SET last_run=? WHERE id=1 AND last_run<?',(instant,stamp(now_utc()-timedelta(hours=1))))
    if not changed.rowcount:return
    conn.execute('DELETE FROM community_messages WHERE created_at<?',(stamp(now_utc()-timedelta(days=RETENTION_DAYS)),))


def live_channel(conn,ident):
    return conn.execute('SELECT * FROM streamer_channels WHERE id=? AND live_until>?',(ident,stamp(now_utc()))).fetchone()


@bp.get('/api/streamers/<channel_id>/comments')
def comments(channel_id):
    cursor=request.args.get('after','')
    after_time,separator,after_id=cursor.partition('|')
    if cursor and (len(cursor)>120 or not separator or not re.fullmatch(r'[a-f0-9]{32}',after_id)):
        return jsonify(error='Cursor de comentarios no válido.'),400
    with database() as conn:
        channel=live_channel(conn,channel_id)
        if not channel:return jsonify(error='Este canal no está en directo.'),404
        from age_policy import gate
        restricted=gate(conn,channel_id,get_user())
        if restricted:return restricted
        from subscriptions import chat_allowed,settings,watch_allowed
        user=get_user()
        if not watch_allowed(conn,channel,user):return jsonify(error='Este directo está reservado a suscriptores del creador.'),403
        private_access=chat_allowed(conn,channel,user);mode=settings(conn,channel_id)
        broadcast=conn.execute('SELECT started_at FROM live_broadcast_sessions WHERE channel_id=?',(channel_id,)).fetchone()
        since=broadcast['started_at'] if broadcast else stamp(now_utc()-timedelta(days=RETENTION_DAYS))
        if request.args.get('session_start') not in {None,since}:cursor='';after_time='';after_id=''
        rows=conn.execute("SELECT (SELECT COUNT(*) FROM community_likes l WHERE l.message_id=c.id) AS likes,(SELECT COUNT(*) FROM community_likes l WHERE l.message_id=c.id AND l.member_id=?) AS liked,c.id,c.member_id,c.body,c.kind,c.created_at,m.username,COALESCE(NULLIF(p.nickname,''),m.username) AS display_name,fa.alias AS fan_alias,f.number AS founder_number,sg.mode AS badge_mode,sg.letter AS badge_letter,sg.caption AS badge_caption FROM community_messages c JOIN members m ON m.id=c.member_id LEFT JOIN member_profiles p ON p.member_id=m.id LEFT JOIN fan_aliases fa ON fa.member_id=m.id LEFT JOIN live_founders f ON f.member_id=m.id LEFT JOIN founder_signatures sg ON sg.member_id=m.id WHERE c.channel_id=? AND c.created_at>=? AND (c.created_at>? OR (c.created_at=? AND c.id>?)) AND c.kind IN ('comment','sticker') AND c.blocked=0 AND (?=1 OR NOT EXISTS(SELECT 1 FROM community_audiences a WHERE a.message_id=c.id AND a.audience='subscribers')) ORDER BY c.created_at DESC,c.id DESC LIMIT 101",(user['id'],channel_id,since,after_time,after_time,after_id,int(private_access))).fetchall()
        reactions=[dict(r) for r in conn.execute("SELECT c.id,(SELECT COUNT(*) FROM community_likes l WHERE l.message_id=c.id) AS likes,(SELECT COUNT(*) FROM community_likes l WHERE l.message_id=c.id AND l.member_id=?) AS liked FROM community_messages c WHERE c.channel_id=? AND c.created_at>=? AND c.blocked=0 AND c.kind IN ('comment','sticker') AND (?=1 OR NOT EXISTS(SELECT 1 FROM community_audiences a WHERE a.message_id=c.id AND a.audience='subscribers')) ORDER BY c.created_at DESC,c.id DESC LIMIT 100",(user['id'],channel_id,since,int(private_access))).fetchall()]
        truncated=len(rows)>100;rows=rows[:100]
        authors=list({row['member_id'] for row in rows})
        badge_members={row['member_id'] for row in conn.execute("SELECT DISTINCT member_id FROM creator_subscriptions WHERE channel_id=? AND revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?) AND benefits_json LIKE ? AND member_id IN ("+','.join('?' for _ in authors)+")",(channel_id,stamp(now_utc()),stamp(now_utc()),'%"badge"%',*authors)).fetchall()} if authors else set()
    from rewards import catalog
    designs={item['id']:item for item in catalog(0)} if any(row['kind']=='sticker' for row in rows) else {}
    comments=[dict(row) for row in reversed(rows)]
    for comment in comments:
        comment['subscriber_badge']=comment.pop('member_id') in badge_members
        if comment.get('founder_number'):
            from founders import signature_from_row
            comment['founder_signature']=signature_from_row(comment)
        for key in ['badge_mode','badge_letter','badge_caption']:comment.pop(key,None)
        if comment['kind']=='sticker':comment['sticker']={key:designs[comment['body']][key] for key in ['id','name','image','phrase']} if comment['body'] in designs else None
    return jsonify(reactions=reactions,session_start=since,comments=comments,cursor=(rows[0]['created_at']+'|'+rows[0]['id']) if rows else cursor,truncated=truncated,subscriber_chat=bool(mode['subscriber_chat']),can_post=not mode['subscriber_chat'] or private_access)


@bp.post('/api/streamers/<channel_id>/comments')
def post_text(channel_id):
    data=request.get_json(silent=True) or {};kind=data.get('kind','comment');body=data.get('text')
    if kind not in {'comment','transcript','report','sticker'} or not isinstance(body,str) or not 1<=len(body.strip())<=1000:
        return jsonify(error='Escribe un comentario o fragmento de hasta 1000 caracteres.'),400
    body=body.strip();user=get_user()
    if kind=='report':
        from membership import allow_attempt
        if not allow_attempt('community-report',limit=6):return jsonify(error='Has enviado varias denuncias. Espera antes de enviar otra.'),429
    report_snapshot=None
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone() if kind=='report' else live_channel(conn,channel_id)
        if not channel:return jsonify(error='Este canal no está en directo.'),404
        from age_policy import gate
        restricted=gate(conn,channel_id,get_user())
        if restricted and kind!='report':return restricted
        from subscriptions import chat_allowed,settings,watch_allowed
        if kind!='report' and not watch_allowed(conn,channel,user):return jsonify(error='Este directo está reservado a suscriptores del creador.'),403
        subscriber_only=bool(settings(conn,channel_id)['subscriber_chat'])
        if kind in {'comment','sticker'} and subscriber_only and not chat_allowed(conn,channel,user):return jsonify(error='Este chat está reservado a suscriptores del creador.'),403
        if kind=='transcript':
            from streamers import publisher_allowed
            if channel['member_id']!=user['id'] or not publisher_allowed():return jsonify(error='Solo el creador puede enviar la transcripción de su micrófono.'),403
        if kind=='sticker':
            from rewards import owns_sticker
            sticker=owns_sticker(conn,user['id'],body)
            if not sticker:return jsonify(error='Este sticker todavía no está desbloqueado en tu colección.'),403
        purge(conn)
        recent=conn.execute('SELECT COUNT(*) AS n FROM community_messages WHERE member_id=? AND created_at>?',(user['id'],stamp(now_utc()-timedelta(seconds=60)))).fetchone()['n']
        if recent>=60:return jsonify(error='Demasiados mensajes. Espera un momento.'),429
        category='report' if kind=='report' else classify(body);blocked=bool(category and kind!='report')
        ident=secrets.token_hex(16)
        conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,category,blocked,created_at) VALUES(?,?,?,?,?,?,?,?)',(ident,channel_id,user['id'],kind,body,category,int(blocked),stamp(now_utc())))
        if kind=='report':
            sent=conn.execute("SELECT COUNT(*) AS n FROM community_messages WHERE member_id=? AND kind='report' AND created_at>?",(user['id'],stamp(now_utc()-timedelta(minutes=15)))).fetchone()['n']
            if sent>=6:return jsonify(error='Espera antes de enviar más denuncias.'),429
            target=None;target_id=data.get('target_message_id')
            if target_id:
                target=conn.execute('SELECT id,member_id,body,kind,created_at FROM community_messages WHERE id=? AND channel_id=? AND kind IN (?,?)',(str(target_id),channel_id,'comment','sticker')).fetchone()
                if not target:return jsonify(error='El comentario señalado no existe en este canal.'),400
            def person(member_id):
                row=conn.execute("SELECT m.id,m.username,COALESCE(p.nickname,m.username) AS nickname,CASE WHEN p.email_verified=1 THEN p.email ELSE NULL END AS verified_email FROM members m LEFT JOIN member_profiles p ON p.member_id=m.id WHERE m.id=?",(member_id,)).fetchone()
                return dict(row) if row else {'id':member_id}
            report_snapshot={'reporter':person(user['id']),'reported':person(target['member_id'] if target else channel['member_id']),'channel_id':channel_id,'channel_title':channel['title'],'reason':body,'at':stamp(now_utc()),'message':dict(target) if target else None}
            report_snapshot['recordings']=[dict(r) for r in conn.execute("SELECT id,state,started_at,expires_at FROM live_recordings WHERE channel_id=? AND expires_at>? ORDER BY started_at DESC LIMIT 5",(channel_id,stamp(now_utc()))).fetchall()]
        if subscriber_only and kind in {'comment','sticker'}:conn.execute('INSERT INTO community_audiences(message_id,audience) VALUES(?,?)',(ident,'subscribers'))
        if report_snapshot:conn.execute('INSERT INTO community_report_details(message_id,snapshot_json) VALUES(?,?)',(ident,json.dumps(report_snapshot,ensure_ascii=False)))
        strikes=conn.execute("SELECT COUNT(*) AS n FROM community_messages WHERE channel_id=? AND member_id=? AND blocked=1 AND created_at>?",(channel_id,user['id'],stamp(now_utc()-timedelta(hours=24)))).fetchone()['n']
    mail_sent=False
    if report_snapshot:
        detail='Denuncia '+ident+'\n'+json.dumps(report_snapshot,ensure_ascii=False,indent=2)+'\n\nConsulta privada: https://electronicama.com/account#moderation-history\nGrabaciones: https://electronicama.com/account#live-recordings-admin\nNo se ha confirmado una infracción: requiere revisión administrativa.'
        mail_sent=bool(notify('moderation','Nueva denuncia · '+ident[:8],detail,event_key='community-report:'+ident,member_ids=[user['id'],channel['member_id'],report_snapshot['reported']['id']]))
    elif blocked:notify('moderation','Aviso de moderación','Hay un nuevo aviso en un directo. Revisa el contexto en administración.',member_ids=[user['id'],channel['member_id']])
    warning=('Aviso de moderación: se ha detectado una expresión no permitida. La reiteración puede dar lugar a suspensión tras revisión de administración.' if strikes<3 else 'Avisos reiterados: el caso queda señalado para revisión de una posible suspensión por administración.') if blocked else ''
    return jsonify(report_id=ident if report_snapshot else None,mail_sent=mail_sent,accepted=not blocked,blocked=blocked,warning=warning,warnings_24h=strikes,review_required=bool(blocked and (strikes>=3 or category in {'sexual_minors','threat','illicit_trade'})),reported=kind=='report')


@bp.get('/api/admin/moderation')
@require_admin
def moderation_log():
    try:page=max(1,int(request.args.get('page','1')))
    except ValueError:page=1
    flagged=request.args.get('flagged','1')!='0'
    where="WHERE c.category!=''" if flagged else ''
    with database() as conn:
        purge(conn);total=conn.execute('SELECT COUNT(*) AS n FROM community_messages c '+where).fetchone()['n'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT c.id,c.kind,c.body,c.category,c.blocked,c.created_at,m.username,s.title AS channel,d.snapshot_json FROM community_messages c JOIN members m ON m.id=c.member_id JOIN streamer_channels s ON s.id=c.channel_id LEFT JOIN community_report_details d ON d.message_id=c.id '+where+' ORDER BY c.created_at DESC,c.id DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
    records=[]
    for row in rows:
        record=dict(row);snapshot=record.pop('snapshot_json',None)
        record['report']=json.loads(snapshot) if snapshot else None;records.append(record)
    return jsonify(records=records,total=total,page=page,pages=pages,retention_days=RETENTION_DAYS)


@bp.post('/api/admin/community-role')
@require_admin
def set_community_role():
    from membership import payload
    data=payload();role=data.get('community_role');ident=data.get('member_id')
    if role not in {'activo','voluntario','docente'} or not isinstance(ident,str):return jsonify(error='Rol de comunidad no válido.'),400
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        target=conn.execute('SELECT id FROM members WHERE id=?',(ident,)).fetchone()
        if not target:return jsonify(error='La cuenta no existe.'),404
        conn.execute('INSERT INTO community_roles VALUES(?,?,?,?) ON CONFLICT(member_id) DO UPDATE SET community_role=excluded.community_role,approved_by=excluded.approved_by,updated_at=excluded.updated_at',(ident,role,get_user()['id'],stamp(now_utc())))
    return jsonify(ok=True,community_role=role,administrative_permissions_changed=False)

@bp.post('/api/account/annual/cancel')
def cancel_annual():
    from membership import user_public
    user=get_user()
    if not user:return jsonify(error='Inicia sesión.'),401
    if not user_public(user).get('live_annual'):return jsonify(error='No tienes un periodo anual vigente.'),409
    with database() as conn:
        conn.execute('INSERT INTO annual_preferences VALUES(?,?) ON CONFLICT(member_id) DO NOTHING',(user['id'],stamp(now_utc())))
    return jsonify(ok=True,access_until=user['access_until'],automatic_renewal=False,message='Cancelación registrada. Conservas el acceso hasta el vencimiento del año pagado. No habrá cargos automáticos.')


def install(app):app.register_blueprint(bp)

@bp.post('/api/streamers/<channel_id>/comments/<message_id>/like')
def like_comment(channel_id,message_id):
    user=get_user();data=request.get_json(silent=True) or {}
    from membership import allow_attempt
    if not allow_attempt('community-like',limit=120):return jsonify(error='Demasiadas reacciones seguidas. Espera un momento.'),429
    if not isinstance(data.get('liked'),bool):return jsonify(error='Indica si deseas dar o retirar Me gusta.'),400
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE');channel=live_channel(conn,channel_id)
        if not channel:return jsonify(error='El directo ha terminado.'),404
        from age_policy import gate
        restricted=gate(conn,channel_id,user)
        if restricted:return restricted
        from subscriptions import watch_allowed,chat_allowed
        if not watch_allowed(conn,channel,user):return jsonify(error='No tienes acceso a este directo.'),403
        message=conn.execute("SELECT * FROM community_messages WHERE id=? AND channel_id=? AND blocked=0 AND kind IN ('comment','sticker')",(message_id,channel_id)).fetchone()
        start=conn.execute('SELECT started_at FROM live_broadcast_sessions WHERE channel_id=?',(channel_id,)).fetchone()
        if not message or (start and message['created_at']<start['started_at']):return jsonify(error='Comentario no disponible en esta emisión.'),404
        private=conn.execute("SELECT 1 FROM community_audiences WHERE message_id=? AND audience='subscribers'",(message_id,)).fetchone()
        if private and not chat_allowed(conn,channel,user):return jsonify(error='Comentario privado.'),403
        if data['liked']:conn.execute('INSERT INTO community_likes(message_id,member_id) VALUES(?,?) ON CONFLICT(message_id,member_id) DO NOTHING',(message_id,user['id']))
        else:conn.execute('DELETE FROM community_likes WHERE message_id=? AND member_id=?',(message_id,user['id']))
        count=conn.execute('SELECT COUNT(*) AS n FROM community_likes WHERE message_id=?',(message_id,)).fetchone()['n']
    return jsonify(likes=count,liked=data['liked'])
