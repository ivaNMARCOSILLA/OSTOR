"""One hundred numbered, durable Ol Live founding-creator places."""
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
 user=get_user()
 with database() as conn:
  claimed=conn.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']
  mine=conn.execute('SELECT number,claimed_at,revoked_at FROM live_founders WHERE member_id=?',(user['id'],)).fetchone() if user else None
 if mine:
  with database() as conn:preferences=conn.execute('SELECT mode AS badge_mode,letter AS badge_letter,caption AS badge_caption,audio_json AS badge_audio FROM founder_signatures WHERE member_id=?',(user['id'],)).fetchone()
  mine=dict(mine);mine['signature']=signature_from_row(preferences or {})
 return jsonify(limit=LIMIT,claimed=claimed,remaining=max(0,LIMIT-claimed),mine=mine if mine else None,lifetime=True)

@bp.post('/api/live/founders/claim')
def claim():
 user=get_user()
 if not user:return jsonify(error='Crea una cuenta gratuita o inicia sesión para reservar tu plaza.'),401
 if not allow_attempt('founder-claim',12):return jsonify(error='Demasiados intentos. Espera unos minutos.'),429
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  existing=conn.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(user['id'],)).fetchone()
  if existing:
   if existing['revoked_at']:return jsonify(error='Esta plaza fue revocada. Contacta con administración; no se puede reclamar otra.'),403
   return jsonify(ok=True,number=existing['number'],already_claimed=True,lifetime=True)
  total=conn.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']
  if total>=LIMIT:return jsonify(error='Las 100 plazas gratuitas de fundador ya están reservadas.'),409
  number=total+1
  conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(user['id'],number,stamp(now_utc())))
 notify('founder','Nueva plaza Ol Live fundadores',f'Se ha reservado la plaza {number} de 100. Incluye acceso de creador sin vencimiento e insignia. Consulta la cuenta en administración.',event_key='founder:'+user['id'])
 return jsonify(ok=True,number=number,already_claimed=False,lifetime=True)

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
