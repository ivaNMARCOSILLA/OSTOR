"""Annual paid founder places are atomic and are released on expiry, with history retained."""
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
 def test_annual_expiry_recycles_number_and_retains_history(self):
  c=self.member('expired-holder');self.assertEqual(self.post(c,'/api/live/founders/claim',{}).json['number'],1)
  ident=c.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as db:db.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),ident))
  self.assertEqual(app.app.test_client().get('/api/live/founders').json['remaining'],100)
  self.assertFalse(c.get('/api/account/me').json['user']['active'])
  history=self.admin.get('/api/admin/founders/history').json;self.assertEqual(history['total'],1);self.assertEqual(history['history'][0]['reason'],'annual_expired')
  next_user=self.member('next-holder');self.assertEqual(self.post(next_user,'/api/live/founders/claim',{}).json['number'],1)
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
