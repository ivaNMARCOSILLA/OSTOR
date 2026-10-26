"""Private profiles, verified email and single-use password recovery; no automatic login."""
import hashlib,re,secrets
from datetime import timedelta
from flask import Blueprint,jsonify,session
from werkzeug.security import check_password_hash,generate_password_hash
from membership import database,get_user,payload,stamp,now_utc,validate_password,allow_attempt
from storage import INTEGRITY_ERRORS
from moderation import validate_public_text
from notifications import mail_ready,deliver_to
bp=Blueprint('email_security',__name__)
ORIGIN='https://electronicama.com'
GENERIC='Si ese correo está confirmado en Ol, recibirás un enlace para cambiar la contraseña. Revisa también spam.'

def clean_email(value):
 email=str(value or '').strip().lower()
 if not email:return None
 if len(email)>254 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}",email) or '..' in email.split('@')[0] or email.startswith('.') or email.split('@')[0].endswith('.'):
  raise ValueError('Escribe un correo electrónico válido, por ejemplo nombre@dominio.com.')
 return email

def clean_nickname(value):
 nickname=str(value or '').strip()
 if nickname and (not 2<=len(nickname)<=40 or any(ord(c)<32 for c in nickname)):raise ValueError('El apodo debe tener entre 2 y 40 caracteres.')
 validate_public_text(nickname)
 return nickname

def profile(c,member_id):
 row=c.execute('SELECT email,nickname,email_verified FROM member_profiles WHERE member_id=?',(member_id,)).fetchone()
 return dict(row) if row else {'email':None,'nickname':'','email_verified':0}

def issue(member_id,purpose):
 if not mail_ready():return False
 with database() as c:
  c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM email_tokens WHERE expires_at<=?',(stamp(now_utc()),));p=profile(c,member_id)
  if not p['email'] or (purpose=='reset' and not p['email_verified']):return False
  recent=c.execute('SELECT token_hash FROM email_tokens WHERE member_id=? AND purpose=? AND created_at>?',(member_id,purpose,stamp(now_utc()-timedelta(seconds=60)))).fetchone()
  if recent:return True
  user=c.execute('SELECT session_version FROM members WHERE id=?',(member_id,)).fetchone()
  token=secrets.token_urlsafe(32);hashed=hashlib.sha256(token.encode()).hexdigest();minutes=30 if purpose=='reset' else 1440
  c.execute('DELETE FROM email_tokens WHERE member_id=? AND purpose=?',(member_id,purpose))
  c.execute('INSERT INTO email_tokens(token_hash,member_id,purpose,email,session_version,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',(hashed,member_id,purpose,p['email'],user['session_version'],stamp(now_utc()),stamp(now_utc()+timedelta(minutes=minutes))))
 fragment='reset-password' if purpose=='reset' else 'verify-email';link=ORIGIN+'/account#'+fragment+'='+token
 title='Cambia tu contraseña' if purpose=='reset' else 'Confirma tu correo'
 body=('Has solicitado cambiar tu contraseña. ' if purpose=='reset' else 'Confirma que este correo te pertenece. ')+f'El enlace caduca en {minutes} minutos y solo se puede usar una vez.\n\n'+link+'\n\nSi no lo has solicitado, ignora este mensaje. Nunca te pediremos tu contraseña por correo.'
 try:deliver_to(p['email'],title,body)
 except Exception:
  with database() as c:c.execute('DELETE FROM email_tokens WHERE token_hash=?',(hashed,))
  return False
 return True

def send_security_mail(member_id,purpose):
 try:return issue(member_id,purpose)
 except Exception:return False


def consume(c,token,purpose):
 if not isinstance(token,str) or not 32<=len(token)<=128:return None
 hashed=hashlib.sha256(token.encode()).hexdigest()
 row=c.execute('SELECT t.*,m.session_version AS current_version,p.email AS current_email,p.email_verified FROM email_tokens t JOIN members m ON m.id=t.member_id JOIN member_profiles p ON p.member_id=t.member_id WHERE t.token_hash=? AND t.purpose=?',(hashed,purpose)).fetchone()
 if not row:return None
 c.execute('DELETE FROM email_tokens WHERE token_hash=?',(hashed,))
 if row['expires_at']<=stamp(now_utc()) or row['session_version']!=row['current_version'] or row['email']!=row['current_email']:return None
 return row

