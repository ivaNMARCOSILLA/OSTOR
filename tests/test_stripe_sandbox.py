import hashlib,hmac,json,time,unittest
from unittest.mock import patch
import app,membership as m,streamers as st,payments as p
from auth_support import authenticated_client

class StripeSandboxTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  env=patch.dict('os.environ',{'STRIPE_TEST_SECRET_KEY':'sk_test_local_only','STRIPE_TEST_WEBHOOK_SECRET':'whsec_local_sandbox','STRIPE_WEBHOOK_SECRET':'whsec_local_platform'});env.start();self.addCleanup(env.stop)
 def checkout(self):
  with patch.object(p,'stripe',return_value={'id':'cs_test_local_only','url':'https://checkout.stripe.com/c/pay/local-test'}) as remote:
   r=self.admin.post('/api/admin/payments/test-checkout',json={})
   self.assertEqual(r.status_code,200);self.assertFalse(r.json['grants_access']);self.assertTrue(remote.call_args.kwargs['sandbox'])
  with app.app.app_context(),m.database() as c:return dict(c.execute("SELECT * FROM stripe_orders WHERE kind='test'").fetchone())
 def event(self,order,scope='test',kind='checkout.session.completed',ident='evt_sandbox',obj=None):
  data={'id':ident,'livemode':scope!='test','type':kind,'data':{'object':obj or {'id':order['checkout_id'],'payment_status':'paid','amount_total':2500,'currency':'eur','metadata':{'ol_order':order['id']},'payment_intent':'pi_sandbox_local'}}}
  raw=json.dumps(data).encode();stamp=str(int(time.time()));secret='whsec_local_sandbox' if scope=='test' else 'whsec_local_platform';sig=hmac.new(secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  return app.app.test_client().post('/api/payments/webhook/'+scope,data=raw,headers={'Content-Type':'application/json','Stripe-Signature':'t='+stamp+',v1='+sig})
 def test_admin_only_and_public_key_is_insufficient(self):
  self.assertEqual(app.app.test_client().get('/api/admin/payments/test-status').status_code,403)
  with patch.dict('os.environ',{'STRIPE_TEST_SECRET_KEY':'pk_test_local_only'}):
   self.assertFalse(self.admin.get('/api/admin/payments/test-status').json['configured'])
   self.assertEqual(self.admin.post('/api/admin/payments/test-checkout',json={}).status_code,409)
 def test_sandbox_signed_payment_never_grants_access_or_sends_financial_mail(self):
  order=self.checkout()
  with patch('notifications.notify') as mail:
   self.assertEqual(self.event(order).status_code,200);self.assertTrue(self.event(order).json['duplicate']);mail.assert_not_called()
  with app.app.app_context(),m.database() as c:
   self.assertEqual(c.execute('SELECT state FROM stripe_orders').fetchone()['state'],'test_paid')
   for table in ['payments','creator_subscriptions','live_entitlements','streamer_access','live_founders']:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM '+table).fetchone()['n'],0)
  self.assertEqual(self.event(order,kind='charge.refunded',ident='evt_sandbox_refund',obj={'payment_intent':'pi_sandbox_local','refunded':True}).status_code,200)
  with app.app.app_context(),m.database() as c:self.assertIsNone(c.execute('SELECT access_until FROM members').fetchone()['access_until'])
 def test_live_endpoint_cannot_fulfill_sandbox_order(self):
  order=self.checkout();self.assertEqual(self.event(order,scope='platform').status_code,400)
  with app.app.app_context(),m.database() as c:self.assertIsNone(c.execute('SELECT paid_at FROM stripe_orders').fetchone()['paid_at'])
 def test_pending_sandbox_checkout_prevents_duplicate_sessions(self):
  self.checkout()
  with patch.object(p,'stripe',return_value={'id':'cs_test_local_only','status':'open','url':'https://checkout.stripe.com/c/pay/local-test'}) as remote:
   result=self.admin.post('/api/admin/payments/test-checkout',json={});self.assertEqual(result.status_code,200);self.assertTrue(result.json['resumed']);self.assertEqual(remote.call_args.args[0],'GET')
  with app.app.app_context(),m.database() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM stripe_orders').fetchone()['n'],1)

 def test_definitive_failure_exposes_safe_code_and_does_not_lock_out_retry(self):
  with patch.object(p,'stripe',side_effect=p.PaymentError('Stripe necesita completar el negocio.','business_profile_required')):
   result=self.admin.post('/api/admin/payments/test-checkout',json={})
   self.assertEqual(result.status_code,409);self.assertEqual(result.json['code'],'business_profile_required')
  with app.app.app_context(),m.database() as c:self.assertEqual(c.execute('SELECT state FROM stripe_orders').fetchone()['state'],'failed')
  self.checkout()
