"""Ol Live: one three-month trial, one fixed price, verified creator activity."""
import calendar,os,time
from datetime import datetime,timedelta
from flask import Blueprint,jsonify
from membership import database,get_user,now_utc,stamp,payload
bp=Blueprint('live_access',__name__)
PRICE_CENTS=2500
INITIAL_MINUTES=30
MONTHLY_MINUTES=120

def months_after(instant,months=3):
 month=instant.month-1+months;year=instant.year+month//12;month=month%12+1
 return instant.replace(year=year,month=month,day=min(instant.day,calendar.monthrange(year,month)[1]))

def details(member_id,conn):
 row=conn.execute('SELECT * FROM live_entitlements WHERE member_id=?',(member_id,)).fetchone()
 return dict(row) if row else {}

def founder_activity(member_id,conn):
 row=conn.execute('SELECT * FROM founder_activity WHERE member_id=?',(member_id,)).fetchone();row=dict(row) if row else {}
 start=(now_utc().date()-timedelta(days=29)).isoformat()
 recent=conn.execute('SELECT COALESCE(SUM(seconds),0) AS n FROM creator_daily_activity WHERE member_id=? AND day>=?',(member_id,start)).fetchone()['n']
 deadline=row.get('qualification_until')
 if not deadline:
  launch=conn.execute("SELECT started_at FROM live_launch WHERE id='live'").fetchone()
  if launch:deadline=stamp(months_after(datetime.fromisoformat(launch['started_at'])))
 qualified=bool(row.get('first_completed_at'))
 grace=not deadline or deadline>stamp(now_utc())
 from founder_slots import reservation
 slot=reservation(conn,member_id)
 payment_current=not slot or slot['confirmed'] or not slot['trial_until'] or slot['trial_until']>stamp(now_utc())
 return dict(payment_current=payment_current,initial_minutes=INITIAL_MINUTES,monthly_minutes=MONTHLY_MINUTES,verified_seconds=row.get('total_seconds',0),recent_seconds=recent,qualification_until=deadline,first_completed_at=row.get('first_completed_at'),qualified=qualified,eligible=payment_current and (grace or (qualified and recent>=MONTHLY_MINUTES*60)),provisional=not qualified)

@bp.post('/api/account/live-trial')
def trial():
 user=get_user()
 if not user:return jsonify(error='Entra en tu cuenta para iniciar la prueba.'),401
 from streamers import live_ready
 if not live_ready() or not video_service_available():return jsonify(error='Tus tres meses empezarán cuando Ol Live esté disponible. Todavía no consumimos tu prueba.'),409
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE')
  from founder_slots import release_expired,reserve
  release_expired(conn);existing=details(user['id'],conn)
  own=conn.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(user['id'],)).fetchone()
  if existing:return jsonify(ok=True,trial_until=existing.get('trial_until'),already_started=True,founder_number=own['number'] if own else None)
  if not own:
   used=conn.execute('SELECT COUNT(*) AS n FROM live_founders').fetchone()['n']
   if used>=100:return jsonify(error='Las 100 plazas de prueba están reservadas. Vuelve cuando quede una disponible.'),409
   from human_check import verify
   if not verify(conn):return jsonify(error='Completa la comprobación visual para reservar una plaza de prueba.',code='human_required'),400
  elif own['revoked_at']:return jsonify(error='Tu plaza fue desactivada. Contacta con administración.'),403
  number=reserve(conn,user['id'])
  if number is None:return jsonify(error='Las 100 plazas de prueba están reservadas.'),409
  start=now_utc();end=months_after(start)
  conn.execute("INSERT INTO live_launch(id,started_at) VALUES('live',?) ON CONFLICT(id) DO NOTHING",(stamp(start),))
  conn.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until) VALUES(?,?,?)',(user['id'],stamp(start),stamp(end)))
  if number:
   conn.execute('INSERT INTO founder_activity(member_id,qualification_until) VALUES(?,?) ON CONFLICT(member_id) DO NOTHING',(user['id'],stamp(end)))
 return jsonify(ok=True,trial_until=stamp(end),already_started=False,founder_number=number)

def verified_broadcast(channel,user):
 """Ask LiveKit for actual published tracks; never trust the browser's live flag."""
 import requests
 from urllib.parse import urlparse
 from streamers import sign_token
 instant=int(time.time());token=sign_token({'iss':os.environ['LIVEKIT_API_KEY'].strip(),'iat':instant,'nbf':instant-5,'exp':instant+45,'video':{'roomAdmin':True,'room':channel['room_name']}})
 try:
  with requests.post('https://'+urlparse(os.environ['LIVEKIT_URL']).netloc+'/twirp/livekit.RoomService/ListParticipants',json={'room':channel['room_name']},headers={'Authorization':'Bearer '+token},timeout=(2,4),allow_redirects=False) as response:
   if response.status_code!=200:return False
   data=response.json()
   return any(str(p.get('identity','')).startswith('maggy-'+user['id']+'-') and any(t.get('source') in (1,3,'CAMERA','SCREEN_SHARE') and not t.get('muted',False) for t in p.get('tracks',[])) for p in data.get('participants',[]))
 except (requests.RequestException,ValueError,TypeError):return False

def credit_activity(conn,member_id):
 instant=now_utc()
 conn.execute("INSERT INTO live_launch(id,started_at) VALUES('live',?) ON CONFLICT(id) DO NOTHING",(stamp(instant),))
 current=conn.execute('SELECT * FROM founder_activity WHERE member_id=?',(member_id,)).fetchone()
 if not current:
  launch=conn.execute("SELECT started_at FROM live_launch WHERE id='live'").fetchone()
  conn.execute('INSERT INTO founder_activity(member_id,total_seconds,session_seconds,last_verified_at,qualification_until) VALUES(?,0,0,?,?)',(member_id,stamp(instant),stamp(months_after(datetime.fromisoformat(launch['started_at'])))))
  return
 gap=(instant-datetime.fromisoformat(current['last_verified_at'])).total_seconds() if current['last_verified_at'] else 0
 seconds=int(gap) if 0<gap<=75 else 0;session_seconds=(current['session_seconds']+seconds) if seconds else 0
 completed=current['first_completed_at'] or (stamp(instant) if session_seconds>=INITIAL_MINUTES*60 else None)
 conn.execute('UPDATE founder_activity SET total_seconds=total_seconds+?,session_seconds=?,last_verified_at=?,first_completed_at=? WHERE member_id=?',(seconds,session_seconds,stamp(instant),completed,member_id))
 if seconds:conn.execute('INSERT INTO creator_daily_activity(member_id,day,seconds) VALUES(?,?,?) ON CONFLICT(member_id,day) DO UPDATE SET seconds=creator_daily_activity.seconds+excluded.seconds',(member_id,instant.date().isoformat(),seconds))

def install(app):app.register_blueprint(bp)


def video_service_available():
 """A configured URL alone must not consume a free trial."""
 import requests
 from urllib.parse import urlparse
 from streamers import sign_token
 instant=int(time.time())
 try:
  token=sign_token({'iss':os.environ['LIVEKIT_API_KEY'].strip(),'iat':instant,'nbf':instant-5,'exp':instant+45,'video':{'roomList':True}})
  with requests.post('https://'+urlparse(os.environ['LIVEKIT_URL']).netloc+'/twirp/livekit.RoomService/ListRooms',json={},headers={'Authorization':'Bearer '+token},timeout=(2,4),allow_redirects=False) as response:
   if response.status_code!=200:return False
   data=response.json();return isinstance(data,dict) and isinstance(data.get('rooms',[]),list)
 except (KeyError,requests.RequestException,ValueError,TypeError):return False
