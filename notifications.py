"""Durable administrator notifications; mail delivery requires server-only credentials."""
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
import requests
from flask import Blueprint,jsonify,request

bp=Blueprint('notifications',__name__)
RECIPIENT='normalesoutro@gmail.com'


def mail_ready():
    return bool(os.getenv('OL_EMAIL_FROM') and (os.getenv('RESEND_API_KEY') or all(os.getenv(key) for key in ['SMTP_HOST','SMTP_USER','SMTP_PASSWORD'])))


def deliver_to(recipient,title,body):
    sender=os.environ['OL_EMAIL_FROM']
    if any('\n' in v or '\r' in v for v in [sender,recipient,title]):raise ValueError('mail header')
    if os.getenv('RESEND_API_KEY'):
        response=requests.post('https://api.resend.com/emails',headers={'Authorization':'Bearer '+os.environ['RESEND_API_KEY']},json={'from':sender,'to':[recipient],'subject':'electronicama · '+title,'text':body},timeout=(2,5))
        response.raise_for_status();return
    message=EmailMessage();message['From']=sender;message['To']=recipient;message['Subject']='electronicama · '+title
    message.set_content(body)
    host=os.environ['SMTP_HOST'];port=int(os.getenv('SMTP_PORT','465'));context=ssl.create_default_context()
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=5,context=context) as client:
            client.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);client.send_message(message)
    else:
        with smtplib.SMTP(host,port,timeout=5) as client:
            client.ehlo();client.starttls(context=context);client.ehlo();client.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD']);client.send_message(message)


def deliver(title,body):
    return deliver_to(RECIPIENT,title,body+'\n\nRevisa los detalles en https://electronicama.com/account')


