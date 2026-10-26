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
  token=client.get('/api/account/me').json['csrf']
  return client.post(path,json=data or {},headers={'X-CSRF-Token':token})
 def test_guests_members_deduplication_expiry_and_private_statistics(self):
  guest=app.app.test_client()
  self.assertEqual(guest.get('/api/admin/statistics').status_code,403)
  first=self.post(guest,'/api/presence');self.assertEqual(first.status_code,200)
  self.assertEqual(first.json,dict(total=1,members=0,guests=1,window_seconds=90))
  self.assertEqual(self.post(guest,'/api/presence').json['total'],1)
  self.assertEqual(self.post(guest,'/api/account/register',{'username':'presence-user','password':'presence-user-password-123'}).status_code,201)
  result=self.post(guest,'/api/presence').json;self.assertEqual((result['total'],result['members'],result['guests']),(1,1,0))
  other=app.app.test_client();self.post(other,'/api/account/login',{'username':'presence-user','password':'presence-user-password-123'})
  self.assertEqual(self.post(other,'/api/presence').json['total'],1)
  visitor=app.app.test_client();self.assertEqual(self.post(visitor,'/api/presence').json['total'],2)
  summary=self.admin.get('/api/admin/statistics');self.assertEqual(summary.status_code,200)
  self.assertEqual(summary.json['accounts']['registered'],1);self.assertEqual(summary.json['accounts']['new_week'],1)
  self.assertEqual(summary.json['payments']['total_cents'],0);self.assertEqual(len(summary.json['days']),7)
  self.assertNotIn('presence-user',summary.get_data(as_text=True))
  with patch.object(analytics,'now_utc',return_value=m.now_utc()+timedelta(seconds=91)):
   expired=self.post(visitor,'/api/presence').json;self.assertEqual((expired['members'],expired['guests']),(0,1))
   self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['total'],1)
  with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM online_presence').fetchone()['n'],1)
 def test_presence_requires_csrf_and_does_not_accept_an_unsigned_identity(self):
  guest=app.app.test_client();self.assertEqual(guest.post('/api/presence').status_code,403)
  guest.set_cookie('ol_presence','forged-cookie')
  response=self.post(guest,'/api/presence');self.assertEqual(response.status_code,200)
  self.assertIn('HttpOnly',response.headers['Set-Cookie'])
  self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['guests'],1)
