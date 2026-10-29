"""Owner concessions apply only to existing accounts and never become admin rights or sales."""
import unittest
from unittest.mock import patch
import app,membership as m,subscriptions as sub
from auth_support import authenticated_client

class FullServiceTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
 def post(self,c,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(c,data)
  token=c.get('/api/account/me').json['csrf'];return c.post(path,json=data,headers={'X-CSRF-Token':token})
 def member(self,name):
  c=app.app.test_client();self.assertEqual(self.post(c,'/api/account/register',{'username':name,'password':'owner-grant-fixture-password-123'}).status_code,201);return c
 def migration(self):
  with app.app.app_context(),patch.dict('os.environ',{'VERCEL_ENV':'production'}):m.apply_owner_access_migration()
 def test_both_existing_accounts_get_services_without_payments_or_authority(self):
  clients=[self.member('prueba'),self.member('prueba2')];other=self.member('ordinary-user');self.migration()
  for c in clients:
   u=c.get('/api/account/me').json['user'];self.assertTrue(u['full_service']);self.assertTrue(u['complimentary']);self.assertTrue(u['streamer_active']);self.assertEqual(u['role'],'member');self.assertFalse(u['live_annual']);self.assertFalse(u['live_lifetime'])
   self.assertEqual(c.get('/api/admin/members').status_code,403)
   with app.app.app_context(),m.database() as db:self.assertEqual(sub.active_benefits(db,'no-channel',u['id']),set(sub.BENEFITS));self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM payments').fetchone()['n'],0)
  self.assertFalse(other.get('/api/account/me').json['user']['full_service'])
 def test_admin_revocation_is_not_reversed_by_restart(self):
  c=self.member('prueba');self.member('prueba2');self.migration();u=c.get('/api/account/me').json['user']
  self.assertEqual(self.post(c,'/api/admin/full-service-access',{'member_id':u['id'],'active':True}).status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/full-service-access',{'member_id':u['id'],'active':False}).status_code,200)
  self.migration()
  self.post(c,'/api/account/login',{'username':'prueba','password':'owner-grant-fixture-password-123'})
  u=c.get('/api/account/me').json['user'];self.assertFalse(u['full_service']);self.assertFalse(u['active']);self.assertFalse(u['streamer_active'])
 def test_missing_account_is_not_granted_on_a_future_registration(self):
  self.migration();later=self.member('prueba2');self.migration();self.assertFalse(later.get('/api/account/me').json['user']['full_service'])
 def test_no_checkout_is_created_for_free_full_service(self):
  import payments
  c=self.member('prueba');self.migration()
  with patch.object(payments,'ready',return_value=True),patch.object(payments,'provider',return_value='stripe'),patch.object(payments,'stripe') as stripe:
   response=self.post(c,'/api/payments/checkout',{'annual_terms':True});self.assertEqual(response.status_code,409);stripe.assert_not_called()
