"""Recyclable numbered trial reservations, with private release history."""
import json,secrets
from datetime import datetime,timedelta
import membership as membership
from membership import stamp
def now_utc():return membership.now_utc()
LIMIT=100
PAYMENT_NOTICE_DAYS=7

def deadline(conn,row,launch=None,known_launch=False):
 if row['trial_until']:return row['trial_until']
 if not known_launch:launch=conn.execute("SELECT started_at FROM live_launch WHERE id='live'").fetchone()
 if not launch:return None
 from live_access import months_after
 return stamp(months_after(max(datetime.fromisoformat(launch['started_at']),datetime.fromisoformat(row['claimed_at']))))

def release_expired(conn):
 """Caller holds BEGIN IMMEDIATE; payments and reallocation share the lock."""
 rows=conn.execute('SELECT f.*,e.trial_until,e.paid_at FROM live_founders f LEFT JOIN live_entitlements e ON e.member_id=f.member_id').fetchall()
 instant=stamp(now_utc());released=0
 launch=conn.execute("SELECT started_at FROM live_launch WHERE id='live'").fetchone()
 for row in rows:
  until=deadline(conn,row,launch=launch,known_launch=True)
  if until and not row['trial_until'] and not row['paid_at']:
   start=max(datetime.fromisoformat(launch['started_at']),datetime.fromisoformat(row['claimed_at']))
   conn.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET trial_started_at=COALESCE(live_entitlements.trial_started_at,excluded.trial_started_at),trial_until=COALESCE(live_entitlements.trial_until,excluded.trial_until)',(row['member_id'],stamp(start),until))
  if row['paid_at'] or not until or until>instant:continue
  signature=conn.execute('SELECT mode,letter,caption,audio_json FROM founder_signatures WHERE member_id=?',(row['member_id'],)).fetchone()
  conn.execute('INSERT INTO founder_slot_history(id,member_id,number,claimed_at,trial_until,released_at,reason,signature_json) VALUES(?,?,?,?,?,?,?,?)',(secrets.token_hex(16),row['member_id'],row['number'],row['claimed_at'],until,instant,'trial_unpaid',json.dumps(dict(signature),ensure_ascii=False) if signature else None))
  # Retain the used trial even for reservations made before trial activation.
  conn.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until) VALUES(?,?,?) ON CONFLICT(member_id) DO UPDATE SET trial_until=COALESCE(live_entitlements.trial_until,excluded.trial_until)',(row['member_id'],row['claimed_at'],until))
  conn.execute('DELETE FROM live_founders WHERE member_id=?',(row['member_id'],))
  # A new reservation must qualify on its own; old activity remains in daily history.
  conn.execute('DELETE FROM founder_activity WHERE member_id=?',(row['member_id'],))
  released+=1
 return released

def cleanup():
 from membership import database
 with database() as conn:
  conn.execute('BEGIN IMMEDIATE');return release_expired(conn)

def reserve(conn,member_id):
 existing=conn.execute('SELECT number,revoked_at FROM live_founders WHERE member_id=?',(member_id,)).fetchone()
 if existing:return existing['number']
 used={row['number'] for row in conn.execute('SELECT number FROM live_founders').fetchall()}
 number=next((n for n in range(1,LIMIT+1) if n not in used),None)
 if number is None:return None
 conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(member_id,number,stamp(now_utc())))
 return number

def reservation(conn,member_id):
 row=conn.execute('SELECT f.*,e.trial_until,e.paid_at FROM live_founders f LEFT JOIN live_entitlements e ON e.member_id=f.member_id WHERE f.member_id=?',(member_id,)).fetchone()
 if not row:return None
 until=deadline(conn,row)
 return dict(payment_due_at=until,payment_confirmation_days=PAYMENT_NOTICE_DAYS,number=row['number'],trial_until=until,confirmed=bool(row['paid_at']),payment_required=not bool(row['paid_at']),payment_opens_at=stamp(datetime.fromisoformat(until)-timedelta(days=PAYMENT_NOTICE_DAYS)) if until else None)

def payment_allowed(entitlement,slot):
 until=entitlement.get('trial_until') or (slot or {}).get('trial_until')
 if not until:return False
 opens=datetime.fromisoformat(until)
 if slot:opens-=timedelta(days=PAYMENT_NOTICE_DAYS)
 return now_utc()>=opens
