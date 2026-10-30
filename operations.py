"""Shared maintenance state and least-privilege supervisor designation."""
import os,secrets
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
 );CREATE TABLE IF NOT EXISTS interface_revisions (topic TEXT PRIMARY KEY,version TEXT NOT NULL);''')

@bp.get('/api/sync')
def interface_state():
 with database() as conn:versions={row['topic']:row['version'] for row in conn.execute('SELECT topic,version FROM interface_revisions').fetchall()}
 result={'public':versions.get('public','initial')}
 if get_user():result['account']=versions.get('account','initial')
 response=jsonify(result);response.headers['Cache-Control']='no-store';return response

def mark_interface_change(response):
 if request.method not in {'POST','PUT','PATCH','DELETE'} or not 200<=response.status_code<300:return response
 path=request.path;public=False;account=False
 if path in {'/api/streamers/me','/api/streamers/me/live','/api/streamers/me/layout'}:public=True
 if path.startswith('/api/streamers/') and path.endswith('/view'):
  data=response.get_json(silent=True) or {};public=bool(data.get('recorded'))
 if path.startswith('/api/live/founders/') and path.endswith(('/claim','/signature')):public=True;account=True
 if path.startswith(('/api/admin/','/api/channel-subscriptions/','/api/payments/')):public=True;account=True
 if path.startswith('/api/account/') and not path.endswith(('/human-check','/login','/logout')):account=True
 if not public and not account:return response
 try:
  with database() as conn:
   for topic,changed in [('public',public),('account',account)]:
    if changed:conn.execute('INSERT INTO interface_revisions(topic,version) VALUES(?,?) ON CONFLICT(topic) DO UPDATE SET version=excluded.version',(topic,secrets.token_hex(16)))
 except Exception:
  current_app.logger.warning('Interface refresh notification could not be stored')
 return response

def premiere():return os.getenv('OL_LIVE_PREMIERE','1')=='1'

def state():
 with database() as c:r=c.execute("SELECT scope,message,updated_at FROM ol_operations WHERE id='maintenance'").fetchone()
 d=dict(r) if r else {'scope':'off','message':'electronicama en mantenimiento. Estamos preparando tu mejor momento. Vuelve en unos minutos.','updated_at':None}
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
def status():return jsonify(maintenance=state(),live_premiere=premiere())

@bp.post('/api/admin/maintenance')
@require_admin
def set_maintenance():
 data=payload();scope=data.get('scope');message=str(data.get('message','')).strip()
 if scope not in {'off','all','live','payments'} or not 10<=len(message)<=240:return jsonify(error='Indica ámbito y un aviso de entre 10 y 240 caracteres.'),400
 with database() as c:
  c.execute('BEGIN IMMEDIATE');c.execute("INSERT INTO ol_operations VALUES('maintenance',?,?,?,?) ON CONFLICT(id) DO UPDATE SET scope=excluded.scope,message=excluded.message,updated_by=excluded.updated_by,updated_at=excluded.updated_at",(scope,message,get_user()['id'],stamp(now_utc())))
 return jsonify(ok=True,maintenance=state())

def supervisor_review(c,user):return False

@bp.get('/api/admin/launch-readiness')
@require_admin
def launch_readiness():
 from streamers import video_configuration_checks,live_ready
 from payments import configured,ready,provider
 with database() as c:
  test=c.execute("SELECT COUNT(*) AS n FROM stripe_orders WHERE kind='test' AND state='test_paid' AND paid_at IS NOT NULL").fetchone()['n']
 checks={'video':video_configuration_checks(),'payments':{
  'STRIPE_SECRET_KEY':os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_live_','rk_live_')),
  'STRIPE_WEBHOOK_SECRET':os.getenv('STRIPE_WEBHOOK_SECRET','').startswith('whsec_'),
  'STRIPE_CONNECT_CLIENT_ID':os.getenv('STRIPE_CONNECT_CLIENT_ID','').startswith('ca_'),
  'STRIPE_CONNECT_WEBHOOK_SECRET':os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET','').startswith('whsec_'),
  'MAGGY_STREAMER_SALES_ENABLED':os.getenv('MAGGY_STREAMER_SALES_ENABLED')=='1',
  'OL_PAYMENTS_ENABLED':os.getenv('OL_PAYMENTS_ENABLED')=='1'}}
 if provider()=='legacy_paypal':checks['payments']={'PAYPAL_MANUAL_VERIFICATION':True,'MAGGY_STREAMER_SALES_ENABLED':os.getenv('MAGGY_STREAMER_SALES_ENABLED')=='1'}
 return jsonify(environment=os.getenv('VERCEL_ENV','local'),checks=checks,stripe_test_confirmed=test>0,video_configuration_complete=live_ready(),live_payments_enabled=ready(),configuration_only=True,packaging={'web_pwa':True,'play_signing_configured':bool(os.getenv('OL_ANDROID_SHA256')),'play_publication_verified':False},message='Los datos presentes no sustituyen probar vídeo entre dos dispositivos ni verificar la cuenta comercial de Stripe.')

@bp.get('/api/admin/maintenance-report')
@require_admin
def maintenance_report():
 from pathlib import Path
 from app import VERSION
 from notifications import mail_ready
 from streamers import live_ready
 from payments import ready
 rows=[]
 def add(name,status,detail):rows.append({'name':name,'status':status,'detail':detail})
 try:
  with database() as c:c.execute('SELECT 1').fetchone()
  add('Base de datos','ok','Conexión comprobada sin modificar cuentas ni pagos.')
 except Exception:
  add('Base de datos','error','No se pudo completar la lectura. Revisa la conexión en Vercel.')
 root=Path(__file__).resolve().parent
 required=['index.html','assets/account.html','assets/streamers.html','assets/account.js','assets/navigation.js','assets/operations.js','assets/ol-theme.css','assets/holograms-launcher.js','assets/holograms.js','assets/vendor/three/build/three.module.js','assets/vendor/hands/hands.js','assets/platform-theme.css','assets/interface-sync.js','assets/studio-tools.js','age_policy.py','visitor_registry.py','locale_preferences.py','assets/visitor-registry.js','assets/site-language.js','manifest.webmanifest','sw.js']
 missing=[name for name in required if not (root/name).is_file()]
 add('Archivos esenciales','error' if missing else 'ok','Faltan: '+', '.join(missing) if missing else 'Páginas, acceso, decoración y recursos de la aplicación presentes.')
 from app import content_security_policy
 policy=content_security_policy()
 add('Protección de scripts del navegador','ok' if "object-src 'none'" in policy and "'unsafe-inline'" not in policy and "'unsafe-eval'" not in policy else 'error','Restricciones de scripts y formularios comprobadas; no equivale a un análisis forense de producción.')
 markup=(root/'index.html').read_text()
 optional_autoload=any(term in markup for term in ['fonts.googleapis.com','fonts.gstatic.com','/_vercel/insights/script.js'])
 add('Servicios opcionales antes del consentimiento','error' if optional_autoload else 'ok','Hay una carga automática de fuentes o métricas que revisar.' if optional_autoload else 'No hay cargas automáticas de fuentes de Google ni del script de estadísticas de Vercel.')
 # Read-only checks for features added after the original maintenance panel.
 for table,columns,label in [('interface_revisions','topic,version','Sincronización entre dispositivos'),('adult_channel_rules','channel_id,adult_content,version,locked','Clasificación de contenido adulto'),('adult_age_declarations','member_id,context,minimum_age,expires_at','Declaraciones de edad'),('community_messages','id,channel_id,created_at,blocked','Comentarios incrementales'),('live_channel_views','channel_id,member_id,day','Visitas verificadas de canales'),('live_broadcast_sessions','channel_id,started_at','Sesiones independientes de emisión'),('live_guest_invites','channel_id,member_id,session_start','Invitados del directo'),('community_likes','message_id,member_id','Me gusta reales de comentarios'),('live_channel_thumbnails','channel_id,session_start,updated_at','Miniaturas actuales del directo'),('visitor_sessions','id,device_id,started_at,last_seen','Registro consentido de visitas'),('visitor_devices','id,first_seen,last_seen','Navegadores protegidos de visitas')]:
  try:
   with database() as c:c.execute('SELECT '+columns+' FROM '+table+' LIMIT 0').fetchall()
   add(label,'ok','Estructura de datos presente; no verifica contenidos ni realiza conexiones externas.')
  except Exception:add(label,'error','No se pudo comprobar la estructura de este módulo.')
 try:
  with database() as c:
   excess=c.execute('SELECT COUNT(*) AS n FROM (SELECT channel_id FROM live_guest_invites GROUP BY channel_id HAVING COUNT(*)>6) AS overbooked').fetchone()['n']
   owner_invites=c.execute('SELECT COUNT(*) AS n FROM live_guest_invites i JOIN streamer_channels c ON c.id=i.channel_id WHERE i.member_id=c.member_id').fetchone()['n']
   stale=c.execute('SELECT COUNT(*) AS n FROM live_guest_invites i LEFT JOIN live_broadcast_sessions s ON s.channel_id=i.channel_id WHERE s.channel_id IS NULL OR s.started_at<>i.session_start').fetchone()['n']
   duplicate_likes=c.execute('SELECT COUNT(*) AS n FROM (SELECT message_id,member_id FROM community_likes GROUP BY message_id,member_id HAVING COUNT(*)>1) AS repeated').fetchone()['n']
  add('Límite de siete participantes','error' if excess or owner_invites else 'ok',f'{excess} canales con más de seis invitados; {owner_invites} invitaciones al propio anfitrión. No se han cambiado plazas ni permisos.')
  add('Invitaciones vinculadas a su emisión','pending' if stale else 'ok',f'{stale} invitaciones con sesión anterior o ausente. No se eliminan automáticamente; el acceso debe comprobar la sesión vigente.')
  add('Un Me gusta por cuenta y comentario','error' if duplicate_likes else 'ok',f'{duplicate_likes} votos duplicados detectados. Esta lectura no añade votos ni altera contadores.')
 except Exception:
  add('Integridad del directo compartido','error','No se pudo comprobar sesiones, invitados y reacciones. Revisa la migración y vuelve a ejecutar el diagnóstico.')
 try:
  from datetime import timedelta
  with database() as c:stale_previews=c.execute('SELECT COUNT(*) AS n FROM live_channel_thumbnails t LEFT JOIN live_broadcast_sessions s ON s.channel_id=t.channel_id JOIN streamer_channels c ON c.id=t.channel_id WHERE s.channel_id IS NULL OR s.started_at<>t.session_start OR t.updated_at<? OR c.live_until IS NULL',(stamp(now_utc()-timedelta(seconds=90)),)).fetchone()['n']
  add('Vigencia de miniaturas','pending' if stale_previews else 'ok',f'{stale_previews} miniaturas antiguas o de otra sesión; el servidor las excluye del acceso público. No se han capturado imágenes ni abierto cámaras.')
 except Exception:add('Vigencia de miniaturas','error','No se pudo comprobar la caducidad de las miniaturas.')
 protected=['streamers.check_video','operations.maintenance_report','operations.launch_readiness','age_policy.moderate_classification','recordings.listing','recordings.private_link','visitor_registry.list_visits']
 secured=all(getattr(current_app.view_functions.get(endpoint),'requires_admin',False) for endpoint in protected)
 add('Comprobaciones exclusivas de administración','ok' if secured else 'error','Protección de rol presente en diagnósticos de vídeo, mantenimiento y moderación.' if secured else 'Hay una ruta de diagnóstico sin la marca de protección administrativa.')
 add('Ubicación y VPN para contenido adulto','pending' if not current_app.extensions.get('adult_region_assessor') else 'ok','Sin proveedor de evaluación fiable: se aplica mínimo interno de 21 años; la IP no demuestra edad ni ausencia de VPN.' if not current_app.extensions.get('adult_region_assessor') else 'Evaluador regional instalado; comprueba su precisión y privacidad antes de confiar en sus resultados.')
 from recordings import ready as recordings_ready
 add('Grabación de directos · 30 días','ok' if recordings_ready() else 'pending','Grabación y retención declaradas en la configuración; comprueba un archivo real en Grabaciones privadas.' if recordings_ready() else 'Los vídeos no se están archivando. Falta conectar almacenamiento privado y grabación de LiveKit; los textos conservados no sustituyen al vídeo.')
 add('Verificación de edad','pending','Se solicita declaración de edad. No hay verificación documental ni detección visual automática de consumo.')
 add('Vídeo y comentarios superpuestos','pending','Diseño preparado. Comprueba vídeo a tamaño completo, pantalla compartida y chat desplazable en dispositivos reales.')
 add('Correos','ok' if mail_ready() else 'pending','Servicio configurado; esta revisión no envía correos ni confirma su llegada.' if mail_ready() else 'Configura el remitente y Resend o SMTP antes de probar confirmación y recuperación.')
 add('YouTube','ok' if os.getenv('YOUTUBE_API_KEY','').strip() else 'pending','Clave de búsqueda presente; usa el filtro YouTube para comprobar cuota y permisos. Los vídeos utilizan el reproductor oficial.' if os.getenv('YOUTUBE_API_KEY','').strip() else 'Falta YOUTUBE_API_KEY en este entorno. Las demás fuentes siguen disponibles.')
 add('Ol Livis','pending' if premiere() or not live_ready() else 'ok','Próximo estreno; la prueba pública sigue detenida.' if premiere() else 'Configuración de vídeo presente; comprueba una emisión entre dos dispositivos.' if live_ready() else 'Falta completar la configuración de vídeo.')
 add('Cobros','ok' if ready() else 'pending','Cobros habilitados según configuración; esta revisión no realiza transacciones.' if ready() else 'Cobros desactivados o pendientes de configuración. No se ha cambiado este estado.')
 try:
  scope=state()['scope']
  add('Aviso de mantenimiento','ok' if scope=='off' else 'pending','Sin cierre de mantenimiento.' if scope=='off' else 'Aviso activo: '+scope+'. Puedes gestionarlo desde el formulario de mantenimiento.')
 except Exception:add('Aviso de mantenimiento','error','No se pudo leer el estado de mantenimiento.')
 response=jsonify(at=stamp(now_utc()),version=VERSION,checks=rows,ok=not any(row['status']=='error' for row in rows),configuration_only=True,automation={'mode':'admin_visible_page','default_interval_minutes':30,'server_scheduler':False,'public_monitor':{'provider':'github_actions','configured_schedule':'7,37 * * * *','observed_active':None},'read_only':True,'description':'Revisión periódica mientras el panel administrativo permanece abierto y visible. No es un monitor permanente del servidor ni repara datos automáticamente.'})
 response.headers['Cache-Control']='no-store'
 return response

@bp.get('/api/admin/supervisor')
@require_admin
def supervisor_status():return jsonify(supervisor=None,retired=True)

@bp.post('/api/admin/supervisor')
@require_admin
def assign_supervisor():return jsonify(error='Este apartado ha sido retirado.'),410


def guard():
 path=request.path
 if request.method=='GET' and request.args.get('distribution')=='googleplay':session['ol_play_distribution']=True
 if path.startswith(('/assets/','/api/admin/','/api/account/','/api/payments/webhook/')) or path in {'/health','/api/status','/api/sync','/api/payments/status','/account','/sw.js','/manifest.webmanifest','/api/payments/connect-return','/.well-known/assetlinks.json'}:return
 d=state();scope=d['scope']
 affected=scope=='all' or scope=='live' and (path in {'/live','/streamers'} or path.startswith(('/api/streamers','/api/channel-subscriptions','/api/live/'))) or scope=='payments' and path.startswith('/api/payments/')
 if not affected:return
 user=get_user()
 if user and user['role']=='admin':return
 if scope=='live' and user:
  from membership import user_public
  if user_public(user).get('full_service'):return
 if path.startswith('/api/'):response=make_response(jsonify(error=d['message'],code='ol_maintenance'),503)
 else:
  from html import escape
  response=make_response('<!doctype html><html lang="es"><meta name="viewport" content="width=device-width,initial-scale=1"><title>electronicama en mantenimiento</title><link rel="stylesheet" href="/assets/maintenance.css"><main><a href="/">electronicama ∞</a><h1>electronicama en mantenimiento</h1><p>'+escape(d['message'])+'</p><p>Tu cuenta y tus beneficios permanecen guardados.</p><a href="/account">Mi cuenta</a> · <button onclick="location.reload()">Volver a comprobar</button></main></html>',503)
 response.headers.update({'Retry-After':'60','Cache-Control':'no-store'});return response

def install(app):
 app.register_blueprint(bp)
 app.after_request(mark_interface_change)
 app.before_request_funcs.setdefault(None,[]).insert(0,guard)
