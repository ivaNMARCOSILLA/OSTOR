import unittest
from unittest.mock import patch
import app
from auth_support import authenticated_client


class MaggyTests(unittest.TestCase):
    def setUp(self):
        self.client=authenticated_client(app.app,self.addCleanup)

    def test_retired_provider_endpoints_are_absent(self):
        self.assertEqual(self.client.get('/api/youtube-link?url=https://youtu.be/abcdefghijk').status_code,404)
        self.assertEqual(self.client.post('/api/youtube-availability',json={'ids':['abcdefghijk']}).status_code,404)
        self.assertEqual(self.client.get('/assets/youtube-availability.js').status_code,404)

    @patch.object(app,'search_archive',return_value=[{'id':'archive_one','title':'Orbit','source':'ARCHIVE'}])
    @patch.object(app,'search_audius',return_value=[{'id':'audius_one','title':'Orbit','source':'AUDIUS'}])
    def test_combined_search_uses_only_audio_providers(self,audius,archive):
        app._search_cache.clear()
        response=self.client.get('/api/search?q=Orbit')
        self.assertEqual(response.status_code,200)
        self.assertEqual({item['source'] for item in response.json},{'ARCHIVE','AUDIUS'})
        audius.assert_called_once();archive.assert_called_once()

    def test_pwa_assets_and_provider_metadata(self):
        for path in ['/','/manifest.webmanifest','/sw.js','/assets/maggy.js']:
            with self.client.get(path) as response:self.assertEqual(response.status_code,200)
        data=self.client.get('/health').json
        self.assertEqual(data['version'],'9.4.0')
        self.assertEqual(data['providers'],['ARCHIVE','AUDIUS','COMMONS','RADIO'])
