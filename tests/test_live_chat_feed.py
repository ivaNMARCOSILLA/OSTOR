"""Bounded incremental live chat, private audiences and moderation under backlog."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import app,community,membership as m
from auth_support import authenticated_client

class ChatFeedTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():
   import streamers
   streamers.init_database();community.init_database()
  self.admin.post('/api/streamers/me',json={'title':'Chat de prueba'})
  self.channel=self.admin.get('/api/streamers').json['mine']['id'];self.member=self.admin.get('/api/account/me').json['user']['id']
  with app.app.app_context(),m.database() as conn:
   conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(hours=1)),self.channel))
 def test_large_backlog_is_bounded_then_only_new_messages(self):
  instant=m.stamp(m.now_utc()-timedelta(minutes=2))
  with app.app.app_context(),m.database() as conn:
   for i in range(3000):conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,created_at) VALUES(?,?,?,?,?,?)',(format(i,'032x'),self.channel,self.member,'comment','Mensaje '+str(i),instant))
  path='/api/streamers/'+self.channel+'/comments';first=self.admin.get(path).json
  self.assertEqual(len(first['comments']),100);self.assertTrue(first['truncated'])
  self.assertEqual(first['comments'][-1]['body'],'Mensaje 2999')
  second=self.admin.get(path,query_string={'after':first['cursor']}).json;self.assertEqual(second['comments'],[])
  self.admin.post(path,json={'kind':'comment','text':'Nuevo comentario'})
  third=self.admin.get(path,query_string={'after':first['cursor']}).json
  self.assertEqual(len(third['comments']),1);self.assertEqual(third['comments'][0]['body'],'Nuevo comentario')
  self.assertEqual(self.admin.get(path,query_string={'after':'invalid'}).status_code,400)
 def test_blocked_and_private_messages_never_reach_free_viewers(self):
  guest=app.app.test_client();csrf=guest.get('/api/account/me').json['csrf']
  from registration_support import registration_data
  guest.post('/api/account/register',json=registration_data(guest,{'username':'chat-viewer','password':'chat-viewer-password-123'}),headers={'X-CSRF-Token':csrf})
  path='/api/streamers/'+self.channel+'/comments'
  with app.app.app_context(),m.database() as conn:
   for i,blocked in [(1,0),(2,1)]:conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,blocked,created_at) VALUES(?,?,?,?,?,?,?)',(format(i,'032x'),self.channel,self.member,'comment','Privado',blocked,m.stamp(m.now_utc())))
   conn.execute('INSERT INTO community_audiences VALUES(?,?)',(format(1,'032x'),'subscribers'))
  self.assertEqual(guest.get(path).json['comments'],[])
  csrf=guest.get('/api/account/me').json['csrf']
  with patch('community.classify',return_value='insult'),patch('community.notify'):
   result=guest.post(path,json={'kind':'comment','text':'Mensaje moderado'},headers={'X-CSRF-Token':csrf})
  self.assertEqual(result.status_code,200);self.assertTrue(result.json['blocked']);self.assertEqual(guest.get(path).json['comments'],[])
