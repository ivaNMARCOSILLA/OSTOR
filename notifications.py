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


def notify(kind,title,detail,event_key=None):
    from membership import database,now_utc,stamp
    ident=secrets.token_hex(16)
    with database() as conn:
        conn.execute('INSERT INTO admin_notifications(id,kind,title,detail,event_key,created_at,status,attempts) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO NOTHING',(ident,kind,title,detail,event_key,stamp(now_utc()),'pending',0))
    send_one(ident)


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
    return jsonify(notifications=[dict(row) for row in rows],total=total,page=page,pages=pages,pending=pending,email_ready=mail_ready(),recipient=RECIPIENT)


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


def install(app):app.register_blueprint(bp)