@bp.post('/api/account/profile')
def save_profile():
 user=get_user()
 if not user:return jsonify(error='Inicia sesión para cambiar tu perfil.'),401
 if not allow_attempt('profile-update',6):return jsonify(error='Espera unos minutos antes de volver a cambiar el perfil.'),429
 data=payload();password=data.get('password')
 if not isinstance(password,str) or not check_password_hash(user['password_hash'],password):return jsonify(error='Introduce tu contraseña actual para guardar el correo o el apodo.'),403
 from two_factor import login_factor
 if not login_factor(user,data):return jsonify(error='Introduce un código válido de tu autenticador.',code='two_factor_required'),403
 try:
  email=clean_email(data.get('email'));nickname=clean_nickname(data.get('nickname'))
  with database() as c:
   c.execute('BEGIN IMMEDIATE');fresh=c.execute('SELECT session_version FROM members WHERE id=?',(user['id'],)).fetchone()
   if not fresh or fresh['session_version']!=user['session_version']:return jsonify(error='La sesión ha cambiado. Vuelve a iniciar sesión.'),401
   old=profile(c,user['id']);verified=old['email_verified'] if old['email']==email else 0
   c.execute('INSERT INTO member_profiles(member_id,email,nickname,email_verified,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(member_id) DO UPDATE SET email=excluded.email,nickname=excluded.nickname,email_verified=excluded.email_verified,updated_at=excluded.updated_at',(user['id'],email,nickname,verified,stamp(now_utc())))
   if old['email']!=email:c.execute('DELETE FROM email_tokens WHERE member_id=?',(user['id'],))
  return jsonify(ok=True,verification_sent=send_security_mail(user['id'],'verify') if email and not verified else False)
 except ValueError as e:return jsonify(error=str(e)),400
 except INTEGRITY_ERRORS:return jsonify(error='Ese correo no está disponible para esta cuenta.'),400

@bp.post('/api/account/email/resend')
def resend():
 user=get_user()
 if not user:return jsonify(error='Inicia sesión para confirmar tu correo.'),401
 if not allow_attempt('email-resend',4):return jsonify(error='Espera unos minutos antes de pedir otro correo.'),429
 with database() as c:p=profile(c,user['id'])
 if not p['email']:return jsonify(error='Guarda primero tu correo en «Mi correo y apodo».'),400
 if p['email_verified']:return jsonify(ok=True,already_verified=True)
 if not send_security_mail(user['id'],'verify'):return jsonify(error='No se ha podido enviar el correo. Tu cuenta sigue funcionando; inténtalo más tarde.'),503
 return jsonify(ok=True)

@bp.post('/api/account/email/confirm')
def confirm():
 if not allow_attempt('email-confirm',12):return jsonify(error='Demasiados intentos. Espera unos minutos.'),429
 with database() as c:
  c.execute('BEGIN IMMEDIATE');row=consume(c,payload().get('token'),'verify')
  if not row:return jsonify(error='El enlace no es válido o ha caducado. Pide otro correo desde tu cuenta.'),400
  c.execute('UPDATE member_profiles SET email_verified=1,updated_at=? WHERE member_id=?',(stamp(now_utc()),row['member_id']))
 return jsonify(ok=True)

@bp.post('/api/account/password/request')
def request_reset():
 if not allow_attempt('password-request',5):return jsonify(error='Espera unos minutos antes de pedir otro enlace.'),429
 with database() as c:
  c.execute('BEGIN IMMEDIATE')
  from human_check import verify
  if not verify(c):return jsonify(error='Completa el código de la imagen.',code='human_required'),400
 try:email=clean_email(payload().get('email'))
 except ValueError:email=None
 with database() as c:row=c.execute('SELECT member_id FROM member_profiles WHERE email=? AND email_verified=1',(email,)).fetchone() if email else None
 if row:send_security_mail(row['member_id'],'reset')
 return jsonify(ok=True,message=GENERIC)

@bp.post('/api/account/password/reset')
def reset():
 if not allow_attempt('password-reset',8):return jsonify(error='Demasiados intentos. Espera unos minutos.'),429
 data=payload()
 try:validate_password(data.get('password'))
 except ValueError as e:return jsonify(error=str(e)),400
 encoded=generate_password_hash(data['password'])
 with database() as c:
  c.execute('BEGIN IMMEDIATE');row=consume(c,data.get('token'),'reset')
  if not row or not row['email_verified']:return jsonify(error='El enlace no es válido o ha caducado. Solicita uno nuevo.'),400
  c.execute('UPDATE members SET password_hash=?,session_version=session_version+1 WHERE id=?',(encoded,row['member_id']))
  c.execute('DELETE FROM email_tokens WHERE member_id=?',(row['member_id'],))
 session.clear()
 return jsonify(ok=True,message='Contraseña cambiada. Las sesiones anteriores se han cerrado. Inicia sesión con tu nueva contraseña; la verificación en dos pasos se mantiene.')

@bp.get('/api/admin/email-health')
def email_health():
 from membership import require_admin
 @require_admin
 def report():
  import os
  from email.utils import parseaddr
  sender=parseaddr(os.getenv('OL_EMAIL_FROM',''))[1];domain=sender.rsplit('@',1)[-1].lower() if '@' in sender else ''
  return jsonify(configured=mail_ready(),provider='resend' if os.getenv('RESEND_API_KEY') else 'smtp',sender_domain=domain,customer_sender_configured=bool(mail_ready() and domain and domain!='resend.dev'),provider_delivery_verified=False)
 return report()


def install(app):
 if bp.name not in app.blueprints:app.register_blueprint(bp)
