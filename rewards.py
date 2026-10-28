"""Account rewards from bounded, server-timed active presence; never money."""
import base64
import binascii
import io
import json
from pathlib import Path
from functools import lru_cache
import re
import secrets
from PIL import Image, UnidentifiedImageError
from datetime import datetime
from flask import Blueprint,jsonify,request,Response
from membership import database,get_user,now_utc,stamp,require_admin
from moderation import validate_public_text,normalized
from sticker_phrases import phrase_for

bp=Blueprint('rewards',__name__)
STICKERS=[
 ('hello','Creador de electronicama',0),('spark','Chispa',1),('wave','Buena onda',5),('heart','Con cariño',15),
 ('star','Estrella electronicama',30),('planet','Una hora en órbita',60),('leaf','A tu ritmo',120),('compass','Explorador',240),
 ('moon','Luz de luna',480),('bolt','Energía compartida',960),('infinity','Sin límites',1440),('crown','Gran colección',2880)]


def init_database():
 with database() as conn:
  conn.executescript('''CREATE TABLE IF NOT EXISTS member_rewards (
    member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
    active_seconds INTEGER NOT NULL DEFAULT 0,last_seen TEXT NOT NULL
  ); CREATE TABLE IF NOT EXISTS sticker_designs (
    id TEXT PRIMARY KEY,name TEXT NOT NULL,points INTEGER NOT NULL,image_data TEXT NOT NULL,updated_at TEXT NOT NULL
  )''')


@lru_cache(maxsize=1)
def illustrated_catalogue():
 path=Path(__file__).parent/'assets'/'stickers'/'catalogue.json'
 return json.loads(path.read_text()) if path.exists() else []


def page_options():
 try:page=max(1,int(request.args.get('page','1')))
 except ValueError:page=1
 return page,request.args.get('q','')[:80],request.args.get('series','')[:60],request.args.get('owned')=='1'


