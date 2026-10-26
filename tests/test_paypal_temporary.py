"""Temporary PayPal must never accidentally submit retained Stripe credentials."""
import unittest
from unittest.mock import patch
import app,streamers
from auth_support import authenticated_client

class TemporaryPayPalTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():streamers.init_database()
 def test_production_never_reactivates_legacy_external_payments(self):
  with patch.dict('os.environ',{'VERCEL_ENV':'production','OL_PAYMENT_PROVIDER':'legacy_paypal','OL_LIVE_PREMIERE':'1'}),patch('payments.stripe') as stripe:
   status=self.admin.get('/api/payments/status').json
   self.assertEqual(status['provider'],'stripe');self.assertFalse(status['enabled'])
   self.assertEqual(self.admin.post('/api/payments/checkout',json={}).status_code,409)
   self.assertEqual(self.admin.post('/api/streamers/any/gift-link',json={'amount_cents':2500}).status_code,410)
   self.assertEqual(self.admin.post('/api/admin/confirm-payment',json={}).status_code,409)
   stripe.assert_not_called()
 def test_manual_payment_cannot_bypass_video_or_maintenance_gate(self):
  with patch('streamers.streamer_sales_ready',return_value=False):
   result=self.admin.post('/api/admin/confirm-payment',json={'plan':'lifetime','reference':'COMPLETED-REFERENCE','member_id':'none'})
   self.assertEqual(result.status_code,409)
  with patch('streamers.streamer_sales_ready',return_value=True),patch('operations.state',return_value={'scope':'payments'}):
   result=self.admin.post('/api/admin/confirm-payment',json={'plan':'lifetime','reference':'COMPLETED-REFERENCE','member_id':'none'})
   self.assertEqual(result.status_code,409)
 def test_premiere_hides_public_channels_and_blocks_trials_without_losing_admin_tools(self):
  with patch.dict('os.environ',{'OL_LIVE_PREMIERE':'1'}),patch('streamers.streamer_sales_ready',return_value=True):
   public=app.app.test_client()
   self.assertTrue(public.get('/api/status').json['live_premiere'])
   catalogue=public.get('/api/live/catalogue').json
   self.assertEqual(catalogue['channels'],[]);self.assertFalse(catalogue['video_ready'])
   self.assertIn(public.get('/api/streamers').status_code,(401,409))
   self.assertEqual(self.admin.post('/api/account/live-trial',json={}).status_code,409)
   self.assertEqual(self.admin.post('/api/live/founders/claim',json={}).status_code,409)
   self.assertFalse(self.admin.get('/api/payments/status').json['enabled'])
   self.assertEqual(self.admin.get('/api/streamers').status_code,200)
