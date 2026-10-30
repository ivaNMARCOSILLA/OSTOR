"""Session-isolated chat and idempotent, private comment reactions."""
from test_live_chat_feed import ChatFeedTests
from datetime import timedelta
import membership as m,app

class CollaborationTests(ChatFeedTests):
 def test_likes_are_idempotent_and_require_login(self):
  path='/api/streamers/'+self.channel+'/comments'
  self.admin.post(path,json={'text':'Hola'})
  message=self.admin.get(path).json['comments'][-1]['id'];url=path+'/'+message+'/like'
  self.assertIn(app.app.test_client().post(url,json={'liked':True}).status_code,(401,403))
  self.assertEqual(self.admin.post(url,json={'liked':True}).json['likes'],1)
  self.assertEqual(self.admin.post(url,json={'liked':True}).json['likes'],1)
  feed=self.admin.get(path).json
  self.assertEqual(feed['reactions'][0]['likes'],1)
  self.assertEqual(self.admin.post(url,json={'liked':False}).json['likes'],0)
 def test_previous_session_comments_stay_private_to_admin_history(self):
  path='/api/streamers/'+self.channel+'/comments'
  self.admin.post(path,json={'text':'Anterior'})
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_broadcast_sessions(channel_id,started_at) VALUES(?,?)',(self.channel,m.stamp(m.now_utc()+timedelta(seconds=1))))
  self.assertEqual(self.admin.get(path).json['comments'],[])
 def test_invite_is_bound_to_current_broadcast(self):
  import streamers
  with app.app.app_context(),m.database() as conn:
   channel=conn.execute('SELECT * FROM streamer_channels WHERE id=?',(self.channel,)).fetchone()
   conn.execute('INSERT INTO live_broadcast_sessions(channel_id,started_at) VALUES(?,?)',(self.channel,'session-a'))
   conn.execute('INSERT INTO live_guest_invites VALUES(?,?,?)',(self.channel,self.member,'session-a'))
   self.assertTrue(streamers.guest_allowed(conn,channel,{'id':self.member}))
   conn.execute('UPDATE live_broadcast_sessions SET started_at=? WHERE channel_id=?',('session-b',self.channel))
   self.assertFalse(streamers.guest_allowed(conn,channel,{'id':self.member}))

 def test_host_cannot_invite_more_than_six_guests(self):
  import secrets
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_broadcast_sessions(channel_id,started_at) VALUES(?,?)',(self.channel,'current'))
   for i in range(7):
    ident=secrets.token_hex(16)
    conn.execute("INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,'member',?)",(ident,'guest'+str(i),'not-a-login',m.stamp(m.now_utc())))
  for i in range(6):self.assertEqual(self.admin.post('/api/streamers/me/guests',json={'username':'guest'+str(i)}).status_code,200)
  self.assertEqual(self.admin.post('/api/streamers/me/guests',json={'username':'guest6'}).status_code,409)
