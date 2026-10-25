import unittest
from unittest.mock import patch, Mock
import app
from auth_support import authenticated_client

class FreeCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.client=authenticated_client(app.app,self.addCleanup)
        app._commons_cache.clear();app._radio_cache.clear();app._search_cache.clear()

    def test_commons_requires_free_license_and_audio_from_known_storage(self):
        page={'pageid':123,'title':'File:Piano.ogg','imageinfo':[{'url':'https://upload.wikimedia.org/wikipedia/commons/piano.ogg','mime':'audio/ogg','extmetadata':{'Artist':{'value':'<b>Composer</b>'},'LicenseShortName':{'value':'CC BY 4.0'},'LicenseUrl':{'value':'https://creativecommons.org/licenses/by/4.0/'}}}]}
        track=app.commons_track(page)
        self.assertEqual(track['source'],'COMMONS');self.assertEqual(track['attribution'],'Composer')
        upstream=Mock(status_code=206,headers={'Content-Type':'audio/ogg','Content-Length':'4','Content-Range':'bytes 0-3/10000'})
        upstream.iter_content.return_value=iter([b'OggS'])
        with patch.object(app,'_safe_upstream',return_value=upstream):
            response=self.client.get('/api/play/commons_123',headers={'Range':'bytes=0-3'})
            self.assertEqual(response.status_code,206);self.assertEqual(response.data,b'OggS')
        self.assertEqual(app.app.test_client().get('/api/play/commons_123').status_code,401)
        page['imageinfo'][0]['mime']='video/webm';self.assertIsNone(app.commons_track(page))
        page['imageinfo'][0]['mime']='audio/ogg';page['imageinfo'][0]['extmetadata']['LicenseShortName']['value']='All rights reserved'
        self.assertIsNone(app.commons_track(page))

    def test_radio_rejects_private_urls_broken_streams_and_video_codecs(self):
        station={'stationuuid':'12345678-1234-1234-1234-123456789abc','url_resolved':'https://radio.example.org/audio.mp3','codec':'MP3','lastcheckok':1,'name':'Piano radio'}
        track=app.radio_track(station);self.assertEqual(track['source'],'RADIO')
        self.assertEqual(self.client.get('/api/play/'+track['id']).location,station['url_resolved'])
        for url in ['http://radio.example.org/audio','https://127.0.0.1/audio','https://localhost/audio','https://radio.example.org/video.m3u8']:
            station['url_resolved']=url;self.assertIsNone(app.radio_track(station))

    @patch.object(app,'search_radio',return_value=[{'id':'radio_test','title':'Piano','source':'RADIO','stream_url':'secret'}])
    @patch.object(app,'search_commons',return_value=[{'id':'commons_1','title':'Piano','source':'COMMONS','license':'CC0','attribution':'Composer','stream_url':'secret'}])
    def test_mix_uses_other_sources_and_preview_preserves_credits_without_audio(self,commons,radio):
        response=app.app.test_client().get('/api/search?q=piano&source=MIX')
        self.assertEqual({x['source'] for x in response.json},{'COMMONS','RADIO'})
        self.assertTrue(all('stream_url' not in x for x in response.json))
        self.assertEqual(next(x for x in response.json if x['source']=='COMMONS')['attribution'],'Composer')
