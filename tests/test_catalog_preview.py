"""Free catalogue/playback and premium-only live video are separate."""
import unittest
from unittest.mock import patch
import app
from auth_support import authenticated_client

class PreviewTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup);self.guest=app.app.test_client()
  self.sample={'id':'audius_test','title':'Test song','channel':'Test artist','source':'AUDIUS','thumbnail':'https://example.org/art.png','stream_url':'https://api.audius.co/v1/tracks/test/stream','url':'https://audius.co','internal_audio':'must-not-leak'}
 @patch.object(app,'multi_search')
 def test_guests_receive_free_playable_metadata_without_internal_fields(self,search):
  search.return_value=[self.sample]
  for path in ['/api/search?q=test','/api/trending']:
   result=self.guest.get(path);self.assertEqual(result.status_code,200);self.assertFalse(result.json[0]['locked']);self.assertIn('stream_url',result.json[0]);self.assertNotIn('internal_audio',result.json[0])
  self.assertEqual(self.guest.get('/api/resolve/audius_test').status_code,200)
  self.assertEqual(self.guest.get('/api/streamers').status_code,401)
 @patch.object(app,'multi_search')
 def test_free_registration_needs_no_payment_for_music(self,search):
  search.return_value=[self.sample];csrf=self.guest.get('/api/account/me').json['csrf']
  self.guest.post('/api/account/register',json=__import__('registration_support').registration_data(self.guest,{'username':'free-user','password':'preview-password-123'}),headers={'X-CSRF-Token':csrf})
  self.assertFalse(self.guest.get('/api/search?q=test').json[0]['locked'])
  self.assertEqual(self.guest.get('/api/resolve/audius_test').status_code,200)
  self.assertEqual(self.guest.post('/api/streamers/me',json={'title':'No autorizado'},headers={'X-CSRF-Token':self.guest.get('/api/account/me').json['csrf']}).status_code,402)
 @patch.object(app,'multi_search')
 def test_admin_and_guest_use_the_same_music_catalogue(self,search):
  search.return_value=[self.sample]
  self.assertEqual(self.admin.get('/api/search?q=test').json,self.guest.get('/api/search?q=test').json)
