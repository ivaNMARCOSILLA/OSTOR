"""Stripe Checkout + Standard Connect. Signed, idempotent payments; no client-side grants."""
import hashlib,hmac,json,os,re,secrets,time
from datetime import datetime,timedelta,timezone
import requests
from flask import Blueprint,jsonify,request,redirect,current_app,session
from membership import database,get_user,user_public,payload,stamp,now_utc,end_of_plan,allow_attempt,require_admin
bp=Blueprint('payments',__name__)
ORIGIN='https://electronicama.com'
class PaymentError(Exception):
 def __init__(self,message,code='provider_unavailable',reason=None):
  super().__init__(message);self.code=code;self.reason=reason


def provider():
 # Legacy imports remain readable locally; deployed electronicama only offers Stripe.
 return 'stripe' if os.getenv('VERCEL_ENV') in {'production','preview'} else os.getenv('OL_PAYMENT_PROVIDER','stripe')
def connect_configuration_error():
 if provider()!='stripe':return 'El servidor no tiene Stripe seleccionado como gestor.'
 client=os.getenv('STRIPE_CONNECT_CLIENT_ID','').strip()
 key=os.getenv('STRIPE_SECRET_KEY','').strip()
 if not client:return 'Falta STRIPE_CONNECT_CLIENT_ID en el despliegue que atiende esta web. Añádelo a Production y despliega de nuevo.'
 if not client.startswith('ca_'):return 'STRIPE_CONNECT_CLIENT_ID no es un ID de cliente OAuth válido: debe empezar por ca_.'
 if not key:return 'Falta STRIPE_SECRET_KEY en el despliegue que atiende esta web.'
 if key.startswith(('sk_test_','rk_test_')):return 'STRIPE_SECRET_KEY contiene una clave de pruebas. Connect requiere una clave secreta real sk_live_.'
 if key.startswith('rk_live_'):return 'La clave de pagos es restringida. Este flujo OAuth necesita STRIPE_SECRET_KEY con una clave sk_live_.'
 if not key.startswith('sk_live_'):return 'STRIPE_SECRET_KEY no tiene el formato secreto real sk_live_ requerido para OAuth.'
 return None

def configured():
 if provider()=='legacy_paypal':return True
 return bool(os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_live_','rk_live_')) and os.getenv('STRIPE_WEBHOOK_SECRET','').startswith('whsec_') and os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET','').startswith('whsec_') and os.getenv('OL_PAYMENTS_ENABLED')=='1')
def ready():
 from streamers import streamer_sales_ready
 from operations import state
 from operations import premiere
 return not premiere() and not session.get('ol_play_distribution',False) and configured() and streamer_sales_ready() and state()['scope'] not in {'all','payments','live'}

def init_database():
 with database() as c:c.executescript('''CREATE TABLE IF NOT EXISTS stripe_order_names (order_id TEXT PRIMARY KEY,legal_name TEXT NOT NULL);CREATE TABLE IF NOT EXISTS annual_access_emails (
 order_id TEXT PRIMARY KEY,member_id TEXT NOT NULL,recipient TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending'
 );CREATE TABLE IF NOT EXISTS stripe_accounts (
 member_id TEXT PRIMARY KEY REFERENCES members(id),account_id TEXT NOT NULL UNIQUE,linked_at TEXT NOT NULL
 );CREATE TABLE IF NOT EXISTS stripe_connect_states (
 token_hash TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id),expires_at TEXT NOT NULL
 );CREATE TABLE IF NOT EXISTS stripe_orders (
 id TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id),kind TEXT NOT NULL,
 channel_id TEXT REFERENCES streamer_channels(id),agreement_id TEXT REFERENCES subscription_agreements(id),
 account_id TEXT NOT NULL,amount_cents INTEGER NOT NULL,currency TEXT NOT NULL,created_at TEXT NOT NULL,
 checkout_id TEXT UNIQUE,payment_intent TEXT,paid_at TEXT,reversed_at TEXT,state TEXT NOT NULL
 );CREATE TABLE IF NOT EXISTS stripe_reversals (
 payment_intent TEXT NOT NULL,account_id TEXT NOT NULL,reversed_at TEXT NOT NULL,PRIMARY KEY(payment_intent,account_id)
 );CREATE TABLE IF NOT EXISTS stripe_events (
 id TEXT PRIMARY KEY,event_type TEXT NOT NULL,received_at TEXT NOT NULL
 );''')

