import unittest
from unittest.mock import patch
import app
from auth_support import authenticated_client


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.admin=authenticated_client(app.app,self.addCleanup)
        self.guest=app.app.test_client()
        self.sample={'id':'archive_test','title':'Test song','channel':'Test artist','source':'ARCHIVE','thumbnail':'https://archive.org/services/img/test','stream_url':'https://archive.org/download/test/audio.mp3','url':'https://archive.org/details/test','internal_audio':'must-not-leak'}

    @patch.object(app,'multi_search')
    def test_guest_can_view_but_receives_only_safe_metadata(self,search):
        search.return_value=[self.sample]
        with self.guest.get('/') as response:self.assertEqual(response.status_code,200)
        for path in ['/api/search?q=test','/api/trending']:
            result=self.guest.get(path)
            self.assertEqual(result.status_code,200)
            self.assertEqual(set(result.json[0]),{'id','title','channel','source','thumbnail','locked'})
            self.assertTrue(result.json[0]['locked'])
            self.assertEqual(result.headers['Cache-Control'],'no-store')
        self.assertEqual(self.guest.get('/api/resolve/archive_test').status_code,401)
        self.assertEqual(self.guest.get('/api/resolve/audius_test').status_code,401)

    @patch.object(app,'multi_search')
    def test_unpaid_account_cannot_unlock_by_registering(self,search):
        search.return_value=[self.sample]
        csrf=self.guest.get('/api/account/me').json['csrf']
        self.guest.post('/api/account/register',json={'username':'preview-user','password':'preview-password-123'},headers={'X-CSRF-Token':csrf})
        self.assertNotIn('stream_url',self.guest.get('/api/search?q=test').json[0])
        self.assertEqual(self.guest.get('/api/resolve/archive_test').status_code,402)
        self.assertEqual(self.guest.get('/api/proxy?url=https://archive.org/audio.mp3').status_code,402)

    @patch.object(app,'multi_search')
    def test_authorized_member_gets_full_metadata_and_audio_resolution(self,search):
        search.return_value=[self.sample]
        self.assertEqual(self.admin.get('/api/search?q=test').json[0]['stream_url'],self.sample['stream_url'])
        result=self.admin.get('/api/resolve/audius_test')
        self.assertEqual(result.status_code,200)
        self.assertIn('/tracks/test/stream',result.json['stream_url'])
