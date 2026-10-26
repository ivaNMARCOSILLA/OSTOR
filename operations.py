"""Shared maintenance state and least-privilege supervisor designation."""
import os
from flask import Blueprint,jsonify,request,current_app,make_response,session
from membership import database,get_user,payload,require_admin,stamp,now_utc
bp=Blueprint('operations',__name__)

def init_database():
 with database() as c:c.executescript('''CREATE TABLE IF NOT EXISTS ol_operations (
 id TEXT PRIMARY KEY,scope TEXT NOT NULL,message TEXT NOT NULL,updated_by TEXT REFERENCES members(id),updated_at TEXT NOT NULL
 );CREATE TABLE IF NOT EXISTS fan_aliases (
 member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,alias TEXT NOT NULL
 );CREATE TABLE IF NOT EXISTS ol_supervisors (
 member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,assigned_by TEXT NOT NULL REFERENCES members(id),assigned_at TEXT NOT NULL,can_review INTEGER NOT NULL DEFAULT 0,revoked_at TEXT
 );''')

def state():
 with database() as c:r=c.execute("SELECT scope,message,updated_at FROM ol_operations WHERE id='maintenance'").fetchone()
 d=dict(r) if r else {'scope':'off','message':'Ol en mantenimiento. Estamos preparando tu mejor momento. Vuelve en unos minutos.','updated_at':None}
 if os.getenv('OL_MAINTENANCE')=='1':d['scope']='all'
 return d