def stripe(method,path,data=None,account=None,idempotency=None,oauth=False,sandbox=False):
 key=os.getenv('STRIPE_TEST_SECRET_KEY' if sandbox else 'STRIPE_SECRET_KEY','').strip()
 if sandbox and not key.startswith(('sk_test_','rk_test_')):raise PaymentError('Configura una clave secreta de pruebas en STRIPE_TEST_SECRET_KEY.')
 if not key:raise PaymentError('Stripe está pendiente de configurar.')
 if oauth:data={**(data or {}),'client_secret':key}
 headers={'Authorization':'Bearer '+key,'Stripe-Version':'2024-06-20'}
 if account:headers['Stripe-Account']=account
 if idempotency:headers['Idempotency-Key']=idempotency
 url=('https://connect.stripe.com' if oauth else 'https://api.stripe.com/v1')+path
 try:
  response=requests.request(method,url,data=data,headers=headers,timeout=(3,15),allow_redirects=False)
  if response.status_code not in (200,201):
   try:error=response.json().get('error',{})
   except ValueError:error={}
   code=str(error.get('code') or error.get('type') or 'request_rejected')
   messages={'api_key_expired':'La clave de Stripe ha caducado. Actualiza la clave secreta de pruebas en Vercel.', 'invalid_api_key':'Stripe rechaza la clave secreta. Revisa que corresponda al mismo entorno de pruebas.', 'account_invalid':'Stripe no reconoce la cuenta asociada a esa clave.', 'permission_error':'La clave restringida no tiene los permisos de Checkout necesarios.', 'idempotency_error':'Stripe conserva un intento anterior distinto. Contacta con administración para revisar la sesión.', 'rate_limit':'Stripe está limitando las peticiones. Espera un minuto.'}
   if response.status_code==401:code='invalid_api_key'
   elif response.status_code==403 and code=='request_rejected':code='permission_error'
   message=str(error.get('message','')).lower()
   if 'business name' in message or 'account name' in message:code='business_profile_required';messages[code]='Stripe necesita que completes el nombre del negocio en su configuración antes de abrir Checkout.'
   reason=str(error.get('message','')) if sandbox else ''
   reason=re.sub(r'(?i)(?:sk|rk|pk)_(?:test|live)_[A-Za-z0-9_*.-]+|whsec_[A-Za-z0-9_*.-]+|[A-Za-z0-9]+_secret_[A-Za-z0-9_*.-]+','[credencial oculta]',reason)
   reason=re.sub(r'https?://\S+','[enlace de Stripe]',reason)[:500]
   raise PaymentError(messages.get(code,'Stripe ha rechazado la creación del pago. Revisa las tareas pendientes de tu cuenta en su panel.'),code if re.fullmatch(r'[a-z_]{1,60}',code) else 'request_rejected',reason or None)
  return response.json()
 except (requests.RequestException,ValueError):raise PaymentError('El gestor de pagos no está disponible. No se ha confirmado ningún pago.') from None

def account_for(c,member_id):
 r=c.execute('SELECT account_id FROM stripe_accounts WHERE member_id=?',(member_id,)).fetchone();return r['account_id'] if r else None

@bp.get('/api/payments/status')
def status():
 user=get_user()
 with database() as c:account=account_for(c,user['id']) if user else None
 return jsonify(provider=provider(),configured=configured(),enabled=ready(),creator_connected=bool(account),connect_available=connect_configuration_error() is None,connect_pending_reason=connect_configuration_error() if user else None,platform_price_cents=2500,currency='eur',platform_commission_percent=0,renewal='manual',billing_period='year',trial_days=0,play_distribution=bool(session.get('ol_play_distribution')),pending_reason=None if ready() else 'Ol Livis · próximo estreno. Todavía no hay cobros disponibles.')

def sandbox_configured():return bool(os.getenv('STRIPE_TEST_SECRET_KEY','').startswith(('sk_test_','rk_test_')) and os.getenv('STRIPE_TEST_WEBHOOK_SECRET','').startswith('whsec_'))

@bp.get('/api/admin/payments/account-health')
@require_admin
def account_health():
 if not allow_attempt('stripe-account-health',limit=4):return jsonify(error='Espera un minuto antes de volver a comprobar Stripe.'),429
 if not os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_live_','rk_live_')):return jsonify(error='Falta la clave secreta real de Stripe en Vercel Production.'),409
 try:account=stripe('GET','/account')
 except PaymentError as error:return jsonify(error=str(error),code=error.code),502
 # Return only readiness flags, never identity, bank, key or document fields.
 requirements=account.get('requirements') or {}
 return jsonify(connected=True,charges_enabled=bool(account.get('charges_enabled')),payouts_enabled=bool(account.get('payouts_enabled')),details_submitted=bool(account.get('details_submitted')),requirements_pending=len(requirements.get('currently_due') or []),requirements_overdue=len(requirements.get('past_due') or []),payments_enabled=ready(),read_only=True)

@bp.get('/api/admin/payments/test-status')
@require_admin
def test_status():return jsonify(configured=sandbox_configured(),mode='test',grants_access=False)