def paged(items,page=1,query='',series='',owned=False):
 query=normalized(query)
 matches=[item for item in items if (not owned or item['unlocked']) and (not series or item.get('series')==series) and (not query or (item['number']==int(query) if query.isdecimal() else query in normalized(item['name']+' '+item.get('series',''))))]
 pages=max(1,(len(matches)+23)//24);page=min(max(1,page),pages)
 return dict(stickers=matches[(page-1)*24:page*24],page=page,pages=pages,filtered_total=len(matches),total=len(items),series=sorted({item.get('series','electronicama') for item in items}))


def catalog(seconds,conn=None):
 if conn is None:
  with database() as connection:return catalog(seconds,connection)
 items={ident:{'id':ident,'name':name,'minutes':minutes,'points':minutes*10,'image':'/assets/stickers/'+ident+'.svg'} for ident,name,minutes in STICKERS}
 items['hello']['image']='/assets/stickers/creator.webp';items['hello']['series']='electronicama'
 illustrated=illustrated_catalogue()
 if illustrated:
  items={'hello':items['hello']}
  items.update({item['id']:dict(item) for item in illustrated})
 for row in conn.execute('SELECT id,name,points,updated_at FROM sticker_designs ORDER BY updated_at,id'):
  items[row['id']]={'id':row['id'],'name':row['name'],'minutes':row['points']//10,'points':row['points'],'image':'/api/stickers/'+row['id']+'/image?v='+row['updated_at'],'series':items.get(row['id'],{}).get('series','Personalizados')}
 ordered=sorted(items.values(),key=lambda item:(item['id']!='hello',item['points'],item['name']))
 for item in ordered:item.setdefault('series','electronicama')
 for number,item in enumerate(ordered,1):item.update(number=number,unlocked=(seconds//60)*10>=item['points'],phrase=phrase_for(item['id']))
 return ordered


def state(seconds,page=1,query='',series='',owned=False):
 minutes=seconds//60;stickers=catalog(seconds);unlocked=[s for s in stickers if s['unlocked']]
 return dict(active_seconds=seconds,minutes=minutes,points=minutes*10,level=1+minutes//60,unlocked=len(unlocked),owned_preview=unlocked[:24],last_milestone_minutes=max((s['minutes'] for s in unlocked),default=0),next_sticker=next((s for s in stickers if not s['unlocked']),None),**paged(stickers,page,query,series,owned))


def owns_sticker(conn,member_id,ident):
 row=conn.execute('SELECT active_seconds FROM member_rewards WHERE member_id=?',(member_id,)).fetchone()
 seconds=row['active_seconds'] if row else 0
 return next((s for s in catalog(seconds,conn) if s['id']==ident and s['unlocked']),None)


@bp.get('/api/rewards')
def rewards():
 with database() as conn:row=conn.execute('SELECT active_seconds FROM member_rewards WHERE member_id=?',(get_user()['id'],)).fetchone()
 return jsonify(state(row['active_seconds'] if row else 0,*page_options()))


@bp.post('/api/rewards/heartbeat')
def heartbeat():
 user=get_user()
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');instant=now_utc()
  row=conn.execute('SELECT * FROM member_rewards WHERE member_id=?',(user['id'],)).fetchone()
  seconds=row['active_seconds'] if row else 0
  if row:
   elapsed=int((instant-datetime.fromisoformat(row['last_seen'])).total_seconds())
   # A clock rollback or absent heartbeat never grants stored/offline hours.
   if 0<elapsed<=90:seconds+=elapsed
   if elapsed>0:conn.execute('UPDATE member_rewards SET active_seconds=?,last_seen=? WHERE member_id=?',(seconds,stamp(instant),user['id']))
  else:conn.execute('INSERT INTO member_rewards(member_id,active_seconds,last_seen) VALUES(?,?,?)',(user['id'],0,stamp(instant)))
 return jsonify(state(seconds,*page_options()))


@bp.get('/api/rewards/collections')
def collection_sheets():
 path=Path(__file__).parent/'assets'/'stickers'/'sheets'/'index.json'
 return jsonify(collections=json.loads(path.read_text()) if path.exists() else [])


@bp.get('/api/stickers/<ident>/image')
def sticker_image(ident):
 with database() as conn:row=conn.execute('SELECT image_data FROM sticker_designs WHERE id=?',(ident,)).fetchone()
 if not row:return jsonify(error='Este diseño no existe.'),404
 return Response(base64.b64decode(row['image_data']),mimetype='image/webp',headers={'Cache-Control':'private, max-age=3600'})


@bp.get('/api/admin/stickers')
@require_admin
def admin_stickers():
 return jsonify(paged(catalog(0),*page_options()))


@bp.post('/api/admin/stickers')
@require_admin
def save_design():
 data=request.get_json(silent=True) or {};name=data.get('name');points=data.get('points');encoded=data.get('image');ident=data.get('id') or 'custom_'+secrets.token_hex(12)
 if not isinstance(name,str) or not 2<=len(name.strip())<=60 or isinstance(points,bool) or not isinstance(points,int) or not 0<=points<=1000000 or points%10 or not isinstance(ident,str) or not re.fullmatch('[a-z0-9_-]{1,60}',ident):
  return jsonify(error='Indica un nombre de 2 a 60 caracteres y puntos en múltiplos de 10.'),400
 if ident=='hello' and points!=0:return jsonify(error='El sticker número 1 del creador siempre es gratuito.'),400
 if not isinstance(encoded,str) or len(encoded)>60000:return jsonify(error='La imagen es demasiado grande. Elige una imagen PNG, JPG o WebP.'),400
 try:
  validate_public_text(name)
  raw=base64.b64decode(encoded,validate=True)
  with Image.open(io.BytesIO(raw)) as original:
   if original.format not in {'PNG','JPEG','WEBP'} or original.width*original.height>1000000 or getattr(original,'is_animated',False):raise ValueError('format')
   image=original.convert('RGBA');image.thumbnail((256,256));buffer=io.BytesIO();image.save(buffer,format='WEBP',quality=90,method=4)
  output=base64.b64encode(buffer.getvalue()).decode('ascii')
 except (ValueError,TypeError,binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError):
  return jsonify(error='Imagen no válida. Usa una imagen estática PNG, JPG o WebP y un nombre respetuoso.'),400
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');existing={item['id']:item for item in catalog(0,conn)}
  if ident in existing and points!=existing[ident]['points']:
   return jsonify(error='Un diseño existente conserva sus puntos para respetar las colecciones. Crea uno nuevo para elegir otro umbral.'),409
  if ident not in existing and conn.execute('SELECT COUNT(*) AS n FROM sticker_designs').fetchone()['n']>=1000:return jsonify(error='El catálogo admite hasta 1000 diseños personalizados.'),409
  conn.execute('INSERT INTO sticker_designs(id,name,points,image_data,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,image_data=excluded.image_data,updated_at=excluded.updated_at',(ident,name.strip(),points,output,stamp(now_utc())))
 return jsonify(ok=True,id=ident)


def install(app):
 with app.app_context():init_database()
 app.register_blueprint(bp)
