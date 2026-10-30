import unittest
from datetime import timedelta
from unittest.mock import patch
import app
import membership as m
import analytics
from auth_support import authenticated_client

class AnalyticsTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():
   import streamers
   streamers.init_database()
 def post(self,client,path,data=None):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  token=client.get('/api/account/me').json['csrf']
  return client.post(path,json=(data or {})|({'consent':True} if path=='/api/presence' else {}),headers={'X-CSRF-Token':token})
 def test_guests_members_deduplication_expiry_and_private_statistics(self):
  guest=app.app.test_client()
  self.assertEqual(guest.get('/api/admin/statistics').status_code,403)
  first=self.post(guest,'/api/presence');self.assertEqual(first.status_code,200)
  self.assertEqual(first.json,{'recorded':True});self.assertEqual(self.admin.get('/api/admin/statistics').json['online'],dict(total=1,members=0,guests=1,window_seconds=90))
  self.assertEqual((self.post(guest,'/api/presence'),self.admin.get('/api/admin/statistics').json['online']['total'])[1],1)
  self.assertEqual(self.post(guest,'/api/account/register',{'username':'presence-user','password':'presence-user-password-123'}).status_code,201)
  self.post(guest,'/api/presence');result=self.admin.get('/api/admin/statistics').json['online'];self.assertEqual((result['total'],result['members'],result['guests']),(1,1,0))
  other=app.app.test_client();self.post(other,'/api/account/login',{'username':'presence-user','password':'presence-user-password-123'})
  self.assertEqual((self.post(other,'/api/presence'),self.admin.get('/api/admin/statistics').json['online']['total'])[1],1)
  visitor=app.app.test_client();self.assertEqual((self.post(visitor,'/api/presence'),self.admin.get('/api/admin/statistics').json['online']['total'])[1],2)
  summary=self.admin.get('/api/admin/statistics');self.assertEqual(summary.status_code,200)
  self.assertEqual(summary.json['accounts']['registered'],1);self.assertEqual(summary.json['accounts']['new_week'],1)
  self.assertEqual(summary.json['payments']['total_cents'],0);self.assertEqual(len(summary.json['days']),7)
  self.assertNotIn('presence-user',summary.get_data(as_text=True))
  with patch.object(analytics,'now_utc',return_value=m.now_utc()+timedelta(seconds=91)):
   self.post(visitor,'/api/presence');expired=self.admin.get('/api/admin/statistics').json['online'];self.assertEqual((expired['members'],expired['guests']),(0,1))
   self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['total'],1)
  with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM online_presence').fetchone()['n'],1)
 def test_presence_requires_csrf_and_does_not_accept_an_unsigned_identity(self):
  guest=app.app.test_client();self.assertEqual(guest.post('/api/presence').status_code,403)
  guest.set_cookie('ol_presence','forged-cookie')
  response=self.post(guest,'/api/presence');self.assertEqual(response.status_code,200)
  self.assertIn('HttpOnly',response.headers['Set-Cookie'])
  self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['guests'],1)

 def test_unaccepted_invitations_do_not_inflate_customer_statistics(self):
  result=self.post(self.admin,'/api/admin/invite',{'username':'not-accepted-stats'})
  self.assertEqual(result.status_code,201)
  data=self.admin.get('/api/admin/statistics').json
  self.assertEqual(data['accounts']['registered'],0)
  self.assertEqual(data['friends'],0)
  friend=app.app.test_client();token=result.json['path'].split('=',1)[1]
  self.assertEqual(self.post(friend,'/api/account/accept-invite',{'token':token,'password':'accepted-stats-password-123'}).status_code,200)
  activated=self.admin.get('/api/admin/statistics').json
  self.assertEqual(activated['accounts']['registered'],1);self.assertEqual(activated['friends'],1)

 def test_presence_without_optional_consent_is_not_recorded(self):
  guest=app.app.test_client();token=guest.get('/api/account/me').json['csrf']
  response=guest.post('/api/presence',json={},headers={'X-CSRF-Token':token})
  self.assertFalse(response.json['recorded']);self.assertIsNone(guest.get_cookie('ol_presence'))
  self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['total'],0)
  self.post(guest,'/api/presence')
  result=guest.post('/api/presence',json={'consent':True},headers={'X-CSRF-Token':token,'Sec-GPC':'1'})
  self.assertFalse(result.json['recorded']);self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['total'],0)