@bp.post('/api/admin/payments/test-checkout')
@require_admin
def test_checkout():
 if not sandbox_configured():return jsonify(error='Añade las dos variables privadas de pruebas en Vercel: STRIPE_TEST_SECRET_KEY y STRIPE_TEST_WEBHOOK_SECRET.'),409
 ident=secrets.token_hex(16);user=get_user()
 with database() as c:
  c.execute('BEGIN IMMEDIATE')
  pending=c.execute("SELECT * FROM stripe_orders WHERE member_id=? AND kind='test' AND state='open' AND created_at>?",(user['id'],stamp(now_utc()-timedelta(minutes=32)))).fetchone()
  if pending:ident=pending['id']
  else:c.execute("INSERT INTO stripe_orders(id,member_id,kind,account_id,amount_cents,currency,created_at,state) VALUES(?,?,'test','',2500,'eur',?,'open')",(ident,user['id'],stamp(now_utc())))
 try:
  if pending and pending['checkout_id']:
   resumed=stripe('GET','/checkout/sessions/'+pending['checkout_id'],sandbox=True)
   if resumed.get('status')=='open' and str(resumed.get('url','')).startswith('https://checkout.stripe.com/'):
    return jsonify(url=resumed['url'],mode='test',grants_access=False,resumed=True)
   return jsonify(error='La sesión anterior ya se completó o caducó. Actualiza la página para comprobarla.'),409
  if not allow_attempt('stripe-admin-sandbox-v2',limit=8):return jsonify(error='Se han repetido varias solicitudes. Espera 15 minutos; no se ha creado otro pago.',code='attempt_limit'),429
  if pending:
   with database() as c:c.execute("UPDATE stripe_orders SET state='abandoned' WHERE id=? AND checkout_id IS NULL",(ident,))
   ident=secrets.token_hex(16)
   with database() as c:c.execute("INSERT INTO stripe_orders(id,member_id,kind,account_id,amount_cents,currency,created_at,state) VALUES(?,?,'test','',2500,'eur',?,'open')",(ident,user['id'],stamp(now_utc())))
  result=stripe('POST','/checkout/sessions',{'mode':'payment','managed_payments[enabled]':'false','success_url':ORIGIN+'/account?test_payment=processing','cancel_url':ORIGIN+'/account?test_payment=cancelled','metadata[ol_order]':ident,'client_reference_id':ident,'line_items[0][quantity]':'1','line_items[0][price_data][currency]':'eur','line_items[0][price_data][unit_amount]':'2500','line_items[0][price_data][product_data][name]':'electronicama · PRUEBA SIN DINERO REAL · no activa acceso','payment_method_types[0]':'card','expires_at':str(int(time.time())+1860)},idempotency='ol-test-'+ident,sandbox=True)
  if not str(result.get('id','')).startswith('cs_test_') or not str(result.get('url','')).startswith('https://checkout.stripe.com/'):raise PaymentError('Stripe no devolvió una sesión válida de pruebas.')
  with database() as c:c.execute('UPDATE stripe_orders SET checkout_id=? WHERE id=?',(result['id'],ident))
  return jsonify(url=result['url'],mode='test',grants_access=False)
 except PaymentError as e:
  with database() as c:c.execute("UPDATE stripe_orders SET state='failed' WHERE id=? AND checkout_id IS NULL",(ident,))
  return jsonify(error=str(e),code=e.code,diagnostic=e.reason),409

