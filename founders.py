"""One hundred numbered, durable Ol Livis founding-creator places."""
from flask import Blueprint,jsonify
from membership import database,get_user,now_utc,stamp,allow_attempt,require_admin,payload
from notifications import notify
bp=Blueprint('founders',__name__)
LIMIT=100

@bp.before_request
def limit_requests():
 from flask import current_app
 limiter=current_app.extensions.get('streamer_rate_limiter')
 if limiter and not limiter('founders',120):return jsonify(error='Espera un momento antes de volver a consultar la promoción.'),429

@bp.get('/api/live/founders')
def status():
 from founder_slots import cleanup,reservation
 cleanup()
 user=get_user()
 with database() as conn:
  claimed=conn.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']
  mine=conn.execute('SELECT number,claimed_at,revoked_at FROM live_founders WHERE member_id=?',(user['id'],)).fetchone() if user else None
 if mine:
  with database() as conn:preferences=conn.execute('SELECT mode AS badge_mode,letter AS badge_letter,caption AS badge_caption,audio_json AS badge_audio FROM founder_signatures WHERE member_id=?',(user['id'],)).fetchone()
  mine=dict(mine)
  with database() as conn:mine['reservation']=reservation(conn,user['id'])
  from live_access import founder_activity
  with database() as conn:mine['activity']=founder_activity(user['id'],conn)
  mine['signature']=signature_from_row(preferences or {})
 if mine:mine['future_transfer_eligible']=mine['number']==1
 return jsonify(limit=LIMIT,claimed=claimed,remaining=max(0,LIMIT-claimed),mine=mine if mine else None,lifetime=False,transfer_sales_open=False,activity_required=True,payment_required=True,trial_months=0,trial_days=0,billing_period='year')

@bp.post('/api/live/founders/claim')
def claim():
 from operations import premiere
 if premiere():return jsonify(error='Ol Livis · próximo estreno. Las plazas aún no están abiertas.'),409
 user=get_user()
 if not user:return jsonify(error='Crea una cuenta gratuita o inicia sesión para reservar tu plaza.'),401
 if not allow_attempt('founder-claim',12):return jsonify(error='Demasiados intentos. Espera unos minutos.'),429
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  from founder_slots import release_expired,reserve
  release_expired(conn)
  existing=conn.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(user['id'],)).fetchone()
  if existing:
   if existing['revoked_at']:return jsonify(error='Esta plaza fue revocada. Contacta con administración; no se puede reclamar otra.'),403
   return jsonify(ok=True,number=existing['number'],already_claimed=True,lifetime=False,payment_required=True)
  from human_check import verify
  if not verify(conn):return jsonify(error='Completa la comprobación visual antes de reservar. El código caduca y solo se usa una vez.'),400
  from membership import user_public
  if not user_public(user).get('full_service') and not user_public(user).get('live_annual') and not user_public(user).get('live_lifetime'):return jsonify(error='Primero contrata Ol Livis por 25 € al año. Las plazas requieren un pago confirmado.'),409
  number=reserve(conn,user['id'])
  if number is None:return jsonify(error='Las 100 plazas están ocupadas.'),409
 notify('founder','Nueva plaza Ol Livis fundadores',f'Se ha reservado la plaza {number} de 100. Acceso anual confirmado. Para conservarla se debe renovar el acceso de 25 € al año y mantener la actividad indicada. Consulta la cuenta en administración.',event_key='founder:'+user['id'])
 return jsonify(ok=True,number=number,already_claimed=False,lifetime=False,payment_required=True)

@bp.post('/api/admin/founders/revoke')
@require_admin
def revoke_founder():
 ident=str(payload().get('member_id',''))
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  conn.execute('UPDATE live_founders SET revoked_at=? WHERE member_id=?',(stamp(now_utc()),ident))
  conn.execute("UPDATE members SET session_version=session_version+1 WHERE id=? AND role!='admin'",(ident,))
 return jsonify(ok=True)

def install(app):app.register_blueprint(bp)


def signature_from_row(row):
 import json
 keys=row.keys();audio=None
 if 'badge_audio' in keys and row['badge_audio']:
  try:audio=json.loads(row['badge_audio'])
  except (ValueError,TypeError):audio=None
 return {'mode':row['badge_mode'] if 'badge_mode' in keys and row['badge_mode'] else 'numero','letter':row['badge_letter'] if 'badge_letter' in keys and row['badge_letter'] else '', 'caption':row['badge_caption'] if 'badge_caption' in keys and row['badge_caption'] else 'Buen rollo', 'audio':audio}


@bp.get('/api/live/founders/audio-search')
def audio_search():
 from flask import current_app,request
 from membership import user_public
 from itsdangerous import URLSafeTimedSerializer
 from concurrent.futures import ThreadPoolExecutor
 user=get_user()
 if not user or not user_public(user)['founder_active']:return jsonify(error='Personalizar una insignia requiere una plaza de fundador activa.'),403
 limiter=current_app.extensions.get('streamer_rate_limiter')
 if limiter and not limiter('founder-audio-search',20):return jsonify(error='Espera un momento antes de volver a buscar.'),429
 from app import multi_search,search_commons,sanitize_query
 query=sanitize_query(request.args.get('q',''))
 if not query:return jsonify(tracks=[])
 with ThreadPoolExecutor(max_workers=2) as pool:
  main=pool.submit(multi_search,query);commons=pool.submit(search_commons,query,10)
  candidates=(main.result() or [])[:8]+(commons.result() or [])[:4]
 signer=URLSafeTimedSerializer(current_app.secret_key,salt='ol-founder-audio');tracks=[];seen=set()
 fields={'id','title','channel','source','license','license_url','attribution','page_url','url'}
 for candidate in candidates:
  if candidate['id'] in seen:continue
  seen.add(candidate['id']);track={key:value for key,value in candidate.items() if key in fields}
  tracks.append({'track':track,'token':signer.dumps({'member':user['id'],'track':track})})
 return jsonify(tracks=tracks)


