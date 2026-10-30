"""Private R2/LiveKit recordings. Disabled until storage and retention are configured."""
import os,secrets,time
from datetime import timedelta,datetime
from urllib.parse import urlparse
from flask import Blueprint,jsonify,request
from membership import database,get_user,require_admin,now_utc,stamp,payload
bp=Blueprint('recordings',__name__)
RETENTION_DAYS=30

def configuration():
 keys=['R2_ENDPOINT','R2_BUCKET','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY']
 present=all(os.getenv(k,'').strip() for k in keys)
 endpoint=urlparse(os.getenv('R2_ENDPOINT',''))
 valid=endpoint.scheme=='https' and bool(endpoint.hostname and endpoint.hostname.endswith('.r2.cloudflarestorage.com')) and not endpoint.username and not endpoint.password and not endpoint.query and not endpoint.fragment and endpoint.path in {'','/'}
 return {'enabled':os.getenv('OL_RECORDINGS_ENABLED')=='1','storage_configured':bool(present and valid),'retention_confirmed':os.getenv('OL_RECORDING_RETENTION_CONFIRMED')=='1','retention_days':RETENTION_DAYS}

def ready():
 info=configuration();return info['enabled'] and info['storage_configured'] and info['retention_confirmed']

def init_database():
 with database() as conn:conn.executescript('''CREATE TABLE IF NOT EXISTS live_recordings(id TEXT PRIMARY KEY,channel_id TEXT NOT NULL REFERENCES streamer_channels(id),owner_id TEXT NOT NULL REFERENCES members(id),room_name TEXT NOT NULL,egress_id TEXT UNIQUE,object_key TEXT NOT NULL UNIQUE,state TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,expires_at TEXT NOT NULL,updated_at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS recordings_channel_state ON live_recordings(channel_id,state); CREATE INDEX IF NOT EXISTS recordings_expiry ON live_recordings(expires_at);''')

def rpc(method,data):
 import requests
 from streamers import sign_token
 now=int(time.time());token=sign_token({'iss':os.environ['LIVEKIT_API_KEY'].strip(),'iat':now,'nbf':now-5,'exp':now+45,'video':{'roomRecord':True}})
 url='https://'+urlparse(os.environ['LIVEKIT_URL']).netloc+'/twirp/livekit.Egress/'+method
 with requests.post(url,json=data,headers={'Authorization':'Bearer '+token},timeout=(3,15),allow_redirects=False) as response:
  if response.status_code!=200:raise RuntimeError('recording_service_unavailable')
  return response.json()

def storage():
 import boto3
 from botocore.config import Config
 return boto3.client('s3',endpoint_url=os.environ['R2_ENDPOINT'],aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],region_name='auto',config=Config(signature_version='s3v4',connect_timeout=3,read_timeout=10,retries={'max_attempts':1}))

