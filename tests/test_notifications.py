import os
import unittest
from unittest.mock import patch
import app
import notifications as n
from auth_support import authenticated_client

class NotificationTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  self.env=patch.dict(os.environ,{'OL_EMAIL_FROM':'','RESEND_API_KEY':'','SMTP_HOST':'','SMTP_USER':'','SMTP_PASSWORD':''})
  self.env.start();self.addCleanup(self.env.stop)
 def test_unconfigured_email_is_queued_without_claiming_delivery(self):
  with app.app.app_context():n.notify('test','Aviso de prueba','Resumen sin secretos',event_key='notice-test')
  result=self.admin.get('/api/admin/notifications').json
  self.assertFalse(result['email_ready']);self.assertEqual(result['pending'],1)
  self.assertEqual(result['recipient'],'normalesoutro@gmail.com')
  self.assertEqual(result['notifications'][0]['status'],'pending')
  self.assertEqual(app.app.test_client().get('/api/admin/notifications').status_code,403)
 def test_deduplication_and_delivery_failure_preserve_pending_notice(self):
  with patch.dict(os.environ,{'OL_EMAIL_FROM':'Ol <test@example.org>','RESEND_API_KEY':'test-key'}),patch.object(n,'deliver',side_effect=RuntimeError('private provider detail')) as deliver:
   with app.app.app_context():
    n.notify('test','Aviso','Resumen',event_key='notice-dedupe')
    n.notify('test','Aviso','Resumen',event_key='notice-dedupe')
   self.assertEqual(deliver.call_count,1)
   result=self.admin.get('/api/admin/notifications').json
   self.assertEqual(result['total'],1);self.assertEqual(result['notifications'][0]['status'],'failed')
   self.assertNotIn('private provider detail',str(result))
