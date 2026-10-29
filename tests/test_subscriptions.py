import unittest
from datetime import timedelta
from unittest.mock import patch
import app
import membership as m
import streamers as st
from auth_support import authenticated_client

class CreatorSubscriptionTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.creator=self.member('channel-owner',creator=True)
  self.mod=self.member('gref')
  self.viewer=self.member('channel-viewer')
  self.other=self.member('other-viewer')
  self.assertEqual(self.post(self.admin,'/api/admin/subscription-moderator',{'username':'Gref'}).status_code,200)
  self.assertEqual(self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':['review_agreements','approve_agreements']}).status_code,200)
  result=self.post(self.creator,'/api/streamers/me',{'title':'Mi canal Ol','paypal_url':'https://paypal.me/CreatorOnly','owns_paypal':True})
  self.channel=result.json['channel']['id']
 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  token=client.get('/api/account/me').json['csrf'];return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def member(self,name,creator=False):
  c=app.app.test_client();self.assertEqual(self.post(c,'/api/account/register',{'username':name,'password':'subscription-test-password-123'}).status_code,201)
  ident=c.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until,paid_at) VALUES(?,?,?,?)',(ident,m.stamp(m.now_utc()),m.stamp(m.now_utc()-timedelta(days=1)),m.stamp(m.now_utc())))
   conn.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),ident))
  return c
 def proposal(self,price=350):
  r=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':price,'period':'month','benefits':['badge','subscriber_chat','exclusive_live']});self.assertEqual(r.status_code,200);return r.json['agreement_id']
 def approve_all(self,ident):
  for client,party in [(self.creator,'creator'),(self.admin,'admin'),(self.mod,'moderator')]:
   r=self.post(client,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':party});self.assertEqual(r.status_code,200)
  self.assertTrue(r.json['agreement_activated'])
 def confirm(self,reference='CREATOR-RECEIPT-001',price=350,client=None):
  with patch.object(st,'streamer_sales_ready',return_value=True):return self.post(client or self.creator,'/api/channel-subscriptions/'+self.channel+'/confirm',{'username':'channel-viewer','reference':reference,'amount_cents':price,'verified_receipt':True})
 def test_three_independent_approvals_and_revision_cannot_reuse_old_consents(self):
  ident=self.proposal();url='/api/channel-subscriptions/'+self.channel
  self.assertIsNone(app.app.test_client().get(url).json['agreement'])
  self.assertEqual(self.post(self.viewer,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':'admin'}).status_code,403)
  self.post(self.creator,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':'creator'})
  self.post(self.admin,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':'admin'})
  self.assertIsNone(self.viewer.get(url).json['agreement'])
  self.assertEqual(self.confirm().status_code,409)
  self.approve_all(ident)
  with patch.object(st,'streamer_sales_ready',return_value=False):self.assertIsNone(self.viewer.get(url).json['payment_url'])
  with patch.object(st,'streamer_sales_ready',return_value=True):
   offer=self.viewer.get(url).json;self.assertEqual(offer['payment_url'],'https://paypal.me/CreatorOnly/3.50EUR')
  changed=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':400,'period':'month','benefits':['badge','subscriber_chat','exclusive_live']})
  self.assertTrue(changed.json['automatic_price']);self.assertEqual(self.viewer.get(url).json['agreement']['price_cents'],400)
  revised=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':400,'period':'month','benefits':['badge']})
  self.assertEqual(revised.status_code,200);next_id=revised.json['agreement_id']
  self.assertEqual(self.post(self.mod,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':'moderator'}).status_code,409)
  self.approve_all(next_id);self.assertEqual(self.viewer.get(url).json['agreement']['price_cents'],400)
 def test_receipt_amount_reference_and_privileges_are_enforced(self):
  self.approve_all(self.proposal())
  self.assertEqual(self.confirm(client=self.viewer).status_code,403)
  self.assertEqual(self.confirm(client=self.mod).status_code,403)
  self.assertEqual(self.confirm(price=100).status_code,400)
  self.assertEqual(self.confirm().status_code,200)
  self.assertEqual(self.confirm().status_code,409)
  info=self.viewer.get('/api/channel-subscriptions/'+self.channel).json
  self.assertEqual(info['subscriber_count'],1);self.assertIn('badge',info['mine'])
  self.assertEqual(self.other.get('/api/channel-subscriptions/'+self.channel+'/members').status_code,403)
  self.assertEqual(self.creator.get('/api/channel-subscriptions/'+self.channel+'/members').json['total'],1)
  self.assertEqual(self.viewer.get('/api/account/me').json['payments'],[])
 def test_exclusive_video_chat_badge_and_private_history_survive_mode_changes(self):
  self.approve_all(self.proposal());self.assertEqual(self.confirm().status_code,200)
  mode='/api/channel-subscriptions/'+self.channel+'/mode'
  self.assertEqual(self.post(self.other,mode,{'subscriber_chat':True,'exclusive_live':True}).status_code,403)
  self.assertEqual(self.post(self.creator,mode,{'subscriber_chat':True,'exclusive_live':True}).status_code,200)
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(minutes=3)),self.channel))
  comments='/api/streamers/'+self.channel+'/comments'
  self.assertEqual(self.post(self.other,comments,{'text':'No estoy suscrito'}).status_code,403)
  self.assertEqual(self.post(self.viewer,comments,{'text':'Hola, comunidad'}).status_code,200)
  self.assertTrue(self.viewer.get(comments).json['comments'][0]['subscriber_badge'])
  self.assertEqual(self.other.get(comments).json['comments'],[])
  self.post(self.creator,mode,{'subscriber_chat':False,'exclusive_live':False})
  self.assertEqual(self.other.get(comments).json['comments'],[])
  self.post(self.creator,mode,{'subscriber_chat':True,'exclusive_live':True})
  with patch.object(st,'live_ready',return_value=True),patch.object(st,'mint_token',return_value='local-test-token'),patch.dict('os.environ',{'LIVEKIT_URL':'wss://test.example.org'}):
   self.assertEqual(self.post(self.other,'/api/streamers/'+self.channel+'/token',{'publish':False}).status_code,403)
   self.assertEqual(self.post(self.viewer,'/api/streamers/'+self.channel+'/token',{'publish':False}).status_code,200)
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE creator_subscriptions SET ends_at=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),))
  self.assertEqual(self.viewer.get('/api/channel-subscriptions/'+self.channel).json['subscriber_count'],0)
  self.assertEqual(self.post(self.viewer,comments,{'text':'Ya ha vencido'}).status_code,403)
 def test_room_revalidation_removes_expired_viewers_and_revoked_moderator_loses_scope(self):
  import subscriptions as subs
  from unittest.mock import Mock
  self.approve_all(self.proposal());self.confirm()
  self.post(self.creator,'/api/channel-subscriptions/'+self.channel+'/mode',{'subscriber_chat':False,'exclusive_live':True})
  owner_id=self.creator.get('/api/account/me').json['user']['id'];viewer_id=self.viewer.get('/api/account/me').json['user']['id'];other_id=self.other.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as conn:
   channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(self.channel,)).fetchone()
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.status_code=200
  participants=[{'identity':'maggy-'+ident+'-0123456789'} for ident in [owner_id,viewer_id,other_id]]
  with app.app.app_context(),patch('requests.post',return_value=response) as remove:
   self.assertTrue(subs.enforce_room_subscribers(channel,participants,'https://test.example.org',{'Authorization':'Bearer local-test'}))
   self.assertEqual(remove.call_count,1)
   self.assertEqual(remove.call_args.kwargs['json']['identity'],'maggy-'+other_id+'-0123456789')
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,200)
  self.post(self.admin,'/api/admin/revoke',{'member_id':self.mod.get('/api/account/me').json['user']['id']})
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,403)

 def test_payout_change_pauses_payments_and_old_benefits_do_not_change(self):
  self.approve_all(self.proposal());self.confirm()
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET paypal_url=? WHERE id=?',('https://paypal.me/ChangedOwner',self.channel))
  with patch.object(st,'streamer_sales_ready',return_value=True):self.assertFalse(self.viewer.get('/api/channel-subscriptions/'+self.channel).json['payments_enabled'])
  self.assertEqual(self.confirm(reference='NEW-RECEIPT-002').status_code,409)
  self.assertIn('badge',self.viewer.get('/api/channel-subscriptions/'+self.channel).json['mine'])

 def test_admin_alone_grants_reviews_approvals_and_revokes_immediately(self):
  endpoint='/api/admin/moderator-permissions'
  ident=self.proposal()
  self.assertEqual(self.post(self.admin,endpoint,{'permissions':[]}).status_code,200)
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,403)
  self.assertEqual(self.post(self.mod,endpoint,{'permissions':['review_agreements','approve_agreements']}).status_code,403)
  self.assertEqual(self.post(self.viewer,endpoint,{'permissions':[]}).status_code,403)
  self.assertEqual(self.post(self.admin,endpoint,{'permissions':['approve_agreements']}).status_code,400)
  self.assertEqual(self.post(self.admin,endpoint,{'permissions':['admin']}).status_code,400)
  self.assertEqual(self.post(self.admin,endpoint,{'permissions':['review_agreements']}).status_code,200)
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,200)
  self.assertEqual(self.post(self.mod,'/api/channel-subscriptions/approve',{'agreement_id':ident,'party':'moderator'}).status_code,403)
  self.post(self.admin,endpoint,{'permissions':['review_agreements','approve_agreements']})
  self.approve_all(ident)
  self.post(self.admin,endpoint,{'permissions':[]})
  with patch.object(st,'streamer_sales_ready',return_value=True):self.assertIsNone(self.viewer.get('/api/channel-subscriptions/'+self.channel).json['payment_url'])
  self.post(self.admin,'/api/admin/subscription-moderator',{'username':'Gref'})
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,403)

 def test_designation_alone_never_grants_permissions(self):
  with app.app.app_context(),m.database() as conn:conn.execute('DELETE FROM moderator_permissions')
  self.post(self.admin,'/api/admin/subscription-moderator',{'username':'Gref'})
  self.assertEqual(self.mod.get('/api/channel-subscriptions/reviewer').json['permissions'],[])
  self.assertEqual(self.mod.get('/api/channel-subscriptions/review').status_code,403)
