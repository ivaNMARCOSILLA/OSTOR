"""Creator subscriptions: versioned terms, three independent approvals, verified receipts."""
import json,secrets
from datetime import datetime
from flask import Blueprint,jsonify,request
from membership import database,get_user,user_public,now_utc,stamp,payload,require_admin,end_of_plan
from storage import INTEGRITY_ERRORS
bp=Blueprint('subscriptions',__name__)
BENEFITS={'badge':'Insignia de suscriptor','subscriber_chat':'Chat para suscriptores','exclusive_live':'Directos para suscriptores'}

def init_database():
 with database() as conn:
  conn.executescript('''CREATE TABLE IF NOT EXISTS moderator_permissions (
   member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,permission TEXT NOT NULL,
   granted_by TEXT NOT NULL REFERENCES members(id),granted_at TEXT NOT NULL,PRIMARY KEY(member_id,permission)
  );CREATE TABLE IF NOT EXISTS subscription_agreements (
   id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES streamer_channels(id),version INTEGER NOT NULL,
   creator_id TEXT NOT NULL REFERENCES members(id),moderator_id TEXT NOT NULL REFERENCES members(id),
   price_cents INTEGER NOT NULL,period TEXT NOT NULL,benefits_json TEXT NOT NULL,paypal_url TEXT NOT NULL,
   created_at TEXT NOT NULL,UNIQUE(channel_id,version)
  );CREATE TABLE IF NOT EXISTS subscription_approvals (
   agreement_id TEXT NOT NULL REFERENCES subscription_agreements(id),party TEXT NOT NULL,
   member_id TEXT NOT NULL REFERENCES members(id),approved_at TEXT NOT NULL,PRIMARY KEY(agreement_id,party)
  );CREATE TABLE IF NOT EXISTS channel_subscription_settings (
   channel_id TEXT PRIMARY KEY REFERENCES streamer_channels(id),agreement_id TEXT REFERENCES subscription_agreements(id),
   subscriber_chat INTEGER NOT NULL DEFAULT 0,exclusive_live INTEGER NOT NULL DEFAULT 0
  );CREATE TABLE IF NOT EXISTS creator_subscriptions (
   id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES streamer_channels(id),member_id TEXT NOT NULL REFERENCES members(id),
   agreement_id TEXT NOT NULL REFERENCES subscription_agreements(id),amount_cents INTEGER NOT NULL,benefits_json TEXT NOT NULL,
   starts_at TEXT NOT NULL,ends_at TEXT,verified_at TEXT NOT NULL,verified_by TEXT NOT NULL REFERENCES members(id),
   reference TEXT NOT NULL UNIQUE,revoked_at TEXT
  );CREATE INDEX IF NOT EXISTS creator_subscriptions_access ON creator_subscriptions(channel_id,member_id,ends_at);
  CREATE TABLE IF NOT EXISTS community_audiences (
   message_id TEXT PRIMARY KEY REFERENCES community_messages(id) ON DELETE CASCADE,audience TEXT NOT NULL
  );''')

 from payments import init_database as init_payments
 init_payments()

# Payment orders reference the agreement tables initialized above.
MODERATOR_PERMISSIONS={'review_agreements':'Ver propuestas y sus condiciones','approve_agreements':'Aprobar precios y beneficios'}

def moderator(conn,user,permission='review_agreements'):
 return bool(user and conn.execute('SELECT p.member_id FROM pricing_moderators p JOIN members m ON m.id=p.member_id WHERE p.member_id=? AND p.revoked_at IS NULL AND m.password_hash IS NOT NULL AND EXISTS (SELECT 1 FROM moderator_permissions x WHERE x.member_id=p.member_id AND x.permission=?)',(user['id'],permission)).fetchone())

