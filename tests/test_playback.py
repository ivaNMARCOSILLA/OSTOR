"""Provider compatibility and paid, low-latency native media redirects."""
import unittest
from unittest.mock import patch, Mock
import app
from auth_support import authenticated_client


class PlaybackTests(unittest.TestCase):
    def setUp(self):
        self.client = authenticated_client(app.app, self.addCleanup)
        app._archive_cache.clear()
        app._search_cache.clear()

    @patch.object(app,'relay_audio')
    def test_media_playback_is_free_without_a_subscription(self,relay):
        relay.return_value=app.Response(b'free-audio',mimetype='audio/mpeg')
        guest=app.app.test_client()
        self.assertEqual(guest.get('/api/play/audius_test').status_code,200)
        csrf=guest.get('/api/account/me').json['csrf']
        guest.post('/api/account/register',json={'username':'audio-free','password':'password-test-123'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(guest.get('/api/play/audius_test').status_code,200)
        self.assertEqual(guest.get('/api/streamers').status_code,402)

    @patch.object(app, '_safe_upstream')
    def test_audius_relay_preserves_range_and_checks_fixed_origins(self, fetch):
        upstream = Mock(status_code=206, headers={'Content-Type':'audio/mpeg','Content-Length':'2','Content-Range':'bytes 0-1/1000000','Accept-Ranges':'bytes'})
        upstream.iter_content.return_value = iter([b'ab'])
        fetch.return_value = upstream
        response = self.client.get('/api/play/audius_test', headers={'Range':'bytes=0-1'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b'ab')
        self.assertEqual(response.headers['Content-Range'], 'bytes 0-1/1000000')
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertTrue(fetch.call_args.args[0].startswith('https://api.audius.co/v1/tracks/test/stream?'))
        self.assertEqual(fetch.call_args.args[1]['Range'], 'bytes=0-1')
        self.assertEqual(self.client.get('/api/play/audius_https://evil.test').status_code, 400)

    @patch.object(app, '_safe_upstream')
    def test_audius_relay_caps_large_requests_and_uses_alternate_provider(self, fetch):
        fetch.return_value = Mock(status_code=502, headers={})
        self.assertEqual(self.client.get('/api/play/audius_test?retry=1',headers={'Range':'bytes=100-'}).status_code,502)
        self.assertIn('https://discoveryprovider2.audius.co/', fetch.call_args.args[0])
        self.assertEqual(fetch.call_args.args[1]['Range'], f'bytes=100-{100+app.AUDIO_CHUNK_BYTES-1}')
        self.assertEqual(self.client.get('/api/play/audius_test',headers={'Range':'bytes=2-1'}).status_code,416)

    def test_diagnostic_is_not_public_and_storage_allowlist_is_exact(self):
        self.assertEqual(app.app.test_client().get('/api/admin/audio-diagnostic/test').status_code,403)
        self.assertTrue(app.allowed_stream_url('https://'+app.AUDIUS_STORAGE_HOST+'/audio'))
        self.assertFalse(app.allowed_stream_url('https://'+app.AUDIUS_STORAGE_HOST+'.evil.test/audio'))
        self.assertFalse(app.allowed_stream_url('https://other.r2.cloudflarestorage.com/audio'))

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
