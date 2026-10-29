"""Ol Livis: one seven-day trial, one fixed price, verified creator activity."""
import calendar,os,time
from datetime import datetime,timedelta
from flask import Blueprint,jsonify
from membership import database,get_user,now_utc,stamp,payload
bp=Blueprint('live_access',__name__)
PRICE_CENTS=2500
TRIAL_DAYS=7

def trial_end(instant):return instant+timedelta(days=TRIAL_DAYS)
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
 founder=conn.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(member_id,)).fetchone()
 exempt=bool(founder and founder['number']==1 and not founder['revoked_at'])
 payment_current=not slot or slot['confirmed'] or not slot['trial_until'] or slot['trial_until']>stamp(now_utc())
 return dict(payment_current=payment_current,activity_exempt=exempt,initial_minutes=0 if exempt else INITIAL_MINUTES,monthly_minutes=0 if exempt else MONTHLY_MINUTES,verified_seconds=row.get('total_seconds',0),recent_seconds=recent,qualification_until=deadline,first_completed_at=row.get('first_completed_at'),qualified=qualified,eligible=payment_current and (exempt or grace or (qualified and recent>=MONTHLY_MINUTES*60)),provisional=not qualified and not exempt)

@bp.post('/api/account/live-trial')
def trial():
 return jsonify(error='Ol Livis cuesta 25 € al año desde la contratación. No se ofrecen pruebas gratuitas.',code='trial_retired'),410

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
   participants=data.get('participants',[])
   if not isinstance(participants,list):return False
   publishing=any(str(p.get('identity','')).startswith('maggy-'+user['id']+'-') and any(t.get('source') in (1,3,'CAMERA','SCREEN_SHARE') and not t.get('muted',False) for t in p.get('tracks',[])) for p in participants)
   if publishing:
    from subscriptions import enforce_room_subscribers
    return enforce_room_subscribers(channel,participants,'https://'+urlparse(os.environ['LIVEKIT_URL']).netloc,{'Authorization':'Bearer '+token})
   return False
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
