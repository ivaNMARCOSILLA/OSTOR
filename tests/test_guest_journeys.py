"""Guest navigation requires consent and CSRF; identity, queries and account activity are excluded."""
import unittest
from unittest.mock import patch
from datetime import timedelta
import app,membership as m,analytics
from auth_support import authenticated_client

class GuestJourneyTests(unittest.TestCase):
 def setUp(self):self.admin=authenticated_client(app.app,self.addCleanup);self.guest=app.app.test_client()
 def post(self,c,path,data):
  token=c.get('/api/account/me').json['csrf'];return c.post(path,json=data,headers={'X-CSRF-Token':token})
 def event(self,**overrides):return {'consent':True,'events':[{'kind':'click','page':'/','target':'buscar-musica'}]}|overrides
 def test_consent_csrf_and_admin_only_ordered_sequence(self):
  self.assertEqual(self.guest.post('/api/navigation/events',json=self.event()).status_code,403)
  self.assertFalse(self.post(self.guest,'/api/navigation/events',self.event(consent=False)).json['recorded'])
  data=self.event(events=[{'kind':'page','page':'/','target':''},{'kind':'click','page':'/','target':'buscar-musica'}]);response=self.post(self.guest,'/api/navigation/events',data)
  self.assertTrue(response.json['recorded']);self.assertIn('HttpOnly',response.headers['Set-Cookie'])
  self.assertEqual(self.guest.get('/api/admin/guest-journeys').status_code,403)
  visits=self.admin.get('/api/admin/guest-journeys').json;self.assertEqual(visits['total'],1);ident=visits['visits'][0]['id']
  self.post(self.guest,'/api/navigation/events',self.event())
  detail=self.admin.get('/api/admin/guest-journeys?visit='+ident);self.assertEqual([x['sequence'] for x in detail.json['events']],[1,2,3]);self.assertIn('no-store',detail.headers['Cache-Control'])
 def test_sensitive_destinations_and_signed_in_accounts_never_record(self):
  for page,target in [('/?q=private','buscar-musica'),('/account#reset-password=secret','iniciar-sesion'),('/','email@example.com')]:
   self.assertEqual(self.post(self.guest,'/api/navigation/events',self.event(events=[{'kind':'click','page':page,'target':target}])).status_code,400)
  self.assertFalse(self.post(self.admin,'/api/navigation/events',self.event()).json['recorded'])
  self.assertEqual(self.admin.get('/api/admin/guest-journeys').json['total'],0)
 def test_withdrawal_erases_current_sequence_and_retention_expires(self):
  self.post(self.guest,'/api/navigation/events',self.event());self.assertEqual(self.admin.get('/api/admin/guest-journeys').json['total'],1)
  self.assertTrue(self.post(self.guest,'/api/navigation/consent',{'allowed':False}).json['ok']);self.assertEqual(self.admin.get('/api/admin/guest-journeys').json['total'],0)
  self.post(self.guest,'/api/navigation/events',self.event())
  with patch('analytics.now_utc',return_value=m.now_utc()+timedelta(days=8)):self.assertEqual(self.admin.get('/api/admin/guest-journeys').json['total'],0)
 def test_event_limit_and_invalid_input_do_not_create_unbounded_sequences(self):
  self.assertEqual(self.post(self.guest,'/api/navigation/events',self.event(events=[])).status_code,400)
  self.assertEqual(self.post(self.guest,'/api/navigation/events',self.event(events=[{'kind':'page','page':'/','target':''}]*21)).status_code,400)
  self.assertEqual(self.admin.get('/api/admin/guest-journeys').json['total'],0)