def active_benefits(conn,channel_id,member_id):
 if not member_id:return set()
 rows=conn.execute('SELECT benefits_json FROM creator_subscriptions WHERE channel_id=? AND member_id=? AND revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?)',(channel_id,member_id,stamp(now_utc()),stamp(now_utc()))).fetchall()
 return {benefit for row in rows for benefit in json.loads(row['benefits_json'])}

def privileged(channel,user):return bool(user and (user['role']=='admin' or user['id']==channel['member_id']))

def settings(conn,channel_id):
 row=conn.execute('SELECT * FROM channel_subscription_settings WHERE channel_id=?',(channel_id,)).fetchone()
 return dict(row) if row else dict(channel_id=channel_id,agreement_id=None,subscriber_chat=0,exclusive_live=0)

def watch_allowed(conn,channel,user):
 mode=settings(conn,channel['id'])
 return not mode['exclusive_live'] or privileged(channel,user) or 'exclusive_live' in active_benefits(conn,channel['id'],user['id'] if user else None)

def chat_allowed(conn,channel,user):
 return privileged(channel,user) or 'subscriber_chat' in active_benefits(conn,channel['id'],user['id'] if user else None)

def count(conn,channel_id):
 return conn.execute('SELECT COUNT(DISTINCT member_id) AS n FROM creator_subscriptions WHERE channel_id=? AND revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?)',(channel_id,stamp(now_utc()),stamp(now_utc()))).fetchone()['n']

def decorate(channels):
 if not channels:return channels
 with database() as conn:
  counts={row['channel_id']:row['n'] for row in conn.execute('SELECT channel_id,COUNT(DISTINCT member_id) AS n FROM creator_subscriptions WHERE revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?) GROUP BY channel_id',(stamp(now_utc()),stamp(now_utc()))).fetchall()}
  modes={row['channel_id']:bool(row['exclusive_live']) for row in conn.execute('SELECT channel_id,exclusive_live FROM channel_subscription_settings').fetchall()}
 return [dict(c,subscriber_count=counts.get(c['id'],0),subscribers_only=modes.get(c['id'],False)) for c in channels]

def public_agreement(conn,row,private=False):
 if not row:return None
 approvals=conn.execute('SELECT party,member_id,approved_at FROM subscription_approvals WHERE agreement_id=?',(row['id'],)).fetchall()
 result={key:row[key] for key in ['id','channel_id','version','price_cents','period','created_at']}
 title=conn.execute('SELECT c.title,m.username FROM streamer_channels c JOIN members m ON m.id=c.member_id WHERE c.id=?',(row['channel_id'],)).fetchone()
 result.update(title=title['title'],creator_name=title['username'])
 result.update(benefits=json.loads(row['benefits_json']),approvals={party:any(a['party']==party for a in approvals) for party in ['creator','admin','moderator']})
 if private:
  result.update(creator_id=row['creator_id'],moderator_id=row['moderator_id'])
  if row['paypal_url'].startswith('stripe:'):result.update(payment_provider='stripe',payout_account=row['paypal_url'][7:])
  else:
   from payments import provider
   if provider()!='stripe':result['paypal_url']=row['paypal_url']
 return result

def approvals_valid(conn,row):
 approvals={a['party']:a['member_id'] for a in conn.execute('SELECT party,member_id FROM subscription_approvals WHERE agreement_id=?',(row['id'],)).fetchall()}
 if set(approvals)!={'creator','admin','moderator'} or len(set(approvals.values()))!=3:return False
 if approvals['creator']!=row['creator_id'] or approvals['moderator']!=row['moderator_id']:return False
 if not conn.execute("SELECT id FROM members WHERE id=? AND role='admin'",(approvals['admin'],)).fetchone():return False
 return moderator(conn,{'id':approvals['moderator']},'approve_agreements')