def init_database():
    from membership import database
    with database() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS admin_notification_members (
          notification_id TEXT NOT NULL REFERENCES admin_notifications(id) ON DELETE CASCADE,
          member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
          PRIMARY KEY(notification_id,member_id)
        );
        """)


def _table_exists(conn,name):
    from storage import PostgresConnection
    if isinstance(conn,PostgresConnection):
        return bool(conn.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='maggy' AND table_name=?",(name,)).fetchone())
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())


def _notice_members(conn,row):
    linked={r['member_id'] for r in conn.execute('SELECT member_id FROM admin_notification_members WHERE notification_id=?',(row['id'],)).fetchall()}
    if linked:return linked
    # Recover old records using trusted identifiers, never the public nickname
    # or free text written by a user.
    prefix,separator,value=(row['event_key'] or '').partition(':')
    if not separator or not value:return set()
    if prefix in {'registration','invite','founder'}:
        return {value} if conn.execute('SELECT 1 FROM members WHERE id=?',(value,)).fetchone() else set()
    if prefix=='stripe-order' and _table_exists(conn,'stripe_orders'):
        order=conn.execute('SELECT member_id,channel_id FROM stripe_orders WHERE id=?',(value,)).fetchone()
        if not order:return set()
        subjects={order['member_id']}
        if order['channel_id'] and _table_exists(conn,'streamer_channels'):
            owner=conn.execute('SELECT member_id FROM streamer_channels WHERE id=?',(order['channel_id'],)).fetchone()
            if owner:subjects.add(owner['member_id'])
        return subjects
    if prefix=='creator-offer' and _table_exists(conn,'subscription_agreements'):
        agreement=conn.execute('SELECT creator_id FROM subscription_agreements WHERE id=?',(value,)).fetchone()
        return {agreement['creator_id']} if agreement else set()
    if prefix=='payment' and _table_exists(conn,'payments'):
        payment=conn.execute('SELECT member_id,verified_by FROM payments WHERE reference=?',(value,)).fetchone()
        return {payment['member_id'],payment['verified_by']} if payment else set()
    if prefix=='creator-receipt' and _table_exists(conn,'creator_subscriptions'):
        import hashlib
        for receipt in conn.execute('SELECT member_id,verified_by,reference FROM creator_subscriptions').fetchall():
            if hashlib.sha256(receipt['reference'].encode()).hexdigest()==value:
                return {receipt['member_id'],receipt['verified_by']}
    if prefix=='community-report':
        import json
        subjects=set()
        if _table_exists(conn,'community_messages'):
            message=conn.execute('SELECT member_id,channel_id FROM community_messages WHERE id=?',(value,)).fetchone()
            if message:
                subjects.add(message['member_id'])
                if _table_exists(conn,'streamer_channels'):
                    owner=conn.execute('SELECT member_id FROM streamer_channels WHERE id=?',(message['channel_id'],)).fetchone()
                    if owner:subjects.add(owner['member_id'])
        if _table_exists(conn,'community_report_details'):
            report=conn.execute('SELECT snapshot_json FROM community_report_details WHERE message_id=?',(value,)).fetchone()
            if report:
                try:snapshot=json.loads(report['snapshot_json'])
                except (TypeError,ValueError):snapshot={}
                if isinstance(snapshot,dict):
                    subjects.update(person['id'] for key in ('reporter','reported') if isinstance(person:=snapshot.get(key),dict) and isinstance(person.get('id'),str))
        return subjects
    return set()


def clear_history_except_flores(conn):
    """Caller holds BEGIN IMMEDIATE. Remove notification rows, never accounts."""
    keep=conn.execute('SELECT id FROM members WHERE username=?',('rosas',)).fetchone()
    if not keep:raise ValueError('No se encuentra la cuenta de Flores (rosas). No se ha borrado ningún aviso.')
    rows=conn.execute('SELECT id,event_key FROM admin_notifications').fetchall()
    deleted=retained=0
    for row in rows:
        if keep['id'] in _notice_members(conn,row):retained+=1
        else:
            deleted+=conn.execute('DELETE FROM admin_notifications WHERE id=?',(row['id'],)).rowcount
    return {'ok':True,'deleted':deleted,'retained':retained,'kept_username':'rosas','kept_label':'Flores'}


def apply_owner_history_cleanup():
    if os.getenv('VERCEL_ENV')!='production':return
    from membership import database,stamp,now_utc
    ident='owner-clear-notifications-except-rosas-2026-10-30'
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM owner_access_migrations WHERE id=?',(ident,)).fetchone():return
        try:
            result=clear_history_except_flores(conn)
            if result['deleted'] and _table_exists(conn,'interface_revisions'):
                conn.execute('INSERT INTO interface_revisions(topic,version) VALUES(?,?) ON CONFLICT(topic) DO UPDATE SET version=excluded.version',
                             ('account',secrets.token_hex(16)))
            result='deleted='+str(result['deleted'])+';retained='+str(result['retained'])
        except ValueError:result='skipped_missing_flores'
        conn.execute('INSERT INTO owner_access_migrations VALUES(?,?,?)',(ident,stamp(now_utc()),result))


def send_one(ident):
    if not mail_ready():return False
    from membership import database,now_utc,stamp
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute("SELECT * FROM admin_notifications WHERE id=? AND status IN ('pending','failed')",(ident,)).fetchone()
        if not row:return False
        conn.execute("UPDATE admin_notifications SET status='sending',attempts=attempts+1,last_attempt=? WHERE id=?",(stamp(now_utc()),ident))
    try:deliver(row['title'],row['detail'])
    except Exception:
        with database() as conn:conn.execute("UPDATE admin_notifications SET status='failed' WHERE id=?",(ident,))
        return False
    with database() as conn:conn.execute("UPDATE admin_notifications SET status='sent',sent_at=? WHERE id=?",(stamp(now_utc()),ident))
    return True


def notify(kind,title,detail,event_key=None,*,member_ids=()):
    from membership import database,now_utc,stamp
    ident=secrets.token_hex(16)
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        inserted=conn.execute('INSERT INTO admin_notifications(id,kind,title,detail,event_key,created_at,status,attempts) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING',(ident,kind,title,detail,event_key,stamp(now_utc()),'pending',0)).rowcount
        if not inserted:return False
        subjects=(member_ids,) if isinstance(member_ids,str) else member_ids or ()
        for member_id in list(subjects)[:16]:
            if isinstance(member_id,str) and conn.execute('SELECT 1 FROM members WHERE id=?',(member_id,)).fetchone():
                conn.execute('INSERT INTO admin_notification_members VALUES(?,?) ON CONFLICT(notification_id,member_id) DO NOTHING',(ident,member_id))
    return send_one(ident)


@bp.get('/api/admin/notifications')
def list_notifications():
    from membership import require_admin
    return require_admin(_list_notifications)()


def _list_notifications():
    from membership import database
    try:page=max(1,int(request.args.get('page','1')))
    except ValueError:page=1
    with database() as conn:
        total=conn.execute('SELECT COUNT(*) AS n FROM admin_notifications').fetchone()['n'];pages=max(1,(total+24)//25);page=min(page,pages)
        rows=conn.execute('SELECT id,kind,title,detail,created_at,status,attempts,sent_at FROM admin_notifications ORDER BY created_at DESC,id DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
        pending=conn.execute("SELECT COUNT(*) AS n FROM admin_notifications WHERE status!='sent'").fetchone()['n']
    return jsonify(notifications=[dict(row) for row in rows],total=total,page=page,pages=pages,pending=pending,email_ready=mail_ready(),recipient=RECIPIENT,history_keep={'username':'rosas','label':'Flores'})


@bp.post('/api/admin/notifications/retry')
def retry_notifications():
    from membership import require_admin
    return require_admin(_retry_notifications)()


def _retry_notifications():
    if not mail_ready():return jsonify(error='Configura OL_EMAIL_FROM y las credenciales privadas de SMTP o Resend en Vercel. Los avisos siguen guardados en el panel.'),409
    from membership import database,stamp,now_utc
    from datetime import timedelta
    with database() as conn:
        conn.execute("UPDATE admin_notifications SET status='failed' WHERE status='sending' AND last_attempt<?",(stamp(now_utc()-timedelta(minutes=5)),))
        rows=conn.execute("SELECT id FROM admin_notifications WHERE status IN ('pending','failed') ORDER BY created_at LIMIT 3").fetchall()
    from payments import send_annual_access_emails
    send_annual_access_emails()
    sent=sum(send_one(row['id']) for row in rows)
    return jsonify(sent=sent,attempted=len(rows))


@bp.post('/api/admin/notifications/clear')
def clear_notifications():
    from membership import require_admin
    return require_admin(_clear_notifications)()


def _clear_notifications():
    from membership import database,get_user
    actor=get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        fresh=conn.execute('SELECT role,session_version FROM members WHERE id=?',(actor['id'],)).fetchone()
        if not fresh or fresh['role']!='admin' or fresh['session_version']!=actor['session_version']:
            return jsonify(error='La sesión de administración ha cambiado. Vuelve a entrar.'),403
        try:result=clear_history_except_flores(conn)
        except ValueError as error:return jsonify(error=str(error)),409
    return jsonify(result)


def install(app):
    app.register_blueprint(bp)
    with app.app_context():init_database()
