import hashlib,hmac,json,time,unittest
from datetime import timedelta
from unittest.mock import patch
import app,membership as m,streamers as st,payments as p
from auth_support import authenticated_client

class ManagedPaymentTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  env=patch.dict('os.environ',{'OL_PAYMENT_PROVIDER':'stripe','OL_PAYMENTS_ENABLED':'0','STRIPE_WEBHOOK_SECRET':'whsec_local_test_platform','STRIPE_CONNECT_WEBHOOK_SECRET':'whsec_local_test_connect'});env.start();self.addCleanup(env.stop)
  self.client=self.member('managed-viewer');self.ident=self.client.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as c:c.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until) VALUES(?,?,?)',(self.ident,m.stamp(m.now_utc()-timedelta(days=100)),m.stamp(m.now_utc()-timedelta(days=8))))
 def test_account_health_admin_only_and_no_private_fields(self):
  self.assertEqual(self.client.get('/api/admin/payments/account-health').status_code,403)
  with patch.dict('os.environ',{'STRIPE_SECRET_KEY':'sk_live_local_fixture'}),patch('payments.stripe',return_value={'charges_enabled':True,'payouts_enabled':False,'details_submitted':True,'email':'private@example.test','requirements':{'currently_due':['business_profile.url'],'past_due':[]}}) as provider:
   response=self.admin.get('/api/admin/payments/account-health')
   self.assertEqual(response.status_code,200);self.assertTrue(response.json['charges_enabled']);self.assertEqual(response.json['requirements_pending'],1)
   self.assertNotIn('private@example.test',response.get_data(as_text=True));provider.assert_called_once_with('GET','/account')

 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  token=client.get('/api/account/me').json['csrf'];return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def member(self,name,paid=False):
  client=app.app.test_client();self.assertEqual(self.post(client,'/api/account/register',{'username':name,'password':'local-managed-test-password-123'}).status_code,201)
  if paid:
   ident=client.get('/api/account/me').json['user']['id']
   with app.app.app_context(),m.database() as c:
    c.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)',(ident,m.stamp(m.now_utc())))
    c.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),ident))
  return client
 def checkout(self,channel=None,checkout_id='cs_local_test'):
  def provider(method,path,data=None,**kwargs):
   if path.startswith('/accounts/'):return {'charges_enabled':True,'payouts_enabled':True}
   self.assertEqual(data['mode'],'payment');self.assertNotIn('payment_intent_data[application_fee_amount]',data)
   return {'id':checkout_id,'url':'https://checkout.stripe.com/c/pay/local-test'}
  data={'annual_terms':True}
  if channel:
   with patch('human_check.new_code',return_value='OL234'):challenge=self.client.get('/api/account/human-check').json
   data={'channel_id':channel,'human_id':challenge['id'],'human_answer':'OL234'}
  with patch.object(p,'ready',return_value=True),patch.object(p,'stripe',side_effect=provider):r=self.post(self.client,'/api/payments/checkout',data)
  self.assertEqual(r.status_code,200,r.json)
  with app.app.app_context(),m.database() as c:return dict(c.execute('SELECT * FROM stripe_orders WHERE checkout_id=?',(checkout_id,)).fetchone())
 def event(self,order,ident='evt_local_paid',scope='platform',amount=None,kind='checkout.session.completed',obj=None,account=None):
  obj=obj or {'id':order['checkout_id'],'payment_status':'paid','amount_total':amount if amount is not None else order['amount_cents'],'currency':'eur','metadata':{'ol_order':order['id']},'payment_intent':'pi_local_test'}
  data={'id':ident,'livemode':True,'type':kind,'data':{'object':obj}}
  if scope=='connect':data['account']=account or order['account_id']
  raw=json.dumps(data).encode();timestamp=str(int(time.time()));secret='whsec_local_test_'+('connect' if scope=='connect' else 'platform');signature=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  return app.app.test_client().post('/api/payments/webhook/'+scope,data=raw,headers={'Content-Type':'application/json','Stripe-Signature':'t='+timestamp+',v1='+signature})
 def test_annual_payment_emails_verified_member_once_after_confirmation(self):
  with app.app.app_context(),m.database() as c:
   c.execute('INSERT INTO member_profiles(member_id,email,nickname,email_verified,updated_at) VALUES(?,?,?,?,?)',(self.ident,'verified@example.test','Cliente',1,m.stamp(m.now_utc())))
  order=self.checkout()
  with patch('notifications.mail_ready',return_value=True),patch('notifications.deliver_to') as deliver:
   self.assertEqual(self.event(order).status_code,200)
   customer_calls=[call for call in deliver.call_args_list if call.args[0]=='verified@example.test']
   self.assertEqual(len(customer_calls),1)
   args=customer_calls[0].args
   self.assertEqual(args[0],'verified@example.test');self.assertIn('solicita tu plaza',args[1]);self.assertIn('/live#founders',args[2])
   self.assertEqual(self.event(order).status_code,200)
   with app.app.app_context():p.send_annual_access_emails()
   self.assertEqual(len([call for call in deliver.call_args_list if call.args[0]=='verified@example.test']),1)

 def test_no_charge_before_configuration_and_browser_return_never_grants(self):
  self.assertFalse(self.client.get('/api/payments/status').json['enabled'])
  self.assertEqual(self.post(self.client,'/api/payments/checkout',{'annual_terms':True}).status_code,409)
  self.client.get('/account?payment=processing')
  self.assertFalse(self.client.get('/api/account/me').json['user']['live_annual'])
  self.assertEqual(app.app.test_client().post('/api/payments/webhook/platform',json={'payment_status':'paid'}).status_code,400)
  self.assertEqual(self.post(self.admin,'/api/admin/confirm-payment',{'plan':'lifetime','reference':'not-a-managed-payment'}).status_code,409)
 def test_signature_amount_idempotency_and_refund(self):
  order=self.checkout();self.assertEqual(self.event(order,amount=1).status_code,400)
  self.assertFalse(self.client.get('/api/account/me').json['user']['live_annual'])
  self.assertEqual(self.event(order).status_code,200)
  self.assertTrue(self.client.get('/api/account/me').json['user']['live_annual'])
  self.assertTrue(self.event(order).json['duplicate'])
  self.assertEqual(self.event(order,ident='evt_second_same_checkout').status_code,200)
  self.assertEqual(len(self.client.get('/api/account/me').json['payments']),1)
  refund=self.event(order,ident='evt_full_refund',kind='charge.refunded',obj={'payment_intent':'pi_local_test','refunded':True})
  self.assertEqual(refund.status_code,200);self.assertFalse(self.client.get('/api/account/me').json['user']['live_annual'])
  self.assertEqual(len(self.client.get('/api/account/me').json['payments']),1)
 def test_out_of_order_refund_prevents_later_access(self):
  order=self.checkout();self.assertEqual(self.event(order,ident='evt_early_refund',kind='charge.refunded',obj={'payment_intent':'pi_local_test','refunded':True}).status_code,200)
  self.assertEqual(self.event(order).status_code,200)
  self.assertFalse(self.client.get('/api/account/me').json['user']['live_annual'])
 def test_timestamp_and_payload_tampering_are_rejected(self):
  raw=b'{"id":"evt_test"}';sig=hmac.new(b'whsec_test',b'1.'+raw,hashlib.sha256).hexdigest()
  with self.assertRaises(ValueError):p.verified_event(raw,'t=1,v1='+sig,'whsec_test')
  with self.assertRaises(ValueError):p.verified_event(raw,'t='+str(int(time.time()))+',v1=0000','whsec_test')
 def test_ambiguous_checkout_cannot_create_second_order(self):
  with patch.object(p,'ready',return_value=True),patch.object(p,'stripe',side_effect=p.PaymentError('local unavailable')):
   self.assertEqual(self.post(self.client,'/api/payments/checkout',{'annual_terms':True}).status_code,409)
   self.assertEqual(self.post(self.client,'/api/payments/checkout',{'annual_terms':True}).status_code,409)
  with app.app.app_context(),m.database() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM stripe_orders').fetchone()['n'],1)
 def test_creator_uses_approved_destination_and_same_processor_without_commission(self):
  creator=self.member('managed-creator',paid=True);mod=self.member('gref');creator_id=creator.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as c:
   c.execute('INSERT INTO stripe_accounts VALUES(?,?,?)',(creator_id,'acct_local_creator',m.stamp(m.now_utc())))
   c.execute('UPDATE live_entitlements SET paid_at=? WHERE member_id=?',(m.stamp(m.now_utc()),self.ident))
   c.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),self.ident))
  channel=self.post(creator,'/api/streamers/me',{'title':'Managed creator','paypal_url':'','owns_paypal':False}).json['channel']['id']
  self.post(self.admin,'/api/admin/subscription-moderator',{'username':'Gref'});self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':['review_agreements','approve_agreements']})
  proposal=self.post(creator,'/api/channel-subscriptions/propose',{'price_cents':350,'period':'month','benefits':['badge','exclusive_live']});self.assertEqual(proposal.status_code,200,proposal.json)
  for client,party in [(creator,'creator'),(self.admin,'admin'),(mod,'moderator')]:self.assertEqual(self.post(client,'/api/channel-subscriptions/approve',{'agreement_id':proposal.json['agreement_id'],'party':party}).status_code,200)
  order=self.checkout(channel,checkout_id='cs_local_creator');self.assertEqual(order['account_id'],'acct_local_creator');self.assertEqual(order['amount_cents'],350)
  self.assertEqual(self.event(order,scope='connect',account='acct_unrelated').status_code,200)
  self.assertEqual(self.client.get('/api/channel-subscriptions/'+channel).json['subscriber_count'],0)
  self.assertEqual(self.event(order,scope='connect',ident='evt_correct_creator').status_code,200)
  info=self.client.get('/api/channel-subscriptions/'+channel).json;self.assertEqual(info['subscriber_count'],1);self.assertIn('badge',info['mine']);self.assertIsNone(info['payment_url'])
  self.assertEqual(self.client.get('/api/account/me').json['payments'],[])
 def test_subscription_captcha_is_required_single_use_and_no_charge_on_failure(self):
  with patch.object(p,'ready',return_value=True),patch.object(p,'stripe') as provider:
   self.assertEqual(self.post(self.client,'/api/payments/checkout',{'channel_id':'no-channel'}).status_code,400)
   with patch('human_check.new_code',return_value='OL234'):proof=self.client.get('/api/account/human-check').json
   data={'channel_id':'no-channel','human_id':proof['id'],'human_answer':'WRONG'}
   self.assertEqual(self.post(self.client,'/api/payments/checkout',data).status_code,400)
   data['human_answer']='OL234';self.assertEqual(self.post(self.client,'/api/payments/checkout',data).status_code,400)
   provider.assert_not_called()
  with app.app.app_context(),m.database() as db:self.assertIsNone(db.execute('SELECT id FROM human_challenges WHERE id=?',(proof['id'],)).fetchone())
 def test_play_distribution_never_enables_web_checkout(self):
  self.client.get('/?distribution=googleplay')
  with patch.dict('os.environ',{'OL_PAYMENTS_ENABLED':'1','STRIPE_SECRET_KEY':'sk_live_local_only'}),patch.object(st,'streamer_sales_ready',return_value=True):self.assertFalse(self.client.get('/api/payments/status').json['enabled'])

 def test_restricted_live_key_is_recognized_without_enabling_video_or_sales(self):
  with patch.dict('os.environ',{'STRIPE_SECRET_KEY':'rk_live_local_only','STRIPE_WEBHOOK_SECRET':'whsec_local_only','STRIPE_CONNECT_WEBHOOK_SECRET':'whsec_connect_local','OL_PAYMENTS_ENABLED':'1'}),patch.object(st,'streamer_sales_ready',return_value=False):
   self.assertTrue(p.configured())
   result=self.client.get('/api/payments/status');self.assertFalse(result.json['enabled'])
   self.assertTrue(self.admin.get('/api/admin/launch-readiness').json['checks']['payments']['STRIPE_SECRET_KEY'])
  with patch.dict('os.environ',{'STRIPE_SECRET_KEY':'pk_live_local_only'}):self.assertFalse(p.configured())
