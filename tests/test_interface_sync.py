import unittest
import app,streamers as st
from auth_support import authenticated_client

class InterfaceSyncTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
 def test_other_device_observes_channel_edits_without_private_data(self):
  guest=app.app.test_client();before=guest.get('/api/sync')
  self.assertEqual(before.status_code,200);self.assertNotIn('account',before.json)
  self.assertEqual(before.headers['Cache-Control'],'no-store')
  self.admin.post('/api/streamers/me',json={'title':'Canal sincronizado'})
  after=guest.get('/api/sync').json;self.assertNotEqual(before.json['public'],after['public'])
  self.assertEqual(set(after),{'public'})
  stable=guest.get('/api/sync').json;self.assertEqual(after,stable)
 def test_failed_writes_do_not_publish_changes(self):
  before=self.admin.get('/api/sync').json
  self.admin.post('/api/streamers/me',json={'title':'x'})
  self.assertEqual(before,self.admin.get('/api/sync').json)
