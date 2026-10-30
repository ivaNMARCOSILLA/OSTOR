"""Browser code restrictions preserve explicitly chosen media and safe navigation."""
import base64,hashlib,re,unittest
from pathlib import Path
import app
from auth_support import authenticated_client

class SecurityHeaderTests(unittest.TestCase):
 def setUp(self):self.client=authenticated_client(app.app,self.addCleanup)
 def test_reviewed_scripts_only_no_inline_handlers_or_active_objects(self):
  response=self.client.get('/');policy=response.headers['Content-Security-Policy']
  directives=dict(part.strip().split(' ',1) for part in policy.split(';'))
  self.assertIn("'self'",directives['script-src']);self.assertIn('https://www.youtube.com',directives['script-src'])
  self.assertIn('https://s.ytimg.com',directives['script-src']);self.assertIn("'wasm-unsafe-eval'",directives['script-src'])
  self.assertNotIn("'unsafe-inline'",policy);self.assertNotIn("'unsafe-eval'",policy)
  self.assertEqual(directives['script-src-attr'],"'none'");self.assertEqual(directives['object-src'],"'none'")
  self.assertEqual(directives['base-uri'],"'self'");self.assertEqual(directives['form-action'],"'self'")
  self.assertEqual(directives['frame-ancestors'],"'self'")
  self.assertNotIn('connect-src',directives);self.assertNotIn('media-src',directives)
 def test_only_static_jsonld_inline_hash_is_permitted(self):
  policy=self.client.get('/').headers['Content-Security-Policy']
  source=Path(app.ROOT,'index.html').read_text()
  bodies=re.findall(r'<script\b[^>]*type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script\s*>',source,re.S|re.I)
  self.assertTrue(bodies)
  for body in bodies:
   digest=base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
   self.assertIn("'sha256-"+digest+"'",policy)
 def test_headers_cover_auth_api_live_and_legal_without_removing_permissions(self):
  for path in ['/account','/api/account/me','/live','/legal/privacidad.html']:
   response=self.client.get(path)
   self.assertIn('Content-Security-Policy',response.headers)
   self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
  self.assertIn('camera=(self)',self.client.get('/live').headers['Permissions-Policy'])
  self.assertIn('microphone=(self)',self.client.get('/live').headers['Permissions-Policy'])