@bp.get('/.well-known/assetlinks.json')
def android_association():
 import re
 fingerprint=os.getenv('OL_ANDROID_SHA256','').upper();package=os.getenv('OL_ANDROID_PACKAGE','com.electronicama.ol')
 if not re.fullmatch(r'(?:[A-F0-9]{2}:){31}[A-F0-9]{2}',fingerprint) or not re.fullmatch(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+',package):return jsonify(error='La firma real de Google Play aún no está configurada.'),404
 return jsonify([{'relation':['delegate_permission/common.handle_all_urls'],'target':{'namespace':'android_app','package_name':package,'sha256_cert_fingerprints':[fingerprint]}}])

@bp.get('/api/account/fan-alias')
def fan_alias():
 user=get_user()
 if not user:return jsonify(error='Entra en tu cuenta.'),401
 with database() as c:r=c.execute('SELECT alias FROM fan_aliases WHERE member_id=?',(user['id'],)).fetchone()
 return jsonify(alias=r['alias'] if r else '',choices=['Lola','Lolo','Loles'])

@bp.post('/api/account/fan-alias')
def save_fan_alias():
 user=get_user();alias=payload().get('alias')
 if not user:return jsonify(error='Entra en tu cuenta.'),401
 if alias not in {'','Lola','Lolo','Loles'}:return jsonify(error='Elige un apodo de afición válido o déjalo sin apodo.'),400
 with database() as c:c.execute('INSERT INTO fan_aliases VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET alias=excluded.alias',(user['id'],alias))
 return jsonify(ok=True,alias=alias)

@bp.get('/api/status')
def status():return jsonify(maintenance=state())

@bp.post('/api/admin/maintenance')
@require_admin
def set_maintenance():
 data=payload();scope=data.get('scope');message=str(data.get('message','')).strip()
 if scope not in {'off','all','live','payments'} or not 10<=len(message)<=240:return jsonify(error='Indica ámbito y un aviso de entre 10 y 240 caracteres.'),400
 with database() as c:
  c.execute('BEGIN IMMEDIATE');c.execute("INSERT INTO ol_operations VALUES('maintenance',?,?,?,?) ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,message=excluded.message,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(scope,message,get_user()['id'],stamp(now_utc())))
 return jsonify(ok=True,maintenance=state())

def supervisor_review(c,user):return bool(user and c.execute('SELECT member_id FROM ol_supervisors WHERE member_id=? AND revoked_at IS NULL AND can_review=1',(user['id'],)).fetchone() and user['password_hash'])

@bp.get('/api/admin/launch-readiness')
@require_admin
def launch_readiness():
 from streamers import video_configuration_checks,live_ready
 from payments import configured,ready
 with database() as c:
  test=c.execute("SELECT COUNT(*) AS n FROM stripe_orders WHERE kind='test' AND state='test_paid' AND paid_at IS NOT NULL").fetchone()['n']
 checks={'video':video_configuration_checks(),'payments':{
  'STRIPE_SECRET_KEY':os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_live_','rk_live_')),
  'STRIPE_WEBHOOK_SECRET':os.getenv('STRIPE_WEBHOOK_SECRET','').startswith('whsec_'),
  'STRIPE_CONNECT_CLIENT_ID':os.getenv('STRIPE_CONNECT_CLIENT_ID','').startswith('ca_'),
  'STRIPE_CONNECT_WEBHOOK_SECRET':os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET','').startswith('whsec_'),
  'MAGGY_STREAMER_SALES_ENABLED':os.getenv('MAGGY_STREAMER_SALES_ENABLED')=='1',
  'OL_PAYMENTS_ENABLED':os.getenv('OL_PAYMENTS_ENABLED')=='1'}}
 return jsonify(environment=os.getenv('VERCEL_ENV','local'),checks=checks,stripe_test_confirmed=test>0,video_configuration_complete=live_ready(),live_payments_enabled=ready(),configuration_only=True,packaging={'web_pwa':True,'play_signing_configured':bool(os.getenv('OL_ANDROID_SHA256')),'play_publication_verified':False},message='Los datos presentes no sustituyen probar vídeo entre dos dispositivos ni verificar la cuenta comercial de Stripe.')

@bp.get('/api/admin/supervisor')
@require_admin
def supervisor_status():
 with database() as c:r=c.execute('SELECT m.username,(m.password_hash IS NOT NULL) AS activated,s.can_review FROM ol_supervisors s JOIN members m ON m.id=s.member_id WHERE s.revoked_at IS NULL ORDER BY s.assigned_at DESC LIMIT 1').fetchone()
 return jsonify(supervisor=dict(r) if r else None)

@bp.post('/api/admin/supervisor')
@require_admin
def assign_supervisor():
 data=payload()
 name=str(data.get('username','Rubi')).strip().lower()
 if not 3<=len(name)<=60 or type(data.get('can_review',False)) is not bool:return jsonify(error='Indica el usuario real de Rubi y su permiso de revisión.'),400
 with database() as c:
  c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT id,role FROM members WHERE LOWER(username)=?',(name,)).fetchone()
  if not r:return jsonify(error='No se encuentra Rubi. Comprueba su nombre de usuario; no se ha creado otra cuenta.'),404
  if r['role']=='admin':return jsonify(error='El supervisor debe usar una cuenta distinta de administración.'),409
  if c.execute('SELECT member_id FROM pricing_moderators WHERE member_id=? AND revoked_at IS NULL',(r['id'],)).fetchone():return jsonify(error='Supervisor y moderador de acuerdos deben usar cuentas distintas.'),409
  c.execute('UPDATE ol_supervisors SET revoked_at=?,can_review=0 WHERE member_id!=?',(stamp(now_utc()),r['id']))
  c.execute('INSERT INTO ol_supervisors(member_id,assigned_by,assigned_at,can_review) VALUES(?,?,?,?) ON CONFLICT(member_id) DO UPDATE SET assigned_by=excluded.assigned_by,assigned_at=excluded.assigned_at,can_review=excluded.can_review,revoked_at=NULL',(r['id'],get_user()['id'],stamp(now_utc()),int(data.get('can_review',False))))
 return jsonify(ok=True)

def guard():
 path=request.path
 if request.method=='GET' and request.args.get('distribution')=='googleplay':session['ol_play_distribution']=True
 if path.startswith(('/assets/','/api/admin/','/api/account/','/api/payments/webhook/')) or path in {'/health','/api/status','/api/payments/status','/account','/sw.js','/manifest.webmanifest','/api/payments/connect-return','/.well-known/assetlinks.json'}:return
 d=state();scope=d['scope']
 affected=scope=='all' or scope=='live' and (path in {'/live','/streamers'} or path.startswith(('/api/streamers','/api/channel-subscriptions','/api/live/'))) or scope=='payments' and path.startswith('/api/payments/')
 if not affected:return
 user=get_user()
 if user and user['role']=='admin':return
 if path.startswith('/api/'):response=make_response(jsonify(error=d['message'],code='ol_maintenance'),503)
 else:
  from html import escape
  response=make_response('<!doctype html><html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ol en mantenimiento</title><link rel="stylesheet" href="/assets/maintenance.css"><main><a href="/">Ol ∞</a><h1>Ol en mantenimiento</h1><p>'+escape(d['message'])+'</p><p>Tu cuenta y tus beneficios permanecen guardados.</p><a href="/account">Mi cuenta</a> · <button onclick="location.reload()">Volver a comprobar</button></main></html>',503)
 response.headers.update({'Retry-After':'60','Cache-Control':'no-store'});return response

def install(app):
 app.register_blueprint(bp)
 app.before_request_funcs.setdefault(None,[]).insert(0,guard)
