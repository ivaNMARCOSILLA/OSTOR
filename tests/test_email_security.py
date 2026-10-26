import unittest
from unittest.mock import patch
from datetime import timedelta
from urllib.parse import urlsplit,parse_qs
import app,membership as m,email_security as es,two_factor as tf
from auth_support import authenticated_client
from registration_support import registration_data

class EmailSecurityTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  self.ready=patch.object(es,'mail_ready',return_value=True);self.ready.start();self.addCleanup(self.ready.stop)
  self.delivery=patch.object(es,'deliver_to');self.send=self.delivery.start();self.addCleanup(self.delivery.stop)
  self.user=app.app.test_client();self.password='a-test-email-password-123'
 def post(self,client,path,data):
  if path in {'/api/account/register','/api/account/password/request'}:data=registration_data(client,data)
  csrf=client.get('/api/account/me').json['csrf'];return client.post(path,json=data,headers={'X-CSRF-Token':csrf})
 def register(self,client=None,**extra):return self.post(client or self.user,'/api/account/register',dict(username='email-user',password=self.password,email='Private@Example.test',nickname='Viejo Ol',**extra))
 def token(self,purpose):
  body=self.send.call_args.args[2];link=next(line for line in body.splitlines() if line.startswith('https://'))
  return parse_qs(urlsplit(link).fragment)[purpose][0]
 def verify(self):
  self.assertEqual(self.register().status_code,201);token=self.token('verify-email')
  self.assertEqual(self.post(self.user,'/api/account/email/confirm',{'token':token}).status_code,200)
 def reset_request(self):
  result=self.post(self.user,'/api/account/password/request',{'email':'private@example.test'})
  self.assertEqual(result.status_code,200);return self.token('reset-password')
 def test_registration_private_profile_and_verification_before_email_login(self):
  result=self.register();self.assertEqual(result.status_code,201);self.assertTrue(result.json['verification_sent'])
  me=self.user.get('/api/account/me').json;self.assertEqual(me['profile']['email'],'private@example.test');self.assertFalse(me['profile']['email_verified']);self.assertEqual(me['user']['nickname'],'Viejo Ol');self.assertNotIn('email',me['user'])
  another=app.app.test_client();login={'username':'PRIVATE@EXAMPLE.TEST','password':self.password}
  self.assertEqual(self.post(another,'/api/account/login',login).status_code,401)
  token=self.token('verify-email')
  with app.app.app_context(),m.database() as c:
   row=c.execute('SELECT token_hash FROM email_tokens').fetchone();self.assertNotEqual(row['token_hash'],token);self.assertEqual(len(row['token_hash']),64)
  self.assertEqual(self.post(another,'/api/account/email/confirm',{'token':token}).status_code,200)
  self.assertEqual(self.post(another,'/api/account/email/confirm',{'token':token}).status_code,400)
  self.assertEqual(self.post(another,'/api/account/login',login).status_code,200)
  self.assertEqual(self.send.call_args.args[0],'private@example.test')
 def test_reset_generic_human_protected_single_use_and_old_sessions_closed(self):
  self.verify();other=app.app.test_client();self.assertEqual(self.post(other,'/api/account/login',{'username':'email-user','password':self.password}).status_code,200)
  unknown=self.post(other,'/api/account/password/request',{'email':'absent@example.test'});token=self.reset_request()
  known=self.post(other,'/api/account/password/request',{'email':'private@example.test'});self.assertEqual(unknown.json,known.json)
  new='a-brand-new-email-password-123';result=self.post(self.user,'/api/account/password/reset',{'token':token,'password':new});self.assertEqual(result.status_code,200)
  self.assertIsNone(other.get('/api/account/me').json['user']);self.assertIsNone(self.user.get('/api/account/me').json['user'])
  self.assertEqual(self.post(other,'/api/account/password/reset',{'token':token,'password':'yet-another-password-123'}).status_code,400)
  self.assertEqual(self.post(other,'/api/account/login',{'username':'email-user','password':self.password}).status_code,401)
  self.assertEqual(self.post(other,'/api/account/login',{'username':'private@example.test','password':new}).status_code,200)
 def test_expiry_purpose_and_changed_address_reject_old_links(self):
  self.assertEqual(self.register().status_code,201);token=self.token('verify-email')
  self.assertEqual(self.post(self.user,'/api/account/password/reset',{'token':token,'password':'another-long-password-123'}).status_code,400)
  self.assertEqual(self.post(self.user,'/api/account/profile',{'email':'new@example.test','nickname':'Nuevo','password':'wrong'}).status_code,403)
  self.assertEqual(self.post(self.user,'/api/account/profile',{'email':'new@example.test','nickname':'Nuevo','password':self.password}).status_code,200)
  self.assertEqual(self.post(self.user,'/api/account/email/confirm',{'token':token}).status_code,400)
  token=self.token('verify-email')
  with app.app.app_context(),m.database() as c:c.execute('UPDATE email_tokens SET expires_at=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),))
  self.assertEqual(self.post(self.user,'/api/account/email/confirm',{'token':token}).status_code,400)
 def test_mail_failure_does_not_lose_account_and_email_is_unique(self):
  self.send.side_effect=RuntimeError('mail unavailable');result=self.register();self.assertEqual(result.status_code,201);self.assertFalse(result.json['verification_sent'])
  other=app.app.test_client();result=self.post(other,'/api/account/register',{'username':'other-email','email':'PRIVATE@example.test','password':self.password});self.assertEqual(result.status_code,400)
  self.assertIsNone(other.get('/api/account/me').json['user'])
  self.assertEqual(self.post(self.user,'/api/account/login',{'username':'email-user','password':self.password}).status_code,200)
 def test_reset_keeps_two_factor_required(self):
  self.verify();ident=self.user.get('/api/account/me').json['user']['id'];token=self.reset_request()
  with app.app.app_context(),m.database() as c:c.execute('INSERT INTO member_two_factor(member_id,nonce,enabled_at,key_id) VALUES(?,?,?,?)',(ident,'local-email-test',m.stamp(m.now_utc()),tf.key_id()))
  self.assertEqual(self.post(self.user,'/api/account/password/reset',{'token':token,'password':'changed-with-two-factor-123'}).status_code,200)
  result=self.post(self.user,'/api/account/login',{'username':'email-user','password':'changed-with-two-factor-123'});self.assertEqual(result.status_code,401);self.assertEqual(result.json['code'],'two_factor_required')
 def test_csrf_and_no_proof_cannot_request_recovery(self):
  self.verify();csrf=self.user.get('/api/account/me').json['csrf'];self.send.reset_mock()
  result=self.user.post('/api/account/password/request',json={'email':'private@example.test'},headers={'X-CSRF-Token':csrf});self.assertEqual(result.status_code,400);self.send.assert_not_called()
  self.assertEqual(self.user.post('/api/account/password/reset',json={'token':'fake','password':'valid-test-password-123'}).status_code,403)
 def test_resend_gmail_sender_is_not_claimed_ready_for_clients(self):
  with patch.dict('os.environ',{'RESEND_API_KEY':'local-only-mail-test','OL_EMAIL_FROM':'Ol <sender@gmail.com>'}):
   result=self.admin.get('/api/admin/email-health').json
   self.assertFalse(result['customer_sender_configured']);self.assertFalse(result['provider_delivery_verified'])
  with patch.dict('os.environ',{'RESEND_API_KEY':'local-only-mail-test','OL_EMAIL_FROM':'Ol <cuentas@electronicama.com>'}):
   result=self.admin.get('/api/admin/email-health').json
   self.assertTrue(result['customer_sender_configured']);self.assertFalse(result['provider_delivery_verified'])
  self.assertEqual(app.app.test_client().get('/api/admin/email-health').status_code,403)
