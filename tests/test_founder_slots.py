import unittest
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import app
import membership as m
import founders
import live_access
import streamers
from auth_support import authenticated_client

class FounderSlotsTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():streamers.init_database()
  for target in ['streamers.live_ready','streamers.streamer_sales_ready','live_access.video_service_available']:
   p=patch(target,return_value=True);p.start();self.addCleanup(p.stop)
  p=patch('human_check.new_code',return_value='OL234');p.start();self.addCleanup(p.stop)
  self.initial=datetime(2027,1,31,12,tzinfo=timezone.utc)
 @contextmanager
 def clock(self,instant):
  with patch.object(m,'now_utc',return_value=instant),patch.object(live_access,'now_utc',return_value=instant),patch.object(founders,'now_utc',return_value=instant):yield
 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  csrf=client.get('/api/account/me').json['csrf']
  if path in ['/api/account/live-trial','/api/live/founders/claim']:
   data=dict(data,human_id=client.get('/api/account/human-check').json['id'],human_answer='OL234')
  return client.post(path,json=data,headers={'X-CSRF-Token':csrf})
 def member(self,name):
  client=app.app.test_client();self.assertEqual(self.post(client,'/api/account/register',{'username':name,'password':'temporary-slot-password-123'}).status_code,201);return client
 def pay(self,client,ref):
  ident=client.get('/api/account/me').json['user']['id']
  return self.post(self.admin,'/api/admin/confirm-payment',{'member_id':ident,'plan':'lifetime','reference':ref})
 def test_trial_reserves_slot_then_unpaid_expiry_recycles_number_without_resetting_trial(self):
  with self.clock(self.initial):
   first=self.member('first-holder');trial=self.post(first,'/api/account/live-trial',{})
   self.assertEqual(trial.status_code,200);self.assertEqual(trial.json['founder_number'],1);self.assertEqual(trial.json['trial_until'],'2027-02-07T12:00:00+00:00')
   self.assertEqual(first.get('/api/live/founders').json['remaining'],99)
   self.assertEqual(self.pay(first,'NO-EARLY-PAYMENT').status_code,409)
   self.assertEqual(self.post(first,'/api/live/founders/signature',{'mode':'letra','letter':'A','caption':'Mi estilo'}).status_code,200)
  expired=datetime(2027,4,30,12,tzinfo=timezone.utc)
  with self.clock(expired):
   self.assertEqual(first.get('/api/streamers').status_code,402)
   # Another visitor triggers expiry: the old holder need not return.
   public=app.app.test_client().get('/api/live/founders').json
   self.assertEqual(public['remaining'],100)
   self.assertFalse(first.get('/api/account/me').json['user']['active'])
   self.assertIsNone(first.get('/api/account/me').json['user']['founder_number'])
   self.assertEqual(self.post(first,'/api/account/live-trial',{}).json['trial_until'],trial.json['trial_until'])
   self.assertEqual(self.post(first,'/api/live/founders/claim',{}).status_code,409)
   second=self.member('second-holder');reserved=self.post(second,'/api/account/live-trial',{})
   self.assertEqual(reserved.status_code,200);self.assertEqual(reserved.json['founder_number'],1)
   mine=second.get('/api/live/founders').json['mine'];self.assertEqual(mine['signature']['letter'],'')
   history=self.admin.get('/api/admin/founders/history').json;self.assertEqual(history['total'],1);self.assertEqual(history['history'][0]['username'],'first-holder')
   self.assertEqual(second.get('/api/admin/founders/history').status_code,403)
   self.assertEqual(self.pay(first,'LATE-PAYMENT-001').status_code,200)
   self.assertTrue(first.get('/api/account/me').json['user']['live_lifetime'])
   self.assertIsNone(first.get('/api/account/me').json['user']['founder_number'])
   self.assertEqual(second.get('/api/account/me').json['user']['founder_number'],1)
 def test_prelaunch_reservation_gets_one_fixed_trial_when_video_launches(self):
  with self.clock(self.initial):
   client=self.member('pending-holder')
   self.assertEqual(self.post(client,'/api/live/founders/claim',{}).status_code,200)
   self.assertIsNone(client.get('/api/account/me').json['user']['live_trial_until'])
  launched=self.initial+timedelta(days=10)
  with app.app.app_context(),m.database() as conn:
   conn.execute("INSERT INTO live_launch(id,started_at) VALUES('live',?)",(m.stamp(launched),))
  expected=m.stamp(live_access.trial_end(launched))
  with self.clock(self.initial+timedelta(days=12)):
   me=client.get('/api/account/me').json
   self.assertEqual(me['user']['live_trial_until'],expected)
   started=self.post(client,'/api/account/live-trial',{})
   self.assertTrue(started.json['already_started'])
   self.assertEqual(started.json['trial_until'],expected)
   self.assertEqual(started.json['founder_number'],1)

 def test_confirmed_payment_in_final_week_keeps_number_after_trial(self):
  with self.clock(self.initial):
   client=self.member('paid-holder');self.post(client,'/api/account/live-trial',{})
   ident=client.get('/api/account/me').json['user']['id']
   with app.app.app_context(),m.database() as conn:conn.execute('UPDATE live_entitlements SET trial_until=? WHERE member_id=?',('2027-04-30T12:00:00+00:00',ident))
  with self.clock(datetime(2027,4,24,12,tzinfo=timezone.utc)):
   self.assertEqual(self.pay(client,'FINAL-WEEK-001').status_code,200)
   self.assertTrue(client.get('/api/account/me').json['founder_reservation']['confirmed'])
  with self.clock(datetime(2027,6,1,12,tzinfo=timezone.utc)):
   public=app.app.test_client().get('/api/live/founders').json
   self.assertEqual(public['remaining'],99)
   self.assertEqual(client.get('/api/account/me').json['user']['founder_number'],1)
   self.assertEqual(self.admin.get('/api/admin/founders/history').json['total'],0)
 def test_last_freed_number_cannot_be_given_to_two_simultaneous_trials(self):
  with self.clock(self.initial):
   with app.app.app_context(),m.database() as conn:
    for number in range(2,101):
     ident='occupied-'+str(number);conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(self.initial)))
     conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(self.initial)))
     conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)',(ident,m.stamp(self.initial)))
   clients=[self.member('simultaneous-a'),self.member('simultaneous-b')]
   with ThreadPoolExecutor(max_workers=2) as pool:
    results=[pool.submit(self.post,c,'/api/account/live-trial',{}) for c in clients];results=[f.result() for f in results]
   self.assertEqual(sorted(r.status_code for r in results),[200,409])
   self.assertEqual(next(r.json['founder_number'] for r in results if r.status_code==200),1)
   loser=clients[0] if results[0].status_code!=200 else clients[1]
   self.assertIsNone(loser.get('/api/account/me').json['user']['live_trial_until'])
   self.assertEqual(app.app.test_client().get('/api/live/founders').json['claimed'],100)