@bp.get('/api/channel-subscriptions/reviewer')
def reviewer_status():
 user=get_user()
 with database() as conn:
  from operations import supervisor_review
  is_supervisor=supervisor_review(conn,user)
  is_mod=moderator(conn,user)
  assigned=conn.execute('SELECT m.id,m.username,(m.password_hash IS NOT NULL) AS activated FROM pricing_moderators p JOIN members m ON m.id=p.member_id WHERE p.revoked_at IS NULL ORDER BY p.assigned_at DESC LIMIT 1').fetchone() if user and user['role']=='admin' else None
  assigned=dict(assigned) if assigned else None
  target=assigned['id'] if assigned else user['id'] if user else None
  permissions=[r['permission'] for r in conn.execute('SELECT permission FROM moderator_permissions WHERE member_id=?',(target,)).fetchall()] if target else []
  if assigned:assigned.pop('id')
 return jsonify(member_id=user['id'] if user else None,supervisor=is_supervisor,moderator=is_mod,admin=bool(user and user['role']=='admin'),assigned=assigned,permissions=permissions,available_permissions=MODERATOR_PERMISSIONS)

@bp.post('/api/admin/subscription-moderator')
@require_admin
def assign_moderator():
 name=str(payload().get('username','Gref')).strip().lower()
 if name!='gref':return jsonify(error='El moderador designado para estos acuerdos es Gref.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT id,password_hash,role FROM members WHERE LOWER(username)=?',(name,)).fetchone()
  if not row:return jsonify(error='Crea primero la cuenta o una invitación privada de Gref desde administración.'),404
  if row['role']=='admin':return jsonify(error='La cuenta del moderador debe ser distinta de la administración.'),409
  previous=conn.execute('SELECT revoked_at FROM pricing_moderators WHERE member_id=?',(row['id'],)).fetchone()
  if not previous or previous['revoked_at']:conn.execute('DELETE FROM moderator_permissions WHERE member_id=?',(row['id'],))
  conn.execute('UPDATE pricing_moderators SET revoked_at=? WHERE member_id!=?',(stamp(now_utc()),row['id']))
  conn.execute('DELETE FROM moderator_permissions WHERE member_id!=?',(row['id'],))
  conn.execute('INSERT INTO pricing_moderators(member_id,assigned_by,assigned_at) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET assigned_by=excluded.assigned_by,assigned_at=excluded.assigned_at,revoked_at=NULL',(row['id'],get_user()['id'],stamp(now_utc())))
 return jsonify(ok=True,username='Gref',activated=bool(row['password_hash']))

