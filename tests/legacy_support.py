"""Fixtures for periods bought before 9.4; retired plans cannot be purchased now."""
from types import SimpleNamespace
import secrets
from datetime import datetime,timedelta
import membership as m
from storage import INTEGRITY_ERRORS

def legacy_payment(app,admin,member_id,plan,reference):
 with app.app_context():
  try:
   with m.database() as conn:
    user=conn.execute('SELECT * FROM members WHERE id=?',(member_id,)).fetchone()
    if plan=='welcome' and user['welcome_used']:return SimpleNamespace(status_code=409,json={})
    prior=conn.execute('SELECT until_at FROM streamer_access WHERE member_id=?',(member_id,)).fetchone() if plan=='streamer' else None
    old=(prior['until_at'] if prior else None) if plan=='streamer' else user['access_until']
    start=max(m.now_utc(),datetime.fromisoformat(old)) if old else m.now_utc();end=m.end_of_plan(start,plan)
    verifier=conn.execute("SELECT id FROM members WHERE role='admin' LIMIT 1").fetchone()['id']
    conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),member_id,plan,{'welcome':100,'monthly':600,'streamer':800}[plan],m.stamp(start),m.stamp(end),m.stamp(m.now_utc()),verifier,reference))
    access=max(end,datetime.fromisoformat(user['access_until'])) if user['access_until'] else end
    conn.execute('UPDATE members SET access_until=?,welcome_used=1 WHERE id=?',(m.stamp(access),member_id))
    if plan=='streamer':conn.execute('INSERT INTO streamer_access(member_id,until_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET until_at=excluded.until_at',(member_id,m.stamp(end)))
   return SimpleNamespace(status_code=200,json={'access_until':m.stamp(access)})
  except INTEGRITY_ERRORS:return SimpleNamespace(status_code=409,json={})
