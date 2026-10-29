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
def configured():
 if provider()=='legacy_paypal':return True
 return bool(os.getenv('STRIPE_SECRET_KEY','').startswith(('sk_live_','rk_live_')) and os.getenv('STRIPE_WEBHOOK_SECRET','').startswith('whsec_') and os.getenv('STRIPE_CONNECT_WEBHOOK_SECRET','').startswith('whsec_') and os.getenv('OL_PAYMENTS_ENABLED')=='1')
def ready():
 from streamers import streamer_sales_ready
 from operations import state
 from operations import premiere
 return not premiere() and not session.get('ol_play_distribution',False) and configured() and streamer_sales_ready() and state()['scope'] not in {'all','payments','live'}

def init_database():
 with database() as c:c.executescript('''CREATE TABLE IF NOT EXISTS stripe_accounts (
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
 key=os.getenv('STRIPE_TEST_SECRET_KEY' if sandbox else 'STRIPE_SECRET_KEY','')
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
 return jsonify(provider=provider(),configured=configured(),enabled=ready(),creator_connected=bool(account),connect_available=bool(provider()=='stripe' and os.getenv('STRIPE_CONNECT_CLIENT_ID','').startswith('ca_') and os.getenv('STRIPE_SECRET_KEY','').startswith('sk_live_')),platform_price_cents=2500,currency='eur',platform_commission_percent=0,renewal='manual',billing_period='year',trial_days=0,play_distribution=bool(session.get('ol_play_distribution')),pending_reason=None if ready() else 'Ol Livis · próximo estreno. Todavía no hay cobros disponibles.')

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
 client=os.getenv('STRIPE_CONNECT_CLIENT_ID','')
 if provider()!='stripe' or not client.startswith('ca_') or not os.getenv('STRIPE_SECRET_KEY','').startswith('sk_live_'):return jsonify(error='La conexión de creadores con Stripe está pendiente de configurar.'),409
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
 return redirect('/live#creator-subscriptions')

def validate_order(c,user,channel_id=None):
 from founder_slots import release_expired,reservation,payment_allowed
 from live_access import details
 if channel_id:
  import subscriptions as sub
  channel=c.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
  if not channel or channel['member_id']==user['id'] or not user_public(user)['active']:raise PaymentError('Necesitas acceso a Ol Livis y una cuenta distinta del creador.')
  mode=sub.settings(c,channel_id);agreement=c.execute('SELECT * FROM subscription_agreements WHERE id=?',(mode['agreement_id'] or '',)).fetchone();account=account_for(c,channel['member_id'])
  if not agreement or not sub.approvals_valid(c,agreement) or not account or agreement['paypal_url']!='stripe:'+account:raise PaymentError('El precio, los beneficios y el destinatario Stripe deben estar aprobados por las tres partes.')
  if sub.active_benefits(c,channel_id,user['id']):raise PaymentError('Ya tienes una suscripción activa. Renueva cuando termine su periodo.')
  pending=c.execute("SELECT id FROM stripe_orders WHERE member_id=? AND channel_id=? AND paid_at IS NULL AND state='open' AND created_at>?",(user['id'],channel_id,stamp(now_utc()-timedelta(minutes=32)))).fetchone()
  if pending:raise PaymentError('Ya hay un pago pendiente para este canal. Completa o deja caducar la sesión anterior.')
  return dict(kind='creator',channel_id=channel_id,agreement_id=agreement['id'],account_id=account,amount_cents=agreement['price_cents'],label='Ol Livis · '+channel['title'])
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
 order_id=secrets.token_hex(16)
 try:
  with database() as c:
   c.execute('BEGIN IMMEDIATE');order=validate_order(c,user,channel_id)
   if order['kind']=='platform_annual' and payload().get('annual_terms') is not True:raise PaymentError('Debes aceptar las condiciones del acceso anual antes de contratar.')
   c.execute('INSERT INTO stripe_orders(id,member_id,kind,channel_id,agreement_id,account_id,amount_cents,currency,created_at,state) VALUES(?,?,?,?,?,?,?,?,?,?)',(order_id,user['id'],order['kind'],order['channel_id'],order['agreement_id'],order['account_id'],order['amount_cents'],'eur',stamp(now_utc()),'open'))
  if order['account_id']:
   account=stripe('GET','/accounts/'+order['account_id'])
   if not account.get('charges_enabled') or not account.get('payouts_enabled'):raise PaymentError('El creador debe completar la verificación bancaria en Stripe antes de cobrar.')
  data={'mode':'payment','managed_payments[enabled]':'false','success_url':ORIGIN+'/account?payment=processing','cancel_url':ORIGIN+'/account?payment=cancelled','client_reference_id':order_id,'metadata[ol_order]':order_id,'payment_intent_data[metadata][ol_order]':order_id,'line_items[0][quantity]':'1','line_items[0][price_data][currency]':'eur','line_items[0][price_data][unit_amount]':str(order['amount_cents']),'line_items[0][price_data][product_data][name]':order['label'],'expires_at':str(int(time.time())+1860),'payment_method_types[0]':'card'}
  if order['kind']=='platform_annual':data['metadata[annual_terms_version]']='2026-10-29-v1'
  result=stripe('POST','/checkout/sessions',data,account=order['account_id'] or None,idempotency='ol-'+order_id)
  if not str(result.get('url','')).startswith('https://checkout.stripe.com/') or not str(result.get('id','')).startswith('cs_'):raise PaymentError('El gestor no devolvió una sesión válida.')
  with database() as c:c.execute('UPDATE stripe_orders SET checkout_id=? WHERE id=?',(result['id'],order_id))
  return jsonify(url=result['url'])
 except PaymentError as e:
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
 else:
  agreement=c.execute('SELECT * FROM subscription_agreements WHERE id=?',(order['agreement_id'],)).fetchone()
  end=stamp(end_of_plan(now_utc(),'monthly')) if agreement['period']=='month' else None
  c.execute('INSERT INTO creator_subscriptions(id,channel_id,member_id,agreement_id,amount_cents,benefits_json,starts_at,ends_at,verified_at,verified_by,reference) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),order['channel_id'],order['member_id'],order['agreement_id'],order['amount_cents'],agreement['benefits_json'],now,end,now,order['member_id'],reference))
 c.execute("UPDATE stripe_orders SET paid_at=?,payment_intent=?,state='paid' WHERE id=?",(now,obj.get('payment_intent'),order['id']))
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
  from notifications import notify
  notify('payment' if order['kind'] in {'platform','platform_annual'} else 'creator_payment','Pago confirmado por Stripe','Stripe ha confirmado un pago de '+format(order['amount_cents']/100,'.2f')+' €. Consulta el detalle privado en electronicama y en el gestor.',event_key='stripe-order:'+order['id'])
 return jsonify(ok=True)

def install(app):
 with app.app_context():init_database()
 app.register_blueprint(bp)
