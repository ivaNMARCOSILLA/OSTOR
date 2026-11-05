"""Permanent personal founder numbers; annual service access remains separate."""
from datetime import datetime,timedelta
import membership as membership
from membership import stamp

def now_utc():return membership.now_utc()
LIMIT=100
PAYMENT_NOTICE_DAYS=7


def init_database():
 """Freeze existing assignments once; historical released numbers stay history."""
 with membership.database() as conn:
  # No member foreign key: removing an account must not free its number for a
  # different person. Only an opaque identifier and assignment state survive.
  conn.executescript('''CREATE TABLE IF NOT EXISTS founder_ownership (
   member_id TEXT PRIMARY KEY NOT NULL,number INTEGER NOT NULL UNIQUE CHECK(number>=1 AND number<=100),
   assigned_at TEXT NOT NULL,revoked_at TEXT
  );''')
  conn.execute('BEGIN IMMEDIATE')
  seed_ownership(conn)


def seed_ownership(conn):
 """Caller holds the serialized account/payment transaction."""
 conn.execute('''INSERT INTO founder_ownership(member_id,number,assigned_at,revoked_at)
  SELECT member_id,number,claimed_at,revoked_at FROM live_founders WHERE 1=1
  ON CONFLICT(member_id) DO NOTHING''')
 inconsistent=conn.execute('''SELECT f.member_id FROM live_founders f
  JOIN founder_ownership o ON o.member_id=f.member_id WHERE f.number<>o.number LIMIT 1''').fetchone()
 if inconsistent:raise ValueError('Una insignia de fundador no coincide con su propietario permanente.')
 # Preserve revocations if a legacy operation later removes the display row.
 conn.execute('''UPDATE founder_ownership SET revoked_at=(SELECT f.revoked_at FROM live_founders f WHERE f.member_id=founder_ownership.member_id)
  WHERE EXISTS(SELECT 1 FROM live_founders f WHERE f.member_id=founder_ownership.member_id AND f.revoked_at IS NOT NULL AND (founder_ownership.revoked_at IS NULL OR founder_ownership.revoked_at<>f.revoked_at))''')
 # A missing display row may be rebuilt only for the same still-existing
 # account. Deleted accounts retain their opaque ownership tombstone alone.
 conn.execute('''INSERT INTO live_founders(member_id,number,claimed_at,revoked_at)
  SELECT o.member_id,o.number,o.assigned_at,o.revoked_at FROM founder_ownership o
  JOIN members m ON m.id=o.member_id
  WHERE NOT EXISTS(SELECT 1 FROM live_founders f WHERE f.member_id=o.member_id)
  ON CONFLICT(member_id) DO NOTHING''')


def ownership(conn,member_id):
 row=conn.execute('SELECT member_id,number,assigned_at,revoked_at FROM founder_ownership WHERE member_id=?',(member_id,)).fetchone()
 return dict(row) if row else None


def deadline(conn,row,launch=None,known_launch=False):
 member=conn.execute('SELECT access_until FROM members WHERE id=?',(row['member_id'],)).fetchone()
 if row['paid_at'] and member and member['access_until']:return member['access_until']
 if row['trial_until']:return row['trial_until']
 if not known_launch:launch=conn.execute("SELECT started_at FROM live_launch WHERE id='live'").fetchone()
 if not launch:return None
 from live_access import trial_end
 return stamp(trial_end(max(datetime.fromisoformat(launch['started_at']),datetime.fromisoformat(row['claimed_at']))))


def release_expired(conn):
 """Compatibility entry point: expiry never releases a personal identity."""
 seed_ownership(conn)
 return 0


def cleanup():
 with membership.database() as conn:
  conn.execute('BEGIN IMMEDIATE');return release_expired(conn)


def reserve(conn,member_id):
 seed_ownership(conn)
 existing=ownership(conn,member_id)
 if existing:return existing['number']
 used={row['number'] for row in conn.execute('SELECT number FROM founder_ownership').fetchall()}
 number=next((n for n in range(1,LIMIT+1) if n not in used),None)
 if number is None:return None
 at=stamp(now_utc())
 conn.execute('INSERT INTO founder_ownership(member_id,number,assigned_at) VALUES(?,?,?)',(member_id,number,at))
 conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(member_id,number,at))
 return number


def reservation(conn,member_id):
 row=conn.execute('SELECT f.*,e.trial_started_at,e.trial_until,e.paid_at FROM live_founders f LEFT JOIN live_entitlements e ON e.member_id=f.member_id WHERE f.member_id=?',(member_id,)).fetchone()
 if not row:return None
 until=deadline(conn,row)
 owner=ownership(conn,member_id)
 return dict(payment_due_at=until,payment_confirmation_days=PAYMENT_NOTICE_DAYS,number=row['number'],trial_until=until,confirmed=bool(row['paid_at'] and until and until>stamp(now_utc())),payment_required=not bool(row['paid_at']),payment_opens_at=payment_opening(row,until) if until else None,ownership_permanent=bool(owner),exclusive=bool(owner),assigned_at=owner['assigned_at'] if owner else row['claimed_at'])


def payment_opening(row,until):
 start=row['trial_started_at'] if 'trial_started_at' in row.keys() else row['claimed_at']
 end=datetime.fromisoformat(until)
 if start and end-datetime.fromisoformat(start)>timedelta(days=7):end-=timedelta(days=PAYMENT_NOTICE_DAYS)
 return stamp(end)


def payment_allowed(entitlement,slot):
 until=entitlement.get('trial_until') or (slot or {}).get('trial_until')
 if not until:return False
 opens=datetime.fromisoformat(until)
 if slot:opens=datetime.fromisoformat(slot['payment_opens_at'])
 return now_utc()>=opens