def ensure_started(channel,user):
 if not configuration()['enabled']:return
 if not ready():raise RuntimeError('recording_not_configured')
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  current=conn.execute("SELECT * FROM live_recordings WHERE channel_id=? AND state IN ('starting','active','stopping','uncertain') ORDER BY started_at DESC LIMIT 1",(channel['id'],)).fetchone()
  if not current:
   ident=secrets.token_hex(16);key='directos/'+now_utc().strftime('%Y/%m/%d')+'/'+ident+'.mp4';instant=stamp(now_utc())
   conn.execute('INSERT INTO live_recordings(id,channel_id,owner_id,room_name,object_key,state,started_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(ident,channel['id'],user['id'],channel['room_name'],key,'starting',instant,stamp(now_utc()+timedelta(days=RETENTION_DAYS)),instant))
 if current:
  if current['room_name']!=channel['room_name']:raise RuntimeError('recording_needs_review')
  if current['state'] in {'uncertain','stopping'} or not current['egress_id']:raise RuntimeError('recording_needs_review')
  try:items=rpc('ListEgress',{'egress_id':current['egress_id']}).get('items',[])
  except Exception:raise RuntimeError('recording_status_unconfirmed') from None
  status=items[0].get('status') if items else None
  if status in {1,'EGRESS_ACTIVE'}:
   with database() as conn:conn.execute("UPDATE live_recordings SET state='active',updated_at=? WHERE id=?",(stamp(now_utc()),current['id']))
   return
  if status in {0,'EGRESS_STARTING'}:raise RuntimeError('recording_start_pending')
  raise RuntimeError('recording_not_active')
 try:
  result=rpc('StartRoomCompositeEgress',{'room_name':channel['room_name'],'layout':'grid','file_outputs':[{'file_type':1,'filepath':key,'disable_manifest':True,'s3':{'access_key':os.environ['R2_ACCESS_KEY_ID'],'secret':os.environ['R2_SECRET_ACCESS_KEY'],'region':'auto','endpoint':os.environ['R2_ENDPOINT'],'bucket':os.environ['R2_BUCKET'],'force_path_style':True}}]})
  if not result.get('egress_id'):raise RuntimeError('recording_start_unconfirmed')
 except Exception:
  with database() as conn:conn.execute("UPDATE live_recordings SET state='uncertain',updated_at=? WHERE id=?",(stamp(now_utc()),ident))
  raise RuntimeError('recording_start_unconfirmed') from None
 active=result.get('status') in {1,'EGRESS_ACTIVE'}
 with database() as conn:conn.execute('UPDATE live_recordings SET egress_id=?,state=?,updated_at=? WHERE id=?',(result['egress_id'],'active' if active else 'starting',stamp(now_utc()),ident))
 if not active:raise RuntimeError('recording_start_pending')


def stop_recording(channel_id):
 with database() as conn:rows=conn.execute("SELECT * FROM live_recordings WHERE channel_id=? AND state IN ('active','starting') AND egress_id IS NOT NULL",(channel_id,)).fetchall()
 for row in rows:
  try:
   rpc('StopEgress',{'egress_id':row['egress_id']})
   with database() as conn:conn.execute("UPDATE live_recordings SET state='stopping',ended_at=?,expires_at=?,updated_at=? WHERE id=?",(stamp(now_utc()),stamp(now_utc()+timedelta(days=RETENTION_DAYS)),stamp(now_utc()),row['id']))
  except Exception:pass # Keep active for an administrator retry; never report success.

def reconcile_recording(row):
 if not row['egress_id'] or row['state'] not in {'active','stopping'}:return
 info=rpc('ListEgress',{'egress_id':row['egress_id']});items=info.get('items',[])
 if not items:return
 status=items[0].get('status')
 state='completed' if status in {3,'EGRESS_COMPLETE'} else 'failed' if status in {4,5,6,'EGRESS_FAILED','EGRESS_ABORTED','EGRESS_LIMIT_REACHED'} else None
 if state:
  with database() as conn:conn.execute('UPDATE live_recordings SET state=?,ended_at=COALESCE(ended_at,?),expires_at=?,updated_at=? WHERE id=?',(state,stamp(now_utc()),row['expires_at'] if row['ended_at'] else stamp(now_utc()+timedelta(days=RETENTION_DAYS)),stamp(now_utc()),row['id']))

@bp.get('/api/admin/recordings')
@require_admin
def listing():
 with database() as conn:rows=conn.execute('SELECT r.id,r.channel_id,c.title,r.state,r.started_at,r.ended_at,r.expires_at FROM live_recordings r JOIN streamer_channels c ON c.id=r.channel_id ORDER BY r.started_at DESC LIMIT 100').fetchall()
 response=jsonify(configuration=configuration(),recordings=[dict(row) for row in rows]);response.headers['Cache-Control']='no-store';return response

@bp.post('/api/admin/recordings/reconcile')
@require_admin
def reconcile():
 if not ready():return jsonify(error='Configura primero R2, retención y grabación de LiveKit.'),409
 ident=str(payload().get('id',''))
 with database() as conn:row=conn.execute('SELECT * FROM live_recordings WHERE id=?',(ident,)).fetchone()
 if not row:return jsonify(error='Grabación no encontrada.'),404
 try:reconcile_recording(row)
 except Exception:return jsonify(error='No se pudo comprobar el estado de la grabación.'),503
 return jsonify(ok=True)

@bp.get('/api/admin/recordings/<ident>/link')
@require_admin
def private_link(ident):
 with database() as conn:row=conn.execute('SELECT * FROM live_recordings WHERE id=?',(ident,)).fetchone()
 if not row:return jsonify(error='Grabación no encontrada.'),404
 remaining=int((datetime.fromisoformat(row['expires_at'])-now_utc()).total_seconds())
 if row['state']!='completed' or remaining<=0:return jsonify(error='La grabación no está disponible o ha caducado.'),410
 if not ready():return jsonify(error='Almacenamiento pendiente de configuración.'),409
 try:url=storage().generate_presigned_url('get_object',Params={'Bucket':os.environ['R2_BUCKET'],'Key':row['object_key']},ExpiresIn=min(120,remaining))
 except Exception:return jsonify(error='No se pudo abrir el archivo privado.'),503
 response=jsonify(url=url,expires_in=min(120,remaining));response.headers['Cache-Control']='no-store';return response

@bp.post('/api/admin/recordings/cleanup')
@require_admin
def cleanup():
 if not ready():return jsonify(error='R2 no está configurado.'),409
 with database() as conn:rows=conn.execute("SELECT id,object_key FROM live_recordings WHERE expires_at<=? AND state NOT IN ('deleted','active','starting','uncertain') LIMIT 50",(stamp(now_utc()),)).fetchall()
 deleted=0
 for row in rows:
  try:
   storage().delete_object(Bucket=os.environ['R2_BUCKET'],Key=row['object_key'])
   with database() as conn:conn.execute("UPDATE live_recordings SET state='deleted',updated_at=? WHERE id=?",(stamp(now_utc()),row['id']))
   deleted+=1
  except Exception:continue
 return jsonify(deleted=deleted,pending=len(rows)-deleted)

def install(app):app.register_blueprint(bp)
