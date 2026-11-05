"""Personal founder numbers remain exclusive across expiry, renewal and account removal."""
import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import app,membership as m,streamers
from auth_support import authenticated_client

class FounderSlotsTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():streamers.init_database()
  code=patch('human_check.new_code',return_value='OL234');code.start();self.addCleanup(code.stop)
 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  token=client.get('/api/account/me').json['csrf']
  if path=='/api/live/founders/claim':data=dict(data,human_id=client.get('/api/account/human-check').json['id'],human_answer='OL234')
  return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def member(self,name,paid=True):
  c=app.app.test_client();self.assertEqual(self.post(c,'/api/account/register',{'username':name,'password':'annual-founder-password-123'}).status_code,201)
  ident=c.get('/api/account/me').json['user']['id']
  if paid:
   with app.app.app_context(),m.database() as db:
    db.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),ident))
    db.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)',(ident,m.stamp(m.now_utc())))
  return c
 def test_unpaid_member_cannot_claim_or_start_a_trial(self):
  c=self.member('unpaid-holder',False);self.assertEqual(self.post(c,'/api/live/founders/claim',{}).status_code,409);self.assertEqual(self.post(c,'/api/account/live-trial',{}).status_code,410)
  self.assertEqual(c.get('/api/live/founders').json['remaining'],100)
 def test_annual_expiry_keeps_exclusive_number_without_free_service(self):
  c=self.member('expired-holder');self.assertEqual(self.post(c,'/api/live/founders/claim',{}).json['number'],1)
  ident=c.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as db:db.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),ident))
  status=c.get('/api/live/founders').json
  self.assertEqual(status['remaining'],99);self.assertEqual(status['mine']['number'],1)
  self.assertTrue(status['ownership_permanent']);self.assertTrue(status['mine']['ownership']['exclusive'])
  account=c.get('/api/account/me').json['user']
  self.assertFalse(account['active']);self.assertFalse(account['streamer_active']);self.assertFalse(account['founder_active'])
  self.assertEqual(account['founder_number'],1)
  self.assertEqual(self.admin.get('/api/admin/founders/history').json['total'],0)
  next_user=self.member('next-holder');self.assertEqual(self.post(next_user,'/api/live/founders/claim',{}).json['number'],2)
  with app.app.app_context(),m.database() as db:db.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),ident))
  self.assertTrue(c.get('/api/account/me').json['user']['founder_active'])
  self.assertEqual(c.get('/api/live/founders').json['mine']['number'],1)
 def test_cancelling_renewal_keeps_number_and_paid_access(self):
  c=self.member('cancel-holder');self.post(c,'/api/live/founders/claim',{})
  self.assertEqual(self.post(c,'/api/account/annual/cancel',{}).status_code,200)
  self.assertEqual(c.get('/api/live/founders').json['mine']['number'],1)
  self.assertTrue(c.get('/api/account/me').json['user']['live_annual'])
 def test_last_number_is_assigned_once_under_concurrent_requests(self):
  with app.app.app_context(),m.database() as db:
   for number in range(2,101):
    ident='occupied-'+str(number);db.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(m.now_utc())))
    db.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(m.now_utc())))
  clients=[self.member('simultaneous-a'),self.member('simultaneous-b')]
  with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda c:self.post(c,'/api/live/founders/claim',{}),clients))
  self.assertEqual(sorted(r.status_code for r in responses),[200,409]);self.assertEqual(next(r.json['number'] for r in responses if r.status_code==200),1)

 def test_expired_owner_can_personalize_without_getting_live_access(self):
  c=self.member('personal-owner');self.post(c,'/api/live/founders/claim',{})
  ident=c.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as db:db.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.now_utc()-timedelta(days=1)),ident))
  result=self.post(c,'/api/live/founders/signature',{'mode':'letra','letter':'F','caption':'Mi insignia personal'})
  self.assertEqual(result.status_code,200);self.assertEqual(result.json['number'],1)
  self.assertEqual(c.get('/api/live/founders').json['mine']['signature']['letter'],'F')
  self.assertEqual(self.post(c,'/api/streamers/me',{'title':'No free broadcasting'}).status_code,402)
  self.assertFalse(c.get('/api/account/me').json['user']['streamer_active'])
  self.assertEqual(c.get('/api/live/founders/audio-search?q=').status_code,200)

 def test_other_member_and_revoked_owner_cannot_edit_the_badge(self):
  owner=self.member('protected-owner');self.post(owner,'/api/live/founders/claim',{})
  ident=owner.get('/api/account/me').json['user']['id']
  stranger=self.member('stranger-owner',False)
  self.assertEqual(self.post(stranger,'/api/live/founders/signature',{'mode':'numero','member_id':ident}).status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/founders/revoke',{'member_id':ident}).status_code,200)
  with app.app.app_context(),m.database() as db:
   self.assertIsNotNone(db.execute('SELECT revoked_at FROM founder_ownership WHERE member_id=?',(ident,)).fetchone()['revoked_at'])
   db.execute('DELETE FROM live_founders WHERE member_id=?',(ident,))
  # Rebuilding a display row must also restore its revocation, never its rights.
  self.assertEqual(app.app.test_client().get('/api/live/founders').json['remaining'],99)
  with app.app.app_context(),m.database() as db:self.assertIsNotNone(db.execute('SELECT revoked_at FROM live_founders WHERE member_id=?',(ident,)).fetchone()['revoked_at'])
  newcomer=self.member('new-protected-owner');self.assertEqual(self.post(newcomer,'/api/live/founders/claim',{}).json['number'],2)

 def test_upgrade_seeds_current_holders_once_and_keeps_opaque_identity(self):
  import founder_slots
  c=self.member('legacy-owner');ident=c.get('/api/account/me').json['user']['id']
  assigned=m.stamp(m.now_utc()-timedelta(days=5))
  with app.app.app_context(),m.database() as db:db.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,7,?)',(ident,assigned))
  with app.app.app_context():founder_slots.init_database();founder_slots.init_database()
  with app.app.app_context(),m.database() as db:
   row=dict(db.execute('SELECT * FROM founder_ownership WHERE member_id=?',(ident,)).fetchone())
   self.assertEqual(row,{'member_id':ident,'number':7,'assigned_at':assigned,'revoked_at':None})
   self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM founder_ownership').fetchone()['n'],1)
   db.execute('UPDATE members SET username=? WHERE id=?',('renamed-legacy-owner',ident))
  status=c.get('/api/live/founders').json
  self.assertEqual(status['mine']['ownership']['number'],7);self.assertEqual(status['mine']['ownership']['assigned_at'],assigned)
  self.assertEqual(c.get('/api/account/me').json['user']['username'],'renamed-legacy-owner')

 def test_missing_display_row_is_restored_only_to_the_same_account(self):
  c=self.member('restored-owner');self.post(c,'/api/live/founders/claim',{})
  ident=c.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as db:db.execute('DELETE FROM live_founders WHERE member_id=?',(ident,))
  self.assertEqual(c.get('/api/account/me').json['user']['founder_number'],1)
  self.assertEqual(c.get('/api/live/founders').json['claimed'],1)

 def test_deleting_a_free_owner_retains_number_as_an_opaque_tombstone(self):
  c=self.member('removed-founder',False);ident=c.get('/api/account/me').json['user']['id']
  self.assertEqual(self.post(self.admin,'/api/admin/full-service-access',{'member_id':ident,'active':True}).status_code,200)
  self.assertEqual(self.post(c,'/api/live/founders/claim',{}).json['number'],1)
  result=self.post(self.admin,'/api/admin/members/delete',{'member_id':ident})
  self.assertEqual(result.status_code,200,result.json)
  with app.app.app_context(),m.database() as db:
   self.assertIsNone(db.execute('SELECT id FROM members WHERE id=?',(ident,)).fetchone())
   self.assertIsNone(db.execute('SELECT member_id FROM live_founders WHERE member_id=?',(ident,)).fetchone())
   self.assertEqual(db.execute('SELECT number FROM founder_ownership WHERE member_id=?',(ident,)).fetchone()['number'],1)
  public=app.app.test_client().get('/api/live/founders').json
  self.assertEqual(public['claimed'],1);self.assertEqual(public['remaining'],99)
  self.assertNotIn(ident,str(public))
  newcomer=self.member('removed-founder')
  self.assertNotEqual(newcomer.get('/api/account/me').json['user']['id'],ident)
  self.assertEqual(self.post(newcomer,'/api/live/founders/claim',{}).json['number'],2)

 def test_historical_released_numbers_are_not_reassigned_retroactively(self):
  import founder_slots
  legacy=self.member('historical-account',False);ident=legacy.get('/api/account/me').json['user']['id'];at=m.stamp(m.now_utc()-timedelta(days=3))
  with app.app.app_context(),m.database() as db:
   db.execute('INSERT INTO founder_slot_history(id,member_id,number,claimed_at,trial_until,released_at,reason) VALUES(?,?,1,?,?,?,?)',('old-history',ident,at,at,at,'annual_expired'))
  with app.app.app_context():founder_slots.init_database()
  self.assertEqual(legacy.get('/api/live/founders').json['remaining'],100)
  self.assertIsNone(legacy.get('/api/live/founders').json['mine'])
  newcomer=self.member('current-owner');self.assertEqual(self.post(newcomer,'/api/live/founders/claim',{}).json['number'],1)

 def test_one_hundred_deleted_assignments_still_fill_founder_capacity(self):
  at=m.stamp(m.now_utc())
  with app.app.app_context(),m.database() as db:
   for number in range(1,101):db.execute('INSERT INTO founder_ownership(member_id,number,assigned_at) VALUES(?,?,?)',('deleted-owner-'+str(number),number,at))
  c=self.member('ordinary-after-founders')
  self.assertEqual(self.post(c,'/api/live/founders/claim',{}).status_code,409)
  public=c.get('/api/live/founders').json;self.assertEqual(public['claimed'],100);self.assertEqual(public['remaining'],0);self.assertIsNone(public['mine'])
  self.assertTrue(c.get('/api/account/me').json['user']['streamer_active'])
