"""Provider compatibility and paid, low-latency native media redirects."""
import unittest
from unittest.mock import patch
import app
from auth_support import authenticated_client


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.client = authenticated_client(app.app, self.addCleanup)
        app._archive_cache.clear()
        app._search_cache.clear()

    def test_media_redirect_requires_paid_access(self):
        guest = app.app.test_client()
        self.assertEqual(guest.get('/api/play/audius_test').status_code, 401)
        csrf = guest.get('/api/account/me').json['csrf']
        guest.post('/api/account/register', json={'username':'no-audio-plan','password':'password-test-123'}, headers={'X-CSRF-Token':csrf})
        self.assertEqual(guest.get('/api/play/archive_test').status_code, 402)

    def test_audius_native_redirect_and_retry_use_fixed_origins(self):
        response = self.client.get('/api/play/audius_test', headers={'Range':'bytes=0-1023'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.startswith('https://api.audius.co/v1/tracks/test/stream?'))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('https://discoveryprovider2.audius.co/', self.client.get('/api/play/audius_test?retry=1').location)
        self.assertEqual(self.client.get('/api/play/audius_https://evil.test').status_code, 400)

    @patch.object(app, 'fetch_json')
    def test_archive_prefers_mp3_over_largest_ogg_and_ignores_private(self, fetch):
        fetch.return_value = {'files':[{'name':'big.ogg','size':'99999999'}, {'name':'hidden.mp3','private':'true'}, {'name':'track.m4a'}, {'name':'track.mp3','size':'1000'}]}
        response = self.client.get('/api/play/archive_album')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, 'https://archive.org/download/album/track.mp3')
        self.client.get('/api/play/archive_album')
        self.assertEqual(fetch.call_count, 1)

    @patch.object(app, 'fetch_json')
    def test_archive_restricted_items_never_redirect(self, fetch):
        fetch.return_value = {'metadata':{'access-restricted-item':'true'},'files':[{'name':'track.mp3'}]}
        self.assertEqual(self.client.get('/api/play/archive_locked').status_code, 404)

    @patch.object(app, 'fetch_json')
    def test_archive_search_is_one_request_without_per_item_resolution(self, fetch):
        fetch.return_value = {'response':{'docs':[{'identifier':'ambient_one','title':'Ambient One'}, {'identifier':'ambient_locked','title':'Ambient Two','access-restricted-item':'true'}]}}
        result = app.search_archive('ambient')
        self.assertEqual([x['id'] for x in result], ['archive_ambient_one'])
        self.assertEqual(fetch.call_count, 1)
        self.assertIn('NOT access-restricted-item:true', fetch.call_args.args[1]['q'])

    @patch.object(app, 'fetch_json')
    def test_audius_filters_tracks_requiring_external_access(self, fetch):
        fetch.return_value = {'data':[{'id':'open','title':'Ambient'}, {'id':'premium','is_stream_gated':True}, {'id':'blocked','is_streamable':False}, {'id':'gone','is_available':False}, {'id':'denied','access':{'stream':False}}]}
        self.assertEqual([x['id'] for x in app.search_audius('ambient')], ['audius_open'])

    @patch.object(app, 'search_audius', return_value=[{'id':'audius_one','title':'Ambient','source':'AUDIUS'}])
    @patch.object(app, 'search_archive')
    def test_provider_search_does_not_wait_for_other_provider(self, archive, audius):
        result = self.client.get('/api/search?q=ambient&source=AUDIUS')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json), 1)
        archive.assert_not_called()
        self.assertEqual(self.client.get('/api/search?q=ambient&source=unknown').status_code, 400)
