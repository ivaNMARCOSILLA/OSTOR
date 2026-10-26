import unittest
from unittest.mock import patch
import app,streamers
from auth_support import authenticated_client

class LaunchReadinessTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():streamers.init_database()
 def test_admin_only_safe_configuration_report_does_not_enable_anything(self):
  self.assertEqual(app.app.test_client().get('/api/admin/launch-readiness').status_code,403)
  env={'LIVEKIT_URL':'','LIVEKIT_API_KEY':'','LIVEKIT_API_SECRET':'','MAGGY_STREAMERS_ENABLED':'0','STRIPE_SECRET_KEY':'','STRIPE_WEBHOOK_SECRET':'','STRIPE_CONNECT_CLIENT_ID':'','STRIPE_CONNECT_WEBHOOK_SECRET':'','MAGGY_STREAMER_SALES_ENABLED':'0','OL_PAYMENTS_ENABLED':'0'}
  with patch.dict('os.environ',env):
   result=self.admin.get('/api/admin/launch-readiness');self.assertEqual(result.status_code,200)
   self.assertTrue(result.json['configuration_only']);self.assertFalse(result.json['live_payments_enabled']);self.assertFalse(result.json['video_configuration_complete']);self.assertFalse(result.json['packaging']['play_publication_verified'])
 def test_probe_names_production_without_exposing_credentials(self):
  with patch.dict('os.environ',{'VERCEL_ENV':'production','LIVEKIT_URL':'','LIVEKIT_API_KEY':'','LIVEKIT_API_SECRET':'','MAGGY_STREAMERS_ENABLED':'0'}):
   r=self.admin.post('/api/streamers/admin/check-video',json={});self.assertEqual(r.status_code,409);self.assertIn('Production',r.json['message']);self.assertNotIn('Preview',r.json['message'])
 def test_fondos_web_is_an_editorial_label_with_no_transaction_controls(self):
  r=app.app.test_client().get('/live');self.assertEqual(r.status_code,200)
  s=r.get_data(as_text=True);i=s.index('class="web-funds-note"');fragment=s[i:s.index('</aside>',i)]
  self.assertIn('Fondos Web',fragment);self.assertIn('etiqueta editorial',fragment)
  self.assertNotIn('<button',fragment);self.assertNotIn('<form',fragment)
