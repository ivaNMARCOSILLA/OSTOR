"""Locale reads only a trusted country hint or necessary language preference."""
import unittest
from unittest.mock import patch
import app

class LocalePreferenceTests(unittest.TestCase):
 def setUp(self):self.client=app.app.test_client()
 def test_untrusted_country_is_ignored_and_browser_fallback_used(self):
  with patch.dict('os.environ',{'VERCEL':'0'}):
   response=self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'DE','Accept-Language':'fr-FR,es;q=.5'})
  self.assertEqual(response.status_code,200);self.assertEqual(response.json['language'],'fr');self.assertEqual(response.json['source'],'browser')
  self.assertIn('no-store',response.headers['Cache-Control']);self.assertNotIn('Set-Cookie',response.headers)
 def test_trusted_country_multilingual_preference_and_saved_choice(self):
  with patch.dict('os.environ',{'VERCEL':'1'}):
   self.assertEqual(self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'DE','Accept-Language':'es'}).json['language'],'de')
   self.assertEqual(self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'CA','Accept-Language':'fr-CA,en;q=.5'}).json['language'],'fr')
   self.assertEqual(self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'ES','Accept-Language':'ca-ES'}).json['language'],'ca')
   self.client.set_cookie('electronicama_language','it')
   response=self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'DE','Accept-Language':'fr'})
   self.assertEqual((response.json['language'],response.json['source']),('it','saved'))
 def test_invalid_hints_and_unsupported_browser_use_safe_fallback(self):
  self.client.set_cookie('electronicama_language','<script>')
  with patch.dict('os.environ',{'VERCEL':'1'}):
   result=self.client.get('/api/locale',headers={'X-Vercel-IP-Country':'FR,US','Accept-Language':'ja-JP'}).json
  self.assertEqual(result['language'],'es');self.assertEqual(result['source'],'default');self.assertEqual(set(result),{'language','source','supported'})
  result=self.client.get('/api/locale',headers={'Accept-Language':'de;q=0,en;q=1'}).json
  self.assertEqual(result['language'],'en')
