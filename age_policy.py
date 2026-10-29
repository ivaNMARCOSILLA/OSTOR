"""Adult-content declarations; IP is not proof of age or a reliable VPN detector."""
import hashlib,secrets,os,re
from datetime import date,timedelta
from flask import Blueprint,current_app,jsonify,request
from membership import database,get_user,now_utc,stamp,payload,require_admin
bp=Blueprint('age_policy',__name__)

def init_database():
 with database() as conn:
  conn.executescript('''CREATE TABLE IF NOT EXISTS adult_channel_rules(channel_id TEXT PRIMARY KEY REFERENCES streamer_channels(id) ON DELETE CASCADE,adult_content INTEGER NOT NULL DEFAULT 0,version TEXT NOT NULL,locked INTEGER NOT NULL DEFAULT 0);
  CREATE TABLE IF NOT EXISTS adult_age_declarations(member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,context TEXT NOT NULL,minimum_age INTEGER NOT NULL,expires_at TEXT NOT NULL,PRIMARY KEY(member_id,context)); CREATE INDEX IF NOT EXISTS adult_declaration_expiry ON adult_age_declarations(expires_at);''')

def regional_requirement():
 # Only a server-side provider may assess country and VPN/proxy status. No client
 # country or age header is trusted. Without that service, fall back to 21.
 country=None;vpn='unknown'
 if os.getenv('VERCEL')=='1':
  supplied=request.headers.get('x-vercel-ip-country','')
  if re.fullmatch('[A-Z]{2}',supplied):country=supplied
 assessor=current_app.extensions.get('adult_region_assessor')
 if assessor:
  try:
   assessment=assessor(request)
   if assessment.get('trusted') is True:
    country=assessment.get('country') if isinstance(assessment.get('country'),str) else None;candidate=assessment.get('vpn','unknown');vpn=candidate if isinstance(candidate,bool) else 'unknown'
  except Exception:pass
 minimum=18 if country=='ES' and vpn is False else 21
 return {'minimum_age':minimum,'country':country,'location_uncertain':vpn is not False or country not in {'ES','US'},'vpn_assessed':vpn in {True,False},'age_verification':'self_declaration'}

def policy(conn,channel_id):
 row=conn.execute('SELECT * FROM adult_channel_rules WHERE channel_id=?',(channel_id,)).fetchone()
 regional=regional_requirement();version=row['version'] if row else 'general'
 context=hashlib.sha256(('adult-v1|'+channel_id+'|'+version+'|'+str(regional)).encode()).hexdigest()
 return regional|{'adult_content':bool(row and row['adult_content']),'context':context}

def gate(conn,channel_id,user):
 info=policy(conn,channel_id)
 if not info['adult_content']:return None
 declared=conn.execute('SELECT minimum_age FROM adult_age_declarations WHERE member_id=? AND context=? AND expires_at>?',(user['id'],info['context'],stamp(now_utc()))).fetchone()
 if declared and declared['minimum_age']>=info['minimum_age']:return None
 return jsonify(error='Este directo contiene tabaco, vapeo o alcohol y requiere declaración de mayoría de edad.',code='adult_age_required',minimum_age=info['minimum_age']),403

@bp.get('/api/streamers/<channel_id>/age-policy')
def age_information(channel_id):
 user=get_user()
 if not user:return jsonify(error='Entra con tu cuenta.'),401
 with database() as conn:
  if not conn.execute('SELECT id FROM streamer_channels WHERE id=?',(channel_id,)).fetchone():return jsonify(error='Canal no encontrado.'),404
  info=policy(conn,channel_id);info['accepted']=gate(conn,channel_id,user) is None
 response=jsonify(info);response.headers['Cache-Control']='no-store';return response

@bp.post('/api/streamers/<channel_id>/age-confirm')
def confirm_age(channel_id):
 user=get_user();data=payload()
 if not user:return jsonify(error='Entra con tu cuenta.'),401
 with database() as conn:
  if not conn.execute('SELECT id FROM streamer_channels WHERE id=?',(channel_id,)).fetchone():return jsonify(error='Canal no encontrado.'),404
  info=policy(conn,channel_id)
  if data.get('context')!=info['context']:return jsonify(error='La ubicación o las condiciones han cambiado. Vuelve a comprobarlas.'),409
  if data.get('accept_rules') is not True:return jsonify(error='Debes aceptar las condiciones del contenido adulto.'),400
  try:
   born=date.fromisoformat(str(data.get('birth_date','')));today=now_utc().date();age=today.year-born.year-((today.month,today.day)<(born.month,born.day))
  except ValueError:return jsonify(error='Indica una fecha de nacimiento válida.'),400
  if age<info['minimum_age'] or age>120:return jsonify(error='No cumples la edad mínima para este directo.',code='age_not_met'),403
  conn.execute('DELETE FROM adult_age_declarations WHERE expires_at<=?',(stamp(now_utc()),))
  conn.execute('INSERT INTO adult_age_declarations(member_id,context,minimum_age,expires_at) VALUES(?,?,?,?) ON CONFLICT(member_id,context) DO UPDATE SET minimum_age=excluded.minimum_age,expires_at=excluded.expires_at',(user['id'],info['context'],info['minimum_age'],stamp(now_utc()+timedelta(hours=24))))
 return jsonify(ok=True,minimum_age=info['minimum_age'],age_verification='self_declaration')

def save_rules(conn,channel_id,data):
 if 'adult_content' not in data:return
 existing=conn.execute('SELECT locked FROM adult_channel_rules WHERE channel_id=?',(channel_id,)).fetchone()
 if existing and existing['locked']:return
 conn.execute('INSERT INTO adult_channel_rules(channel_id,adult_content,version) VALUES(?,?,?) ON CONFLICT(channel_id) DO UPDATE SET adult_content=excluded.adult_content,version=CASE WHEN adult_channel_rules.adult_content!=excluded.adult_content THEN excluded.version ELSE adult_channel_rules.version END',(channel_id,int(data['adult_content']),secrets.token_hex(16)))

@bp.post('/api/admin/live-channels/adult-content')
@require_admin
def moderate_classification():
 data=payload();channel_id=str(data.get('channel_id',''))
 if not isinstance(data.get('adult_content'),bool):return jsonify(error='Clasificación no válida.'),400
 with database() as conn:
  if not conn.execute('SELECT id FROM streamer_channels WHERE id=?',(channel_id,)).fetchone():return jsonify(error='Canal no encontrado.'),404
  conn.execute('INSERT INTO adult_channel_rules(channel_id,adult_content,version,locked) VALUES(?,?,?,?) ON CONFLICT(channel_id) DO UPDATE SET adult_content=excluded.adult_content,version=excluded.version,locked=excluded.locked',(channel_id,int(data['adult_content']),secrets.token_hex(16),int(data['adult_content'])))
 return jsonify(ok=True)

def install(app):app.register_blueprint(bp)