@bp.post('/api/live/founders/signature')
def save_signature():
 import json
 from flask import current_app
 from itsdangerous import URLSafeTimedSerializer,BadSignature,SignatureExpired
 from membership import user_public
 from moderation import validate_public_text
 user=get_user()
 if not user or not user_public(user)['founder_active']:return jsonify(error='Esta personalización requiere tu plaza de fundador activa.'),403
 data=payload();mode=data.get('mode');letter=str(data.get('letter','')).strip().upper();caption=str(data.get('caption','')).strip()
 if mode not in {'numero','letra','cancion','sonido'} or len(caption)>40 or (mode=='letra' and (len(letter)!=1 or not letter.isalpha())):
  return jsonify(error='Elige número, una letra, canción o sonido, y una frase de hasta 40 caracteres.'),400
 try:validate_public_text(caption)
 except ValueError as error:return jsonify(error=str(error)),400
 audio=None
 with database() as conn:
  previous=conn.execute('SELECT audio_json FROM founder_signatures WHERE member_id=?',(user['id'],)).fetchone()
 if mode=='cancion':
  token=data.get('audio_token')
  if token:
   try:
    signed=URLSafeTimedSerializer(current_app.secret_key,salt='ol-founder-audio').loads(token,max_age=3600)
    if signed.get('member')!=user['id']:raise BadSignature('owner')
    audio={'kind':'track','track':signed['track']}
   except (BadSignature,SignatureExpired,KeyError,TypeError):return jsonify(error='Vuelve a elegir una canción de los resultados de búsqueda.'),400
  elif data.get('keep_audio') is True and previous and previous['audio_json']:
   audio=json.loads(previous['audio_json'])
   if audio.get('kind')!='track':return jsonify(error='Elige una canción de los resultados.'),400
  else:return jsonify(error='Busca y elige una canción o grabación gratuita.'),400
 elif mode=='sonido':
  voice=data.get('voice','brisa')
  if voice not in {'brisa','aurora','sonrisa','ritmo','estrellas','celebracion'}:return jsonify(error='Elige uno de los sonidos disponibles.'),400
  audio={'kind':'tone','voice':voice}
 with database() as conn:
  conn.execute('INSERT INTO founder_signatures(member_id,mode,letter,caption,audio_json,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(member_id) DO UPDATE SET mode=excluded.mode,letter=excluded.letter,caption=excluded.caption,audio_json=excluded.audio_json,updated_at=excluded.updated_at',(user['id'],mode,letter if mode=='letra' else '',caption,json.dumps(audio,ensure_ascii=False) if audio else None,stamp(now_utc())))
 return jsonify(ok=True,number=user['founder_number'],signature={'mode':mode,'letter':letter if mode=='letra' else '', 'caption':caption or 'Buen rollo','audio':audio})

@bp.get('/api/admin/founders/activity')
@require_admin
def activity_directory():
 from founder_slots import cleanup
 cleanup()
 from flask import request
 from live_access import founder_activity
 try:page=max(1,int(request.args.get('page',1)))
 except ValueError:page=1
 with database() as conn:
  total=conn.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']
  rows=conn.execute('SELECT f.*,m.username FROM live_founders f JOIN members m ON m.id=f.member_id ORDER BY f.number LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
  results=[dict(row)|{'activity':founder_activity(row['member_id'],conn)} for row in rows]
 return jsonify(founders=results,total=total,page=page,pages=max(1,(total+24)//25))

@bp.post('/api/admin/founders/grace')
@require_admin
def extend_grace():
 from datetime import timedelta
 data=payload();days=data.get('days');ident=str(data.get('member_id',''))
 if type(days) is not int or not 1<=days<=365:return jsonify(error='Indica de 1 a 365 días para revisar la incidencia.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  founder=conn.execute('SELECT * FROM live_founders WHERE member_id=?',(ident,)).fetchone()
  if not founder or founder['revoked_at']:return jsonify(error='La plaza no está disponible para ampliar su plazo.'),404
  from live_access import founder_activity
  from datetime import datetime
  previous=founder_activity(ident,conn)['qualification_until']
  base=max(now_utc(),datetime.fromisoformat(previous)) if previous else now_utc()
  deadline=stamp(base+timedelta(days=days))
  conn.execute('INSERT INTO founder_activity(member_id,qualification_until) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET qualification_until=excluded.qualification_until',(ident,deadline))
 return jsonify(ok=True,qualification_until=deadline)

@bp.get('/api/admin/founders/history')
@require_admin
def slot_history():
 from founder_slots import cleanup
 cleanup()
 from flask import request
 try:page=max(1,int(request.args.get('page',1)))
 except ValueError:page=1
 with database() as conn:
  total=conn.execute('SELECT COUNT(*) AS n FROM founder_slot_history').fetchone()['n']
  rows=conn.execute('SELECT h.number,h.claimed_at,h.trial_until,h.released_at,h.reason,m.username FROM founder_slot_history h JOIN members m ON m.id=h.member_id ORDER BY h.released_at DESC,h.id DESC LIMIT 25 OFFSET ?',((page-1)*25,)).fetchall()
 return jsonify(history=[dict(row) for row in rows],total=total,page=page,pages=max(1,(total+24)//25))
