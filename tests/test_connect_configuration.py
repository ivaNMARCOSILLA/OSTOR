import unittest
from unittest.mock import patch
import payments

class ConnectConfigurationTests(unittest.TestCase):
 def test_valid_credentials_ignore_surrounding_whitespace(self):
  with patch.dict('os.environ',{'VERCEL_ENV':'production','STRIPE_CONNECT_CLIENT_ID':' ca_fixture\n','STRIPE_SECRET_KEY':' sk_live_fixture\n'},clear=True):
   self.assertIsNone(payments.connect_configuration_error())
 def test_precise_safe_configuration_errors(self):
  for key,client,expected in [('', 'ca_fixture','Falta STRIPE_SECRET_KEY'),('sk_test_private','ca_fixture','pruebas'),('rk_live_private','ca_fixture','restringida'),('sk_live_private','','Falta STRIPE_CONNECT_CLIENT_ID'),('sk_live_private','pk_live_private','ID de cliente OAuth')]:
   with self.subTest(expected=expected),patch.dict('os.environ',{'VERCEL_ENV':'production','STRIPE_CONNECT_CLIENT_ID':client,'STRIPE_SECRET_KEY':key},clear=True):
    message=payments.connect_configuration_error()
    self.assertIn(expected,message)
    self.assertNotIn('private',message)
