import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch,Mock
import app
import membership as m
import streamers as st
import live_access as access
from auth_support import authenticated_client

class LiveAccessTests(unittest.TestCase):
 def setUp(self):
  code=patch("human_check.new_code",return_value="OL234");code.start();self.addCleanup(code.stop)
  healthy=patch("live_access.video_service_available",return_value=True);healthy.start();self.addCleanup(healthy.stop)
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.user=app.app.test_client();self.post(self.user,'/api/account/register',{'username':'live-user','password':'live-user-password-123'})
  self.ident=self.user.get('/api/account/me').json['user']['id']
 def post(self,client,path,data):
  token=client.get('/api/account/me').json['csrf']
  if path=='/api/account/live-trial':data=dict(data,human_id=client.get('/api/account/human-check').json['id'],human_answer='OL234')
  return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def pay(self,client=None,reference='REAL-REFERENCE-001',member=None,plan='lifetime'):
  return self.post(client or self.admin,'/api/admin/confirm-payment',{'member_id':member or self.ident,'plan':plan,'reference':reference})
 def test_three_calendar_months_once_and_no_premature_or_repeated_billing(self):
  initial=datetime(2027,1,31,12,tzinfo=timezone.utc)
  with patch.object(st,'live_ready',return_value=False):
   self.assertEqual(self.post(self.user,'/api/account/live-trial',{}).status_code,409)
  with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM live_entitlements').fetchone()['n'],0)
  with patch.object(st,'live_ready',return_value=True),patch.object(st,'streamer_sales_ready',return_value=True),patch.object(access,'now_utc',return_value=initial),patch.object(m,'now_utc',return_value=initial):
   self.assertEqual(self.pay().status_code,409)
   trial=self.post(self.user,'/api/account/live-trial',{});self.assertEqual(trial.json['trial_until'],'2027-04-30T12:00:00+00:00')
   self.assertEqual(self.post(self.user,'/api/account/live-trial',{}).json['trial_until'],trial.json['trial_until'])
   self.assertTrue(self.user.get('/api/account/me').json['user']['streamer_active'])
   self.assertEqual(self.pay().status_code,409)
   for retired in ['welcome','monthly','streamer']:self.assertEqual(self.pay(plan=retired).status_code,400)
  expired=datetime(2027,4,30,12,tzinfo=timezone.utc)
  with patch.object(st,'streamer_sales_ready',return_value=True),patch.object(m,'now_utc',return_value=expired):
   self.assertFalse(self.user.get('/api/account/me').json['user']['active'])
   self.assertEqual(self.pay(self.user).status_code,403)
   result=self.pay();self.assertEqual(result.status_code,200)
   me=self.user.get('/api/account/me').json;self.assertTrue(me['user']['live_lifetime']);self.assertTrue(me['user']['streamer_active'])
   self.assertEqual(me['payments'][0]['amount_cents'],2500)
   self.assertEqual(self.pay(reference='OTHER-REFERENCE-002').status_code,409)
   other=app.app.test_client();self.post(other,'/api/account/register',{'username':'other-live','password':'other-live-password-123'});otherid=other.get('/api/account/me').json['user']['id']
   with app.app.app_context(),m.database() as conn:conn.execute('INSERT INTO live_entitlements(member_id,trial_until) VALUES(?,?)',(otherid,m.stamp(expired-timedelta(seconds=1))))
   self.assertEqual(self.pay(member=otherid).status_code,409)
  self.post(self.admin,'/api/admin/revoke',{'member_id':self.ident})
  self.post(self.user,'/api/account/login',{'username':'live-user','password':'live-user-password-123'})
  self.assertFalse(self.user.get('/api/account/me').json['user']['active'])
  with patch.object(st,'live_ready',return_value=True):self.assertTrue(self.post(self.user,'/api/account/live-trial',{}).json['already_started'])
 def test_visual_check_wrong_answer_replay_and_session_binding(self):
  with patch('human_check.new_code',return_value='OL234'):
   first=self.user.get('/api/account/human-check').json
   self.assertNotIn('OL234',str(first));self.assertTrue(first['image'].startswith('data:image/png;base64,'))
   self.assertEqual(self.post(self.user,'/api/live/founders/claim',{'human_id':first['id'],'human_answer':'WRONG'}).status_code,400)
   self.assertEqual(self.post(self.user,'/api/live/founders/claim',{'human_id':first['id'],'human_answer':'OL234'}).status_code,400)
   second=self.user.get('/api/account/human-check').json
   other=app.app.test_client();self.post(other,'/api/account/register',{'username':'other-captcha','password':'other-captcha-password-123'})
   self.assertEqual(self.post(other,'/api/live/founders/claim',{'human_id':second['id'],'human_answer':'OL234'}).status_code,400)
   third=self.user.get('/api/account/human-check').json
   result=self.post(self.user,'/api/live/founders/claim',{'human_id':third['id'],'human_answer':'OL234'});self.assertEqual(result.status_code,200)
   mine=self.user.get('/api/live/founders').json['mine'];self.assertTrue(mine['future_transfer_eligible'])
   self.assertFalse(self.user.get('/api/live/founders').json['transfer_sales_open'])
 def test_private_camera_and_unverified_heartbeats_cannot_earn_founder_time(self):
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,1,?)',(self.ident,m.stamp(m.now_utc())))
  self.post(self.user,'/api/streamers/me',{'title':'Mi directo'})
  with patch.object(st,'live_ready',return_value=True),patch.object(access,'verified_broadcast',return_value=False):
   self.assertEqual(self.post(self.user,'/api/streamers/me/live',{'live':True}).status_code,409)
  with app.app.app_context(),m.database() as conn:
   self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM founder_activity').fetchone()['n'],0)
  initial=m.now_utc()
  with app.app.app_context(),m.database() as conn,patch.object(access,'now_utc',return_value=initial):access.credit_activity(conn,self.ident)
  # Only contiguous server-verified intervals count, once per clock, not each tab.
  for offset in range(30,1830,30):
   with app.app.app_context(),m.database() as conn,patch.object(access,'now_utc',return_value=initial+timedelta(seconds=offset)):access.credit_activity(conn,self.ident)
  with app.app.app_context(),m.database() as conn:
   info=access.founder_activity(self.ident,conn);self.assertEqual(info['verified_seconds'],1800);self.assertTrue(info['qualified'])
  with app.app.app_context(),m.database() as conn,patch.object(access,'now_utc',return_value=initial+timedelta(days=100)):
   info=access.founder_activity(self.ident,conn);self.assertFalse(info['eligible'])
   access.credit_activity(conn,self.ident);self.assertEqual(access.founder_activity(self.ident,conn)['verified_seconds'],1800)
 def test_admin_grace_extension_never_shortens_a_deadline(self):
  deadline=m.now_utc()+timedelta(days=90)
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,1,?)',(self.ident,m.stamp(m.now_utc())))
   conn.execute('INSERT INTO founder_activity(member_id,qualification_until) VALUES(?,?)',(self.ident,m.stamp(deadline)))
  self.assertEqual(self.post(self.user,'/api/admin/founders/grace',{'member_id':self.ident,'days':30}).status_code,403)
  result=self.post(self.admin,'/api/admin/founders/grace',{'member_id':self.ident,'days':30})
  self.assertEqual(result.status_code,200)
  self.assertEqual(result.json['qualification_until'],m.stamp(deadline+timedelta(days=30)))
  self.assertEqual(self.post(self.admin,'/api/admin/founders/grace',{'member_id':self.ident,'days':-1}).status_code,400)

 def test_livekit_requires_the_creator_identity_and_published_video(self):
  channel={'room_name':'test-room'};user={'id':'owner'};response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.status_code=200
  with patch.dict('os.environ',{'LIVEKIT_API_KEY':'test','LIVEKIT_API_SECRET':'x'*40,'LIVEKIT_URL':'wss://test.invalid'}),patch('requests.post',return_value=response):
   for participant,expected in [({'identity':'maggy-other-a','tracks':[{'source':1}]},False),({'identity':'maggy-owner-a','tracks':[]},False),({'identity':'maggy-owner-a','tracks':[{'source':1,'muted':True}]},False),({'identity':'maggy-owner-a','tracks':[{'source':3}]},True)]:
    response.json.return_value={'participants':[participant]};self.assertEqual(access.verified_broadcast(channel,user),expected)
 def test_phrases_and_promo_actions_are_real_and_bounded(self):
  guest=app.app.test_client();r=guest.get('/api/stickers/hello/phrase');self.assertEqual(r.status_code,200);self.assertTrue(r.json['phrase'])
  self.assertEqual(guest.get('/api/stickers/missing/phrase').status_code,404)
  self.assertEqual(self.post(guest,'/api/promotion/event',{'event':'skip'}).status_code,200)
  self.assertEqual(self.post(guest,'/api/promotion/event',{'event':'made-up'}).status_code,400)
  self.assertEqual(self.admin.get('/api/admin/statistics').json['promotion']['skip'],1)