@bp.post('/api/payments/connect')
def connect():
 user=get_user()
 if not user or not user_public(user)['streamer_active']:return jsonify(error='Entra con una cuenta de creador activa.'),403
 client=os.getenv('STRIPE_CONNECT_CLIENT_ID','').strip()
 problem=connect_configuration_error()
 if problem:return jsonify(error=problem,code='connect_configuration_incomplete'),409
 if not allow_attempt('stripe-connect',limit=6):return jsonify(error='Espera unos minutos antes de volver a conectar.'),429
 token=secrets.token_urlsafe(32)
 with database() as c:
  c.execute('DELETE FROM stripe_connect_states WHERE expires_at<?',(stamp(now_utc()),));c.execute('INSERT INTO stripe_connect_states VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],stamp(now_utc()+timedelta(minutes=10))))
 from urllib.parse import urlencode
 return jsonify(url='https://connect.stripe.com/oauth/authorize?'+urlencode({'response_type':'code','client_id':client,'scope':'read_write','redirect_uri':ORIGIN+'/api/payments/connect-return','state':token}))

@bp.get('/api/payments/connect-return')
def connect_return():
 user=get_user();token=request.args.get('state','');code=request.args.get('code','')
 if not user or not token or not code:return jsonify(error='Vuelve a entrar en electronicama y conecta tu cuenta desde tu canal.'),400
 with database() as c:
  c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT member_id,expires_at FROM stripe_connect_states WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
  if not r or r['member_id']!=user['id'] or r['expires_at']<stamp(now_utc()):return jsonify(error='La autorización ha caducado o pertenece a otra cuenta.'),403
  c.execute('DELETE FROM stripe_connect_states WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))
 try:
  data=stripe('POST','/oauth/token',{'grant_type':'authorization_code','code':code},oauth=True);account=data.get('stripe_user_id','')
  if not re.fullmatch(r'acct_[A-Za-z0-9]+',account) or data.get('livemode') is not True:raise PaymentError('Conecta una cuenta de Stripe en modo real.')
  # OAuth access/refresh tokens are deliberately not stored or returned.
  with database() as c:
   c.execute('BEGIN IMMEDIATE');old=account_for(c,user['id'])
   if old and old!=account:raise PaymentError('Solicita a administración una revisión de los acuerdos antes de cambiar el destinatario.')
   c.execute('INSERT INTO stripe_accounts VALUES(?,?,?) ON CONFLICT(member_id) DO NOTHING',(user['id'],account,stamp(now_utc())))
 except PaymentError as e:return jsonify(error=str(e)),409
 return redirect('/live?stripe=connected#creator-subscriptions')

def validate_order(c,user,channel_id=None):
 from founder_slots import release_expired,reservation,payment_allowed
 from live_access import details
 if channel_id:
  import subscriptions as sub
  channel=c.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
  if not channel or channel['member_id']==user['id'] or not user_public(user)['active']:raise PaymentError('Necesitas acceso a Ol Livis y una cuenta distinta del creador.')
  from account_archives import is_archived
  if is_archived(c,channel['member_id']):raise PaymentError('El creador ha dado de baja su cuenta. No se admiten nuevas suscripciones.',code='creator_unavailable')
  mode=sub.settings(c,channel_id);agreement=c.execute('SELECT * FROM subscription_agreements WHERE id=?',(mode['agreement_id'] or '',)).fetchone();account=account_for(c,channel['member_id'])
  if not agreement or not sub.approvals_valid(c,agreement) or not account or agreement['paypal_url']!='stripe:'+account:raise PaymentError('El precio, los beneficios y el destinatario Stripe deben estar aprobados por las tres partes.')
  if not 300<=sub.channel_price(c,channel_id,agreement['price_cents'])<=400 or agreement['period']!='month':raise PaymentError('El precio del canal debe estar entre 3 y 4 € al mes y volver a aprobarse.')
  if sub.active_benefits(c,channel_id,user['id']):raise PaymentError('Ya tienes una suscripción activa. Renueva cuando termine su periodo.')
  pending=c.execute("SELECT id FROM stripe_orders WHERE member_id=? AND channel_id=? AND paid_at IS NULL AND state='open' AND created_at>?",(user['id'],channel_id,stamp(now_utc()-timedelta(minutes=32)))).fetchone()
  if pending:raise PaymentError('Ya hay un pago pendiente para este canal. Completa o deja caducar la sesión anterior.')
  return dict(kind='creator',channel_id=channel_id,agreement_id=agreement['id'],account_id=account,amount_cents=sub.channel_price(c,channel_id,agreement['price_cents'],user['id']),label='Ol Livis · '+channel['title'])
 release_expired(c);entitlement=details(user['id'],c);slot=reservation(c,user['id'])
 if entitlement.get('revoked_at'):raise PaymentError('Contacta con administración para revisar el acceso antes de contratar.')
 if user['role']=='admin' or user_public(user)['complimentary'] or user_public(user)['live_lifetime']:raise PaymentError('Esta cuenta ya dispone de acceso; no corresponde cobrar.')
 if user_public(user)['active'] and user['access_until'] and user['access_until']>stamp(now_utc()+timedelta(days=30)):raise PaymentError('Tu acceso anual sigue vigente. Podrás renovar durante sus últimos 30 días.')
 if c.execute("SELECT id FROM stripe_orders WHERE member_id=? AND kind IN ('platform','platform_annual') AND paid_at IS NULL AND state='open' AND created_at>?",(user['id'],stamp(now_utc()-timedelta(minutes=32)))).fetchone():raise PaymentError('Ya hay un pago pendiente. Completa o deja caducar la sesión anterior.')
 return dict(kind='platform_annual',channel_id=None,agreement_id=None,account_id='',amount_cents=2500,label='Ol Livis · 25 EUR por un año, sin prueba gratuita')

@bp.post('/api/payments/checkout')
def checkout():
 user=get_user()
 if not user:return jsonify(error='Entra antes de pagar.'),401
 if provider()!='stripe' or not ready():return jsonify(error='electronicama está preparando el gestor de pagos. Todavía no se habilitan cobros.'),409
 if not allow_attempt('stripe-checkout',limit=8):return jsonify(error='Espera unos minutos antes de volver a pagar.'),429
 channel_id=payload().get('channel_id')
 if channel_id is not None and not isinstance(channel_id,str):return jsonify(error='Canal no válido.'),400
 if channel_id:
  from age_policy import gate
  with database() as check:restricted=gate(check,channel_id,user)
  if restricted:return restricted
  from human_check import verify
  with database() as check:
   check.execute('BEGIN IMMEDIATE');human_ok=verify(check)
  if not human_ok:return jsonify(error='Completa la comprobación humana antes de pagar la suscripción del canal.',code='human_required'),400
 order_id=secrets.token_hex(16)
 timezone_name=str(payload().get('timezone','UTC'))
 from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
 try:ZoneInfo(timezone_name)
 except (ZoneInfoNotFoundError,ValueError):return jsonify(error='Zona horaria no válida.'),400
 try:
  with database() as c:
   c.execute('BEGIN IMMEDIATE');order=validate_order(c,user,channel_id)
   if order['kind']=='platform_annual' and payload().get('annual_terms') is not True:raise PaymentError('Debes aceptar las condiciones del acceso anual antes de contratar.')
   legal_name=None
   if order['kind']=='platform_annual':
    from email_security import clean_legal_name
    saved=c.execute('SELECT legal_name FROM member_legal_names WHERE member_id=?',(user['id'],)).fetchone()
    legal_name=clean_legal_name(payload().get('legal_name') or (saved['legal_name'] if saved else ''))
    if not legal_name:raise PaymentError('Indica tu nombre real completo para identificar el pago de Ol Livis.')
    c.execute('INSERT INTO member_legal_names(member_id,legal_name,updated_at) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET legal_name=excluded.legal_name,updated_at=excluded.updated_at',(user['id'],legal_name,stamp(now_utc())))
   c.execute('INSERT INTO stripe_orders(id,member_id,kind,channel_id,agreement_id,account_id,amount_cents,currency,created_at,state) VALUES(?,?,?,?,?,?,?,?,?,?)',(order_id,user['id'],order['kind'],order['channel_id'],order['agreement_id'],order['account_id'],order['amount_cents'],'eur',stamp(now_utc()),'open'))
   c.execute('INSERT INTO stripe_order_context VALUES(?,?)',(order_id,timezone_name))
   if legal_name:c.execute('INSERT INTO stripe_order_names VALUES(?,?)',(order_id,legal_name))
  if order['account_id']:
   account=stripe('GET','/accounts/'+order['account_id'])
   if not account.get('charges_enabled') or not account.get('payouts_enabled'):raise PaymentError('El creador debe completar la verificación bancaria en Stripe antes de cobrar.')
  data={'mode':'payment','managed_payments[enabled]':'false','success_url':ORIGIN+'/account?payment=processing','cancel_url':ORIGIN+'/account?payment=cancelled','client_reference_id':order_id,'metadata[ol_order]':order_id,'payment_intent_data[metadata][ol_order]':order_id,'line_items[0][quantity]':'1','line_items[0][price_data][currency]':'eur','line_items[0][price_data][unit_amount]':str(order['amount_cents']),'line_items[0][price_data][product_data][name]':order['label'],'expires_at':str(int(time.time())+1860),'payment_method_types[0]':'card'}
  if order['kind']=='platform_annual':
   data['metadata[annual_terms_version]']='2026-10-29-v2';data['metadata[registered_legal_name]']=legal_name;data['payment_intent_data[metadata][registered_legal_name]']=legal_name;data['billing_address_collection']='required';data['custom_text[submit][message]']='Utiliza el mismo nombre real que has indicado en electronicama.'
  result=stripe('POST','/checkout/sessions',data,account=order['account_id'] or None,idempotency='ol-'+order_id)
  if not str(result.get('url','')).startswith('https://checkout.stripe.com/') or not str(result.get('id','')).startswith('cs_'):raise PaymentError('El gestor no devolvió una sesión válida.')
  with database() as c:c.execute('UPDATE stripe_orders SET checkout_id=? WHERE id=?',(result['id'],order_id))
  return jsonify(url=result['url'])
 except (PaymentError,ValueError) as e:
  # Keep ambiguous requests pending until Checkout expires: retries must not produce a second charge.
  return jsonify(error=str(e)),409

def verified_event(raw,signature,secret):
 if not secret.startswith('whsec_'):raise ValueError('unconfigured')
 parts={}
 for bit in signature.split(','):
  key,sep,value=bit.partition('=')
  if sep:parts.setdefault(key,[]).append(value)
 timestamp=int(parts.get('t',['0'])[0])
 if abs(time.time()-timestamp)>300:raise ValueError('expired')
 expected=hmac.new(secret.encode(),str(timestamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
 if not any(hmac.compare_digest(expected,v) for v in parts.get('v1',[])):raise ValueError('signature')
 event=json.loads(raw)
 if not isinstance(event,dict) or not isinstance(event.get('id'),str):raise ValueError('event')
 return event

def notification_members(order):
 ids=[order['member_id']]
 if order['channel_id']:
  with database() as c:channel=c.execute('SELECT member_id FROM streamer_channels WHERE id=?',(order['channel_id'],)).fetchone()
  if channel:ids.append(channel['member_id'])
 return ids

def assign_confirmed_founders(c):
 """Caller holds the payment/account transaction. Never infer a payment from a return URL."""
 from founder_slots import release_expired,reserve
 from storage import PostgresConnection
 exists=c.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='maggy' AND table_name='stripe_orders'").fetchone() if isinstance(c,PostgresConnection) else c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stripe_orders'").fetchone()
 if not exists:return
 release_expired(c)
 if c.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']>=100:return
 rows=c.execute("SELECT m.id,MIN(o.paid_at) AS paid FROM members m JOIN stripe_orders o ON o.member_id=m.id JOIN live_entitlements e ON e.member_id=m.id WHERE o.kind='platform_annual' AND o.paid_at IS NOT NULL AND o.reversed_at IS NULL AND e.paid_at IS NOT NULL AND e.revoked_at IS NULL AND m.role!='admin' AND m.access_until>? AND NOT EXISTS(SELECT 1 FROM member_archives a WHERE a.member_id=m.id AND a.restored_at IS NULL) AND NOT EXISTS(SELECT 1 FROM live_founders f WHERE f.member_id=m.id) GROUP BY m.id ORDER BY paid,m.id LIMIT 100",(stamp(now_utc()),)).fetchall()
 for member in rows:
  if reserve(c,member['id']) is None:break

@bp.post('/api/payments/reconcile')
def reconcile():
 user=get_user()
 if not user:return jsonify(error='Inicia sesión para comprobar tu pago.'),401
 return reconcile_member(user)

@bp.post('/api/admin/payments/reconcile')
@require_admin
def admin_reconcile():
 with database() as c:member=c.execute('SELECT * FROM members WHERE id=?',(str(payload().get('member_id','')),)).fetchone()
 if not member or member['role']=='admin':return jsonify(error='Selecciona una cuenta de cliente.'),400
 return reconcile_member(member)

def reconcile_member(user):
 with database() as c:
  order=c.execute("SELECT * FROM stripe_orders WHERE member_id=? AND kind='platform_annual' AND paid_at IS NULL AND reversed_at IS NULL AND checkout_id IS NOT NULL AND state IN ('open','expired') ORDER BY created_at DESC LIMIT 1",(user['id'],)).fetchone()
 if not order:
  with database() as c:
   paid=c.execute("SELECT o.id FROM stripe_orders o JOIN members m ON m.id=o.member_id JOIN live_entitlements e ON e.member_id=m.id WHERE o.member_id=? AND o.kind='platform_annual' AND o.paid_at IS NOT NULL AND o.reversed_at IS NULL AND e.revoked_at IS NULL AND m.access_until>? LIMIT 1",(user['id'],stamp(now_utc()))).fetchone()
   if paid:
    c.execute('BEGIN IMMEDIATE');assign_confirmed_founders(c)
  return jsonify(ok=True,confirmed=bool(paid),pending=False)
 if not allow_attempt('stripe-reconcile:'+user['id'],limit=6):return jsonify(error='Espera unos minutos antes de comprobar de nuevo este pago.'),429
 try:
  obj=stripe('GET','/checkout/sessions/'+order['checkout_id'])
  if obj.get('livemode') is not True:return jsonify(error='La sesión de Stripe no corresponde a un pago real.'),409
  if obj.get('payment_status')!='paid':return jsonify(ok=True,confirmed=False,pending=True)
  with database() as c:
   c.execute('BEGIN IMMEDIATE')
   current=c.execute('SELECT * FROM stripe_orders WHERE id=?',(order['id'],)).fetchone()
   changed=fulfill(c,current,obj)
   final=c.execute('SELECT paid_at,reversed_at FROM stripe_orders WHERE id=?',(order['id'],)).fetchone()
   confirmed=bool(final['paid_at'] and not final['reversed_at'])
  if changed:
   send_annual_access_emails()
   from notifications import notify
   notify('payment','Pago sincronizado con Stripe','Stripe ha confirmado un pago anual de 25 €. El acceso está activo y la plaza se asigna según disponibilidad.',event_key='stripe-order:'+order['id'],member_ids=notification_members(order))
 except (PaymentError,ValueError,TypeError):return jsonify(error='No se ha podido confirmar todavía el pago con Stripe. Tu pedido se conserva; no repitas el cobro.'),409
 return jsonify(ok=True,confirmed=confirmed,pending=False)

def fulfill(c,order,obj):
 if order['paid_at'] or order['reversed_at']:return False
 if c.execute('SELECT payment_intent FROM stripe_reversals WHERE payment_intent=? AND account_id=?',(('test:'+str(obj.get('payment_intent'))) if order['kind']=='test' else obj.get('payment_intent'),order['account_id'])).fetchone():
  c.execute("UPDATE stripe_orders SET reversed_at=?,state='reversed' WHERE id=?",(stamp(now_utc()),order['id']));return False
 if obj.get('payment_status')!='paid' or obj.get('amount_total')!=order['amount_cents'] or obj.get('currency')!='eur' or obj.get('id')!=order['checkout_id']:raise ValueError('payment mismatch')
 if (obj.get('metadata') or {}).get('ol_order')!=order['id']:raise ValueError('metadata mismatch')
 now=stamp(now_utc());reference='stripe:'+obj['id']
 if order['kind']=='test':
  c.execute("UPDATE stripe_orders SET paid_at=?,payment_intent=?,state='test_paid' WHERE id=?",(now,obj.get('payment_intent'),order['id']));return False
 if order['kind'] in {'platform','platform_annual'}:
  plan='annual' if order['kind']=='platform_annual' else 'lifetime'
  member=c.execute('SELECT access_until FROM members WHERE id=?',(order['member_id'],)).fetchone()
  start=max(now_utc(),datetime.fromisoformat(member['access_until'])) if member['access_until'] and plan=='annual' else now_utc()
  end=stamp(end_of_plan(start,plan))
  # Automated receipt explicitly attributes verification to the account holder, not a fabricated administrator.
  c.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),order['member_id'],plan,2500,stamp(start),end,now,order['member_id'],reference))
  c.execute('DELETE FROM annual_preferences WHERE member_id=?',(order['member_id'],))
  c.execute('UPDATE members SET access_until=?,welcome_used=1 WHERE id=?',(end,order['member_id']))
  c.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET paid_at=excluded.paid_at,revoked_at=NULL',(order['member_id'],now))
  c.execute('INSERT INTO streamer_access(member_id,until_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET until_at=excluded.until_at',(order['member_id'],end))
  if plan=='annual':
   profile=c.execute('SELECT email,email_verified FROM member_profiles WHERE member_id=?',(order['member_id'],)).fetchone()
   if profile and profile['email'] and profile['email_verified']:
    c.execute('INSERT INTO annual_access_emails(order_id,member_id,recipient) VALUES(?,?,?) ON CONFLICT(order_id) DO NOTHING',(order['id'],order['member_id'],profile['email']))
 else:
  agreement=c.execute('SELECT * FROM subscription_agreements WHERE id=?',(order['agreement_id'],)).fetchone()
  from subscriptions import month_end
  context=c.execute('SELECT timezone FROM stripe_order_context WHERE order_id=?',(order['id'],)).fetchone()
  end=stamp(month_end(now_utc(),context['timezone'] if context else 'UTC')) if agreement['period']=='month' else None
  c.execute('INSERT INTO creator_subscriptions(id,channel_id,member_id,agreement_id,amount_cents,benefits_json,starts_at,ends_at,verified_at,verified_by,reference) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),order['channel_id'],order['member_id'],order['agreement_id'],order['amount_cents'],agreement['benefits_json'],now,end,now,order['member_id'],reference))
 c.execute("UPDATE stripe_orders SET paid_at=?,payment_intent=?,state='paid' WHERE id=?",(now,obj.get('payment_intent'),order['id']))
 if order['kind']=='platform_annual':assign_confirmed_founders(c)
 return True

@bp.post('/api/payments/webhook/<scope>')
def webhook(scope):
 if scope not in {'platform','connect','test'}:return jsonify(error='No existe ese webhook.'),404
 try:event=verified_event(request.get_data(),request.headers.get('Stripe-Signature',''),os.getenv('STRIPE_TEST_WEBHOOK_SECRET' if scope=='test' else 'STRIPE_CONNECT_WEBHOOK_SECRET' if scope=='connect' else 'STRIPE_WEBHOOK_SECRET',''))
 except (ValueError,TypeError,UnicodeError):return jsonify(error='Firma del gestor no válida.'),400
 if type(event.get('livemode')) is not bool or event['livemode']!=(scope!='test'):return jsonify(error='El modo del evento no coincide con el webhook.'),400
 account=event.get('account','')
 if bool(account)!=(scope=='connect'):return jsonify(error='Origen del evento no válido.'),400
 event_id=('test:' if scope=='test' else '')+event['id']
 obj=(event.get('data') or {}).get('object') or {};changed=False;order=None
 try:
  with database() as c:
   c.execute('BEGIN IMMEDIATE')
   if c.execute('SELECT id FROM stripe_events WHERE id=?',(event_id,)).fetchone():return jsonify(ok=True,duplicate=True)
   kind=event.get('type')
   if kind in {'checkout.session.completed','checkout.session.async_payment_succeeded','checkout.session.expired'}:
    order=c.execute('SELECT * FROM stripe_orders WHERE checkout_id=? AND account_id=?',(obj.get('id',''),account)).fetchone()
    if order:
     if (order['kind']=='test')!=(scope=='test'):raise ValueError('order mode mismatch')
     if kind=='checkout.session.expired':c.execute("UPDATE stripe_orders SET state='expired' WHERE id=? AND paid_at IS NULL",(order['id'],))
     else:changed=fulfill(c,order,obj)
   elif kind in {'charge.refunded','charge.dispute.created'}:
    intent=obj.get('payment_intent');order=c.execute('SELECT * FROM stripe_orders WHERE payment_intent=? AND account_id=?',(intent,account)).fetchone() if intent else None
    if intent and (kind=='charge.dispute.created' or obj.get('refunded') is True):c.execute('INSERT INTO stripe_reversals VALUES(?,?,?) ON CONFLICT(payment_intent,account_id) DO NOTHING',(('test:'+intent) if scope=='test' else intent,account,stamp(now_utc())))
    if order and (order['kind']=='test')!=(scope=='test'):raise ValueError('order mode mismatch')
    if order and (kind=='charge.dispute.created' or obj.get('refunded') is True):
     now=stamp(now_utc());c.execute("UPDATE stripe_orders SET reversed_at=?,state='reversed' WHERE id=?",(now,order['id']))
     if order['kind']=='creator':c.execute('UPDATE creator_subscriptions SET revoked_at=? WHERE reference=?',(now,'stripe:'+order['checkout_id']))
     elif order['kind'] in {'platform','platform_annual'} and not c.execute("SELECT 1 FROM payments p JOIN members m ON m.id=p.member_id WHERE p.member_id=? AND p.reference=? AND p.ends_at<m.access_until",(order['member_id'],'stripe:'+order['checkout_id'])).fetchone():
      c.execute('UPDATE live_entitlements SET paid_at=NULL,revoked_at=? WHERE member_id=?',(now,order['member_id']))
      c.execute('UPDATE streamer_access SET until_at=? WHERE member_id=?',(now,order['member_id']))
      c.execute('UPDATE members SET access_until=? WHERE id=?',(now,order['member_id']))
   c.execute('INSERT INTO stripe_events VALUES(?,?,?)',(event_id,str(kind),stamp(now_utc())))
 except (ValueError,TypeError):return jsonify(error='El evento no coincide con el pedido registrado.'),400
 if changed:
  send_annual_access_emails()
  from notifications import notify
  notify('payment' if order['kind'] in {'platform','platform_annual'} else 'creator_payment','Pago confirmado por Stripe','Stripe ha confirmado un pago de '+format(order['amount_cents']/100,'.2f')+' €. Consulta el detalle privado en electronicama y en el gestor.',event_key='stripe-order:'+order['id'],member_ids=notification_members(order))
 return jsonify(ok=True)

def send_annual_access_emails():
 from notifications import deliver_to,mail_ready
 if not mail_ready():return 0
 with database() as c:rows=c.execute("SELECT e.* FROM annual_access_emails e JOIN stripe_orders o ON o.id=e.order_id JOIN member_profiles p ON p.member_id=e.member_id WHERE e.status='pending' AND o.paid_at IS NOT NULL AND o.reversed_at IS NULL AND p.email=e.recipient AND p.email_verified=1 LIMIT 3").fetchall()
 sent=0
 for row in rows:
  with database() as c:
   c.execute('BEGIN IMMEDIATE')
   claimed=c.execute("UPDATE annual_access_emails SET status='sending' WHERE order_id=? AND status='pending'",(row['order_id'],)).rowcount
  if not claimed:continue
  try:
   with database() as c:founder=c.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(row['member_id'],)).fetchone()
   badge=('Tu plaza de fundador n.º '+str(founder['number'])+' se ha asignado automáticamente. Conserva el acceso anual y cumple las condiciones de actividad.' if founder and not founder['revoked_at'] else 'Tienes acceso anual como participante de Ol Livis. Las 100 insignias de fundador están sujetas a disponibilidad; no limitan el acceso ordinario.')
   deliver_to(row['recipient'],'Ol Livis · tu acceso anual está activo','Tu pago de 25 € está confirmado y tu acceso anual a Ol Livis está activo.\n\n'+badge+'\n\nNo necesitas solicitar otra plaza ni realizar otro pago.\n\nConsulta tu estado y vencimiento en '+ORIGIN+'/account#pricing')
  except Exception:
   with database() as c:c.execute("UPDATE annual_access_emails SET status='pending' WHERE order_id=?",(row['order_id'],))
  else:
   with database() as c:c.execute("UPDATE annual_access_emails SET status='sent' WHERE order_id=?",(row['order_id'],))
   sent+=1
 return sent

def install(app):
 with app.app_context():init_database()
 app.register_blueprint(bp)
