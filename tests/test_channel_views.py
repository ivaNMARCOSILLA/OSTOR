import unittest
from unittest.mock import patch
from datetime import timedelta
import app,membership as m,streamers as st
from auth_support import authenticated_client

class ChannelViewsTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.admin.post('/api/streamers/me',json={'title':'Canal popular'})
  self.channel=self.admin.get('/api/streamers').json['mine']['id']
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(minutes=5)),self.channel))
  self.viewer=app.app.test_client();csrf=self.viewer.get('/api/account/me').json['csrf']
  from registration_support import registration_data
  self.viewer.post('/api/account/register',json=registration_data(self.viewer,{'username':'real-viewer','password':'real-viewer-password-123'}),headers={'X-CSRF-Token':csrf});self.csrf=self.viewer.get('/api/account/me').json['csrf']
 def test_only_confirmed_viewer_counts_once_per_day(self):
  path='/api/streamers/'+self.channel+'/view'
  with patch.object(st,'live_ready',return_value=True),patch.object(st,'viewer_connected',return_value=False):
   self.assertEqual(self.viewer.post(path,json={},headers={'X-CSRF-Token':self.csrf}).status_code,202)
  with patch.object(st,'live_ready',return_value=True),patch.object(st,'viewer_connected',return_value=True) as verified:
   self.assertTrue(self.viewer.post(path,json={},headers={'X-CSRF-Token':self.csrf}).json['recorded'])
   self.assertFalse(self.viewer.post(path,json={},headers={'X-CSRF-Token':self.csrf}).json['recorded']);self.assertEqual(verified.call_count,1)
  data=app.app.test_client().get('/api/live/catalogue').json
  self.assertEqual(data['channels'][0]['view_count'],1)
  self.assertNotIn('member_id',data['channels'][0])