@bp.post('/api/admin/moderator-permissions')
@require_admin
def update_moderator_permissions():
 permissions=payload().get('permissions')
 if not isinstance(permissions,list) or any(not isinstance(p,str) or p not in MODERATOR_PERMISSIONS for p in permissions):return jsonify(error='Permisos no válidos.'),400
 if 'approve_agreements' in permissions and 'review_agreements' not in permissions:return jsonify(error='Para aprobar acuerdos debes permitir también verlos.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  row=conn.execute('SELECT member_id FROM pricing_moderators WHERE revoked_at IS NULL ORDER BY assigned_at DESC LIMIT 1').fetchone()
  if not row:return jsonify(error='Designa primero la cuenta del moderador.'),409
  conn.execute('DELETE FROM moderator_permissions WHERE member_id=?',(row['member_id'],))
  for permission in set(permissions):conn.execute('INSERT INTO moderator_permissions(member_id,permission,granted_by,granted_at) VALUES(?,?,?,?)',(row['member_id'],permission,get_user()['id'],stamp(now_utc())))
 return jsonify(ok=True,permissions=sorted(set(permissions)))

@bp.get('/api/channel-subscriptions/creator')
def creator_dashboard():
 user=get_user()
 if not user:return jsonify(error='Entra en tu cuenta.'),401
 with database() as conn:
  channel=conn.execute('SELECT * FROM streamer_channels WHERE member_id=?',(user['id'],)).fetchone()
  if not channel:return jsonify(channel=None)
  latest=conn.execute('SELECT * FROM subscription_agreements WHERE channel_id=? ORDER BY version DESC LIMIT 1',(channel['id'],)).fetchone()
  gross=conn.execute('SELECT COALESCE(SUM(amount_cents),0) AS n FROM creator_subscriptions WHERE channel_id=?',(channel['id'],)).fetchone()['n']
  return jsonify(channel=dict(id=channel['id'],title=channel['title'],subscriber_count=count(conn,channel['id']),gross_confirmed_cents=gross),latest=public_agreement(conn,latest,True),settings=settings(conn,channel['id']),benefits=BENEFITS)

@bp.post('/api/channel-subscriptions/propose')
def propose():
 user=get_user();data=payload()
 if not user or not user_public(user)['streamer_active']:return jsonify(error='Necesitas acceso de creador activo para proponer una suscripción.'),403
 cents=data.get('price_cents');period=data.get('period');benefits=data.get('benefits')
 if type(cents) is not int or not 1<=cents<=99999999 or period not in {'month','once'} or not isinstance(benefits,list) or not benefits or len(benefits)>3 or any(type(b) is not str or b not in BENEFITS for b in benefits):return jsonify(error='Indica un precio positivo en euros, periodo y beneficios válidos.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');channel=conn.execute('SELECT * FROM streamer_channels WHERE member_id=?',(user['id'],)).fetchone()
  from payments import provider,account_for
  if not channel:return jsonify(error='Guarda antes tu canal.'),409
  account=account_for(conn,user['id']) if provider()=='stripe' else None
  payout='stripe:'+account if account else channel['paypal_url']
  if provider()=='stripe' and not account:return jsonify(error='Conecta primero tu cuenta Stripe desde tu canal. Las tres partes deben aprobar el destinatario.'),409
  if not payout:return jsonify(error='Guarda antes el destinatario de las suscripciones.'),409
  mod=conn.execute('SELECT p.member_id FROM pricing_moderators p JOIN members m ON m.id=p.member_id WHERE p.revoked_at IS NULL AND LOWER(m.username)=? ORDER BY p.assigned_at DESC LIMIT 1',('gref',)).fetchone()
  if not mod:return jsonify(error='Administración debe designar primero la cuenta de Gref como moderador de acuerdos.'),409
  if mod['member_id']==user['id']:return jsonify(error='El creador y el moderador deben usar cuentas distintas.'),409
  mode=settings(conn,channel['id'])
  if (mode['subscriber_chat'] and 'subscriber_chat' not in benefits) or (mode['exclusive_live'] and 'exclusive_live' not in benefits):return jsonify(error='Desactiva expresamente los modos exclusivos antes de quitar esos beneficios del siguiente acuerdo.'),409
  version=conn.execute('SELECT COALESCE(MAX(version),0)+1 AS n FROM subscription_agreements WHERE channel_id=?',(channel['id'],)).fetchone()['n'];ident=secrets.token_hex(16)
  conn.execute('INSERT INTO subscription_agreements(id,channel_id,version,creator_id,moderator_id,price_cents,period,benefits_json,paypal_url,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',(ident,channel['id'],version,user['id'],mod['member_id'],cents,period,json.dumps(sorted(set(benefits))),payout,stamp(now_utc())))
 from notifications import notify
 notify('creator_offer','Nueva propuesta de suscripción',f'Hay una nueva propuesta de precio y beneficios, versión {version}, pendiente de las tres aprobaciones. Revisa el acuerdo en tu panel.',event_key='creator-offer:'+ident)
 return jsonify(ok=True,agreement_id=ident,version=version,published=False)

@bp.get('/api/channel-subscriptions/review')
def review_queue():
 user=get_user()
 with database() as conn:
  from operations import supervisor_review
  supervising=supervisor_review(conn,user)
  if not user or (user['role']!='admin' and not moderator(conn,user) and not supervising):return jsonify(error='Este panel es solo para administración y el moderador designado.'),403
  try:page=max(1,int(request.args.get('page',1)))
  except ValueError:page=1
  where='' if user['role']=='admin' or supervising else ' AND a.moderator_id=?';params=() if user['role']=='admin' or supervising else (user['id'],)
  base='FROM subscription_agreements a WHERE a.version=(SELECT MAX(b.version) FROM subscription_agreements b WHERE b.channel_id=a.channel_id)'+where
  total=conn.execute('SELECT COUNT(*) AS n '+base,params).fetchone()['n']
  rows=conn.execute('SELECT a.* '+base+' ORDER BY a.created_at DESC LIMIT 25 OFFSET ?',params+((page-1)*25,)).fetchall()
  result=[public_agreement(conn,row,True) for row in rows]
 return jsonify(agreements=result,page=page,pages=max(1,(total+24)//25),total=total,party='admin' if user['role']=='admin' else 'supervisor' if supervising else 'moderator',benefits=BENEFITS)

@bp.post('/api/channel-subscriptions/approve')
def approve():
 user=get_user();data=payload();party=data.get('party')
 if not user or party not in {'creator','admin','moderator'}:return jsonify(error='Entra con la cuenta de la parte que aprueba.'),403
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');row=conn.execute('SELECT * FROM subscription_agreements WHERE id=?',(str(data.get('agreement_id','')),)).fetchone()
  if not row:return jsonify(error='El acuerdo no existe.'),404
  allowed=(party=='creator' and user['id']==row['creator_id']) or (party=='admin' and user['role']=='admin' and user['id'] not in {row['creator_id'],row['moderator_id']}) or (party=='moderator' and user['id']==row['moderator_id'] and user['id']!=row['creator_id'] and moderator(conn,user,'approve_agreements'))
  if not allowed:return jsonify(error='Cada parte debe aprobar desde su propia cuenta autorizada.'),403
  latest=conn.execute('SELECT MAX(version) AS n FROM subscription_agreements WHERE channel_id=?',(row['channel_id'],)).fetchone()['n']
  if row['version']!=latest:return jsonify(error='Este acuerdo fue sustituido. Revisa la versión actual.'),409
  conn.execute('INSERT INTO subscription_approvals(agreement_id,party,member_id,approved_at) VALUES(?,?,?,?) ON CONFLICT(agreement_id,party) DO NOTHING',(row['id'],party,user['id'],stamp(now_utc())))
  activated=approvals_valid(conn,row)
  if activated:conn.execute('INSERT INTO channel_subscription_settings(channel_id,agreement_id) VALUES(?,?) ON CONFLICT(channel_id) DO UPDATE SET agreement_id=excluded.agreement_id',(row['channel_id'],row['id']))
 return jsonify(ok=True,agreement_activated=activated)

@bp.get('/api/channel-subscriptions/<channel_id>')
def offer(channel_id):
 user=get_user()
 with database() as conn:
  channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
  if not channel:return jsonify(error='El canal no existe.'),404
  mode=settings(conn,channel_id);row=conn.execute('SELECT * FROM subscription_agreements WHERE id=?',(mode['agreement_id'] or '',)).fetchone()
  valid=bool(row and approvals_valid(conn,row));benefits=active_benefits(conn,channel_id,user['id'] if user else None)
  from streamers import streamer_sales_ready
  enabled=bool(valid and streamer_sales_ready() and row['paypal_url']==channel['paypal_url'] and user and user_public(user)['active'] and user['id']!=channel['member_id'])
  from payments import provider,ready,account_for
  if provider()=='stripe':enabled=bool(valid and ready() and row['paypal_url']=='stripe:'+str(account_for(conn,channel['member_id'])) and user and user_public(user)['active'] and user['id']!=channel['member_id'])
  link=(row['paypal_url']+f"/{row['price_cents']//100}.{row['price_cents']%100:02d}EUR") if enabled and provider()!='stripe' else None
  return jsonify(checkout_available=enabled and provider()=='stripe',channel_id=channel_id,title=channel['title'],subscriber_count=count(conn,channel_id),agreement=public_agreement(conn,row) if valid else None,benefits=BENEFITS,mine=sorted(benefits),payments_enabled=enabled,payment_url=link,exclusive_live=bool(mode['exclusive_live']),subscriber_chat=bool(mode['subscriber_chat']),payment_mode='stripe' if provider()=='stripe' else 'creator_verified_external_paypal',commission_cents=0)

@bp.post('/api/channel-subscriptions/<channel_id>/mode')
def update_mode(channel_id):
 user=get_user();data=payload()
 if not user:return jsonify(error='Entra en tu cuenta.'),401
 if any(type(data.get(key)) is not bool for key in ['subscriber_chat','exclusive_live']):return jsonify(error='Indica los dos modos del canal.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
  if not channel or channel['member_id']!=user['id']:return jsonify(error='Solo el titular puede cambiar el modo de su canal.'),403
  mode=settings(conn,channel_id);agreement=conn.execute('SELECT * FROM subscription_agreements WHERE id=?',(mode['agreement_id'] or '',)).fetchone()
  benefits=json.loads(agreement['benefits_json']) if agreement and approvals_valid(conn,agreement) else []
  if any(data[key] and key not in benefits for key in ['subscriber_chat','exclusive_live']):return jsonify(error='Primero deben aprobarse esos beneficios entre las tres partes.'),409
  conn.execute('INSERT INTO channel_subscription_settings(channel_id,subscriber_chat,exclusive_live) VALUES(?,?,?) ON CONFLICT(channel_id) DO UPDATE SET subscriber_chat=excluded.subscriber_chat,exclusive_live=excluded.exclusive_live',(channel_id,int(data['subscriber_chat']),int(data['exclusive_live'])))
 return jsonify(ok=True)

@bp.post('/api/channel-subscriptions/<channel_id>/confirm')
def confirm_subscription(channel_id):
 from payments import provider
 if provider()=='stripe':return jsonify(error='Las suscripciones nuevas se confirman mediante el gestor de pagos, no manualmente.'),409
 user=get_user();data=payload();reference=str(data.get('reference','')).strip()
 if not user or data.get('verified_receipt') is not True or not 4<=len(reference)<=120:return jsonify(error='El creador debe comprobar el ingreso en su PayPal e indicar una referencia única.'),400
 from streamers import streamer_sales_ready
 if not streamer_sales_ready():return jsonify(error='Los pagos esperan a que Ol Live esté disponible.'),409
 try:
  with database() as conn:
   conn.execute('BEGIN IMMEDIATE');channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
   if not channel or user['id']!=channel['member_id'] or not user_public(user)['streamer_active']:return jsonify(error='Solo el creador activo puede confirmar un ingreso en su propio PayPal.'),403
   mode=settings(conn,channel_id);row=conn.execute('SELECT * FROM subscription_agreements WHERE id=?',(mode['agreement_id'] or '',)).fetchone()
   if not row or not approvals_valid(conn,row) or row['paypal_url']!=channel['paypal_url']:return jsonify(error='No hay un acuerdo vigente aprobado por las tres partes.'),409
   if type(data.get('amount_cents')) is not int or data['amount_cents']!=row['price_cents']:return jsonify(error='El importe comprobado debe coincidir exactamente con el precio acordado.'),400
   member=conn.execute("SELECT id FROM members WHERE LOWER(username)=LOWER(?) AND password_hash IS NOT NULL",(str(data.get('username','')).strip(),)).fetchone()
   if not member or member['id']==user['id']:return jsonify(error='Indica la cuenta activada del suscriptor, distinta del creador.'),400
   old=conn.execute('SELECT ends_at FROM creator_subscriptions WHERE channel_id=? AND member_id=? AND revoked_at IS NULL ORDER BY CASE WHEN ends_at IS NULL THEN 0 ELSE 1 END,ends_at DESC LIMIT 1',(channel_id,member['id'])).fetchone()
   if old and old['ends_at'] is None:return jsonify(error='Esta cuenta ya tiene una suscripción sin vencimiento a tu canal.'),409
   start=max(now_utc(),datetime.fromisoformat(old['ends_at'])) if old else now_utc();end=stamp(end_of_plan(start,'monthly')) if row['period']=='month' else None
   conn.execute('INSERT INTO creator_subscriptions(id,channel_id,member_id,agreement_id,amount_cents,benefits_json,starts_at,ends_at,verified_at,verified_by,reference) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),channel_id,member['id'],row['id'],row['price_cents'],row['benefits_json'],stamp(start),end,stamp(now_utc()),user['id'],reference))
  from notifications import notify
  import hashlib
  notify('creator_payment','Ingreso de suscripción confirmado por un creador',f'Un creador ha confirmado un ingreso de {row["price_cents"]/100:.2f} € en su propio PayPal para una suscripción de canal. Este importe no es ingreso ni saldo de electronicama. Revisa los registros privados del canal.',event_key='creator-receipt:'+hashlib.sha256(reference.encode()).hexdigest())
  return jsonify(ok=True,ends_at=end)
 except INTEGRITY_ERRORS:return jsonify(error='Esa referencia ya se utilizó; no se ha duplicado la suscripción.'),409

def install(app):app.register_blueprint(bp)

@bp.get('/api/channel-subscriptions/<channel_id>/members')
def subscriber_members(channel_id):
 user=get_user()
 with database() as conn:
  channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(channel_id,)).fetchone()
  if not channel or not privileged(channel,user):return jsonify(error='El listado de suscriptores es privado.'),403
  try:page=max(1,int(request.args.get('page',1)))
  except ValueError:page=1
  total=conn.execute('SELECT COUNT(*) AS n FROM creator_subscriptions WHERE channel_id=?',(channel_id,)).fetchone()['n']
  rows=conn.execute('SELECT s.starts_at,s.ends_at,s.amount_cents,s.revoked_at,m.username FROM creator_subscriptions s JOIN members m ON m.id=s.member_id WHERE s.channel_id=? ORDER BY s.verified_at DESC,s.id DESC LIMIT 25 OFFSET ?',(channel_id,(page-1)*25)).fetchall()
 return jsonify(members=[dict(r) for r in rows],total=total,page=page,pages=max(1,(total+24)//25))

def enforce_room_subscribers(channel,participants,url,headers):
 """Recheck existing viewers on verified creator heartbeats, not only on entry."""
 import re,requests
 if 'id' not in channel.keys():return True
 with database() as conn:
  if not settings(conn,channel['id'])['exclusive_live']:return True
  allowed={channel['member_id']}|{r['id'] for r in conn.execute("SELECT id FROM members WHERE role='admin'").fetchall()}
  allowed|={r['member_id'] for r in conn.execute('SELECT DISTINCT member_id FROM creator_subscriptions WHERE channel_id=? AND revoked_at IS NULL AND starts_at<=? AND (ends_at IS NULL OR ends_at>?) AND benefits_json LIKE ?',(channel['id'],stamp(now_utc()),stamp(now_utc()),'%"exclusive_live"%')).fetchall()}
 unauthorized=[]
 for p in participants:
  identity=str(p.get('identity',''));matched=re.fullmatch(r'maggy-([a-f0-9]{32})-[a-f0-9]{10}',identity)
  if not matched or matched.group(1) not in allowed:unauthorized.append(identity)
 if len(unauthorized)>5:return False  # Pause the publisher rather than continue an unprotected feed.
 try:
  for identity in unauthorized:
   with requests.post(url+'/twirp/livekit.RoomService/RemoveParticipant',json={'room':channel['room_name'],'identity':identity},headers=headers,timeout=(2,3),allow_redirects=False) as response:
    if response.status_code!=200:return False
 except requests.RequestException:return False
 return True
