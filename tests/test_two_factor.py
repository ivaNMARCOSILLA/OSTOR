import base64
import unittest
from unittest.mock import patch
from datetime import timedelta
import app
import membership as m
import two_factor as tf
from auth_support import authenticated_client

class TwoFactorTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  self.user=app.app.test_client();self.post(self.user,'/api/account/register',{'username':'secure-user','password':'secure-user-password-123'})
  self.tick=1000000;clock=patch.object(tf,'counter_now',side_effect=lambda:self.tick);clock.start();self.addCleanup(clock.stop)
 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  csrf=client.get('/api/account/me').json['csrf'];return client.post(path,json=data,headers={'X-CSRF-Token':csrf})
 def password(self,**extra):return dict(password='secure-user-password-123',**extra)
 def login(self,client,**extra):return self.post(client,'/api/account/login',dict(username='secure-user',**self.password(**extra)))
 def test_standard_hotp_vector(self):self.assertEqual(tf.totp(b'12345678901234567890',1),'287082')
 def test_optional_setup_totp_replay_recovery_and_session_invalidation(self):
  old=app.app.test_client();self.assertEqual(self.login(old).status_code,200)
  self.assertFalse(self.user.get('/api/account/2fa/status').json['enabled'])
  self.assertEqual(self.post(self.user,'/api/account/2fa/setup',{'password':'wrong'}).status_code,403)
  setup=self.post(self.user,'/api/account/2fa/setup',self.password());self.assertEqual(setup.status_code,200)
  secret=setup.json['secret'];key=base64.b32decode(secret);code=tf.totp(key,self.tick)
  self.assertEqual(self.post(self.user,'/api/account/2fa/enable',{'otp':'bad'}).status_code,400)
  enabled=self.post(self.user,'/api/account/2fa/enable',{'otp':code});self.assertEqual(enabled.status_code,200)
  codes=enabled.json['recovery_codes'];self.assertEqual(len(set(codes)),8)
  self.assertIsNone(old.get('/api/account/me').json['user'])
  stranger=app.app.test_client();needed=self.login(stranger);self.assertEqual(needed.status_code,401);self.assertEqual(needed.json['code'],'two_factor_required')
  self.assertIsNone(stranger.get('/api/account/me').json['user'])
  self.assertEqual(self.login(stranger,otp=code).status_code,401)
  self.tick+=1;newcode=tf.totp(key,self.tick);self.assertEqual(self.login(stranger,otp=newcode).status_code,200)
  second=app.app.test_client();self.assertEqual(self.login(second,otp=newcode).status_code,401)
  self.assertEqual(self.login(second,recovery_code=codes[0]).status_code,200)
  third=app.app.test_client();self.assertEqual(self.login(third,recovery_code=codes[0]).status_code,401)
  self.assertEqual(self.user.get('/api/account/2fa/status').json['recovery_remaining'],7)
  with app.app.app_context(),m.database() as conn:
   row=conn.execute('SELECT nonce FROM member_two_factor').fetchone();self.assertNotEqual(row['nonce'],secret)
   hashes=[r['code_hash'] for r in conn.execute('SELECT code_hash FROM two_factor_recovery').fetchall()]
   self.assertFalse(any(c in hashes for c in codes))
  self.assertEqual(self.post(self.user,'/api/account/2fa/disable',{'password':'wrong','recovery_code':codes[1]}).status_code,403)
  self.assertEqual(self.post(self.user,'/api/account/2fa/disable',self.password(recovery_code=codes[1])).status_code,200)
  self.assertFalse(self.user.get('/api/account/2fa/status').json['enabled'])
  self.assertIsNone(stranger.get('/api/account/me').json['user'])
  self.assertEqual(self.login(app.app.test_client()).status_code,200)
 def test_pending_setup_expiry_and_no_secrets_in_status(self):
  self.post(self.user,'/api/account/2fa/setup',self.password())
  status=self.user.get('/api/account/2fa/status').json
  self.assertNotIn('secret',status);self.assertNotIn('nonce',status)
  with patch.object(tf,'now_utc',return_value=m.now_utc()+timedelta(minutes=11)):
   self.assertEqual(self.post(self.user,'/api/account/2fa/enable',{'otp':'123456'}).status_code,409)
  self.assertFalse(self.user.get('/api/account/2fa/status').json['enabled'])
