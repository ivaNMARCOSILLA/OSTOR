"""Exercise guest grants, private channels and room isolation across broadcasts."""
import os,base64,json,unittest
from datetime import timedelta
from unittest.mock import patch,Mock
import app,streamers as st,membership as m,subscriptions as subs
from auth_support import authenticated_client
from registration_support import registration_data

class CollaborationPermissionTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.admin.post('/api/streamers/me',json={'title':'Sala compartida'})
  self.channel=self.admin.get('/api/streamers').json['mine']['id']
  self.owner=self.admin.get('/api/account/me').json['user']['id']
  env=patch.dict(os.environ,{'LIVEKIT_URL':'wss://video.test.invalid','LIVEKIT_API_KEY':'local-test-key','LIVEKIT_API_SECRET':'x'*40,'MAGGY_STREAMERS_ENABLED':'1','OL_RECORDINGS_ENABLED':'0'})
  env.start();self.addCleanup(env.stop)
  self.guest=app.app.test_client();csrf=self.guest.get('/api/account/me').json['csrf']
  data=registration_data(self.guest,{'username':'invited-creator','password':'guest-password-123'})
  self.assertEqual(self.guest.post('/api/account/register',json=data,headers={'X-CSRF-Token':csrf}).status_code,201)
  self.guest_id=self.guest.get('/api/account/me').json['user']['id']
  self.csrf=self.guest.get('/api/account/me').json['csrf']
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO service_grants(member_id,granted_at,granted_by) VALUES(?,?,?)',(self.guest_id,m.stamp(m.now_utc()),self.owner))
 def post_guest(self,path,data):return self.guest.post(path,json=data,headers={'X-CSRF-Token':self.csrf})
 def owner_start(self):
  token=self.admin.post('/api/streamers/'+self.channel+'/token',json={'publish':True})
  self.assertEqual(token.status_code,200)
  with patch('live_access.verified_broadcast',return_value=True):
   self.assertEqual(self.admin.post('/api/streamers/me/live',json={'live':True}).status_code,200)
  return self.claims(token.json['token'])
 def claims(self,token):
  middle=token.split('.')[1];return json.loads(base64.urlsafe_b64decode(middle+'='*(-len(middle)%4)))
 def invite(self):
  self.assertEqual(self.admin.post('/api/streamers/me/guests',json={'username':'invited-creator'}).status_code,200)
 def test_guest_grants_consent_identity_and_new_session_room(self):
  owner_claims=self.owner_start();path='/api/streamers/'+self.channel+'/token'
  self.assertEqual(self.post_guest(path,{'publish':True,'guest':True,'recording_notice_accepted':True}).status_code,403)
  self.invite()
  self.assertEqual(self.post_guest(path,{'publish':True,'guest':True}).status_code,403)
  token=self.post_guest(path,{'publish':True,'guest':True,'recording_notice_accepted':True})
  self.assertEqual(token.status_code,200);claims=self.claims(token.json['token'])
  self.assertEqual(claims['video']['room'],owner_claims['video']['room'])
  self.assertEqual(claims['sub'],'maggy-'+self.guest_id+'-publisher')
  repeated=self.post_guest(path,{'publish':True,'guest':True,'recording_notice_accepted':True})
  self.assertEqual(self.claims(repeated.json['token'])['sub'],claims['sub'])
  self.admin.post('/api/streamers/me/live',json={'live':False})
  new_claims=self.owner_start()
  self.assertNotEqual(claims['video']['room'],new_claims['video']['room'])
  self.assertEqual(self.post_guest(path,{'publish':True,'guest':True,'recording_notice_accepted':True}).status_code,403)
 def test_transient_heartbeat_expiry_preserves_invitation_and_chat_session(self):
  self.owner_start();self.invite()
  with app.app.app_context(),m.database() as conn:
   before=dict(conn.execute('SELECT * FROM live_broadcast_sessions WHERE channel_id=?',(self.channel,)).fetchone())
   conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()-timedelta(seconds=5)),self.channel))
  self.assertTrue(self.guest.get('/api/streamers/'+self.channel+'/access').json['guest_allowed'])
  with patch('live_access.verified_broadcast',return_value=True):self.admin.post('/api/streamers/me/live',json={'live':True})
  with app.app.app_context(),m.database() as conn:
   after=dict(conn.execute('SELECT * FROM live_broadcast_sessions WHERE channel_id=?',(self.channel,)).fetchone())
   self.assertEqual(before,after)
   self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM live_guest_invites WHERE channel_id=?',(self.channel,)).fetchone()['n'],1)
 def test_private_channel_preserves_invited_creators_and_recording_participant(self):
  self.owner_start();self.invite()
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO channel_subscription_settings(channel_id,subscriber_chat,exclusive_live) VALUES(?,1,1)',(self.channel,))
   channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(self.channel,)).fetchone()
  self.assertEqual(self.guest.get('/api/streamers/'+self.channel+'/access').status_code,200)
  path='/api/streamers/'+self.channel+'/comments'
  self.assertEqual(self.post_guest(path,{'text':'Conversación entre invitados'}).status_code,200)
  self.assertEqual(self.guest.get(path).json['comments'][0]['body'],'Conversación entre invitados')
  participants=[{'identity':'maggy-'+self.owner+'-publisher'},{'identity':'maggy-'+self.guest_id+'-publisher'},{'identity':'recording-server','kind':2},{'identity':'not-a-member'}]
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.status_code=200
  with app.app.app_context(),patch('requests.post',return_value=response) as remove:
   self.assertTrue(subs.enforce_room_subscribers(channel,participants,'https://video.test.invalid',{}))
   self.assertEqual(remove.call_count,1);self.assertEqual(remove.call_args.kwargs['json']['identity'],'not-a-member')
 def test_invitation_list_private_and_removal_releases_capacity(self):
  import secrets
  self.owner_start();self.invite();path='/api/streamers/me/guests'
  listing=self.admin.get(path).json
  self.assertEqual(listing['guests'],[{'username':'invited-creator'}]);self.assertEqual(listing['limit'],7)
  self.assertEqual(self.guest.get(path).status_code,403)
  self.assertEqual(self.post_guest(path,{'action':'remove','username':'invited-creator'}).status_code,403)
  with app.app.app_context(),m.database() as conn:
   for i in range(6):
    ident=secrets.token_hex(16)
    conn.execute("INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,'member',?)",(ident,'slot-'+str(i),'not-a-login',m.stamp(m.now_utc())))
  for i in range(5):self.assertEqual(self.admin.post(path,json={'username':'slot-'+str(i)}).status_code,200)
  self.assertEqual(self.admin.post(path,json={'username':'slot-5'}).status_code,409)
  response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.status_code=200
  with patch('requests.post',return_value=response) as remove:
   result=self.admin.post(path,json={'action':'remove','username':'Invited-Creator'})
  self.assertTrue(result.json['disconnected']);self.assertEqual(remove.call_args.kwargs['json']['identity'],'maggy-'+self.guest_id+'-publisher')
  self.assertEqual(self.admin.post(path,json={'username':'slot-5'}).status_code,200)
  self.assertFalse(self.guest.get('/api/streamers/'+self.channel+'/access').json['guest_allowed'])
  self.assertEqual(self.post_guest('/api/streamers/'+self.channel+'/token',{'publish':True,'guest':True,'recording_notice_accepted':True}).status_code,403)
 def test_remove_failure_preserves_revocation_and_does_not_hide_warning(self):
  self.owner_start();self.invite();path='/api/streamers/me/guests'
  import requests
  with patch('requests.post',side_effect=requests.Timeout('local-test-only')):
   result=self.admin.post(path,json={'action':'remove','username':'invited-creator'})
  self.assertEqual(result.status_code,200);self.assertFalse(result.json['disconnected'])
  self.assertEqual(self.admin.get(path).json['guests'],[])
  self.assertFalse(self.guest.get('/api/streamers/'+self.channel+'/access').json['guest_allowed'])
