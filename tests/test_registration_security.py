import unittest
from unittest.mock import patch
import app,membership as m,streamers
from auth_support import authenticated_client

class RegistrationSecurityTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():streamers.init_database()
  self.client=app.app.test_client()
 def post(self,client,data,csrf=None):
  token=csrf or client.get('/api/account/me').json['csrf']
  return client.post('/api/account/register',json=data,headers={'X-CSRF-Token':token})
 def challenge(self,client):
  with patch('human_check.new_code',return_value='OL234'):return client.get('/api/account/human-check').json
 def data(self,name='signup-user',challenge=None,answer='OL234'):
  return {'username':name,'password':'a-long-test-password-123','human_id':(challenge or {}).get('id',''),'human_answer':answer,'role':'admin','access_until':'2099-01-01'}
 def test_human_check_required_and_wrong_answer_does_not_create_account(self):
  self.assertEqual(self.post(self.client,self.data()).json['code'],'human_required')
  challenge=self.challenge(self.client)
  self.assertEqual(self.post(self.client,self.data(challenge=challenge,answer='WRONG')).status_code,400)
  self.assertIsNone(self.client.get('/api/account/me').json['user'])
 def test_self_registration_is_immediate_but_cannot_grant_live_or_admin(self):
  challenge=self.challenge(self.client)
  with patch.dict('os.environ',{'OL_LIVE_PREMIERE':'1'}):
   self.assertEqual(self.post(self.client,self.data(challenge=challenge)).status_code,201)
   user=self.client.get('/api/account/me').json['user']
   self.assertEqual(user['role'],'member');self.assertFalse(user['active']);self.assertFalse(user['live_lifetime']);self.assertIsNone(user['founder_number'])
   self.assertEqual(self.client.get('/api/admin/members').status_code,403)
   self.assertEqual(self.client.get('/api/rewards').status_code,200)
 def test_check_is_session_bound_single_use_and_expires(self):
  challenge=self.challenge(self.client);other=app.app.test_client()
  self.assertEqual(self.post(other,self.data(challenge=challenge)).status_code,400)
  challenge=self.challenge(self.client)
  self.assertEqual(self.post(self.client,self.data(challenge=challenge)).status_code,201)
  self.assertEqual(self.post(self.client,self.data('another-signup',challenge)).status_code,400)
  challenge=self.challenge(self.client)
  with app.app.app_context(),m.database() as c:c.execute("UPDATE human_challenges SET expires_at='2000-01-01T00:00:00+00:00' WHERE id=?",(challenge['id'],))
  self.assertEqual(self.post(self.client,self.data('expired-signup',challenge)).status_code,400)
 def test_csrf_rejection_is_explicit_and_does_not_consume_challenge(self):
  challenge=self.challenge(self.client)
  result=self.post(self.client,self.data(challenge=challenge),csrf='wrong-token')
  self.assertEqual(result.status_code,403);self.assertEqual(result.json['code'],'csrf_expired')
  self.assertEqual(self.post(self.client,self.data(challenge=challenge)).status_code,201)
