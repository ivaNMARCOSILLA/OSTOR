import os,unittest,hashlib
from unittest.mock import patch,Mock
import app,membership as m,sounds
from auth_support import authenticated_client
from sticker_phrases import phrase_for

class NeuralStickerVoicesTests(unittest.TestCase):
 def setUp(self):
  self.client=authenticated_client(app.app,self.addCleanup)
  import streamers
  with app.app.app_context():streamers.init_database()
  self.env=patch.dict(os.environ,{'OL_STICKER_VOICE_PROVIDER':'azure','OL_STICKER_NEURAL_VOICES':'1','OL_AZURE_SPEECH_KEY':'local-test-secret','OL_AZURE_SPEECH_REGION':'westeurope'});self.env.start();self.addCleanup(self.env.stop)
 def post(self,data=None,ident='hello',client=None):
  client=client or self.client;csrf=client.get('/api/account/me').json['csrf']
  return client.post('/api/stickers/'+ident+'/voice',json=data or {'voice':'female'},headers={'X-CSRF-Token':csrf})
 def provider(self):return Mock(status_code=200,content=b'ID3-local-fixture',headers={'Content-Type':'audio/mpeg'})
 def test_disabled_service_never_calls_provider(self):
  with patch.dict(os.environ,{'OL_STICKER_NEURAL_VOICES':'0'}),patch('requests.post') as request:
   self.assertFalse(self.client.get('/api/stickers/voices').json['neural_available'])
   response=self.post();self.assertEqual(response.status_code,409);request.assert_not_called()
 def test_two_neural_voices_reuse_cached_audio_and_ignore_arbitrary_text(self):
  with patch('requests.post',return_value=self.provider()) as request:
   for voice,name in [('female','ElviraNeural'),('male','AlvaroNeural')]:
    response=self.post({'voice':voice,'text':'this must never be sent'})
    self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,'audio/mpeg')
    ssml=request.call_args.kwargs['data'].decode();self.assertIn(name,ssml);self.assertNotIn('this must never',ssml)
    self.assertEqual(self.post({'voice':voice}).data,response.data)
   self.assertEqual(request.call_count,2)
 def test_elevenlabs_uses_selected_voice_and_fixed_sticker_phrase(self):
  with patch.dict(os.environ,{'OL_STICKER_VOICE_PROVIDER':'elevenlabs','OL_ELEVENLABS_API_KEY':'local-key','OL_ELEVENLABS_FEMALE_VOICE_ID':'voiceFemale','OL_ELEVENLABS_MALE_VOICE_ID':'voiceMale'}),patch('requests.post',return_value=self.provider()) as request:
   self.assertTrue(self.client.get('/api/stickers/voices').json['neural_available'])
   self.assertEqual(self.post({'voice':'male'}).status_code,200)
   self.assertEqual(request.call_args.args[0],'https://api.elevenlabs.io/v1/text-to-speech/voiceMale')
   self.assertEqual(request.call_args.kwargs['json']['text'],phrase_for('hello'))
   self.assertEqual(request.call_args.kwargs['json']['model_id'],'eleven_multilingual_v2')
 def test_auth_csrf_and_voice_choices_are_enforced(self):
  guest=app.app.test_client();self.assertEqual(self.post(client=guest).status_code,401)
  self.assertEqual(self.client.open('/api/stickers/hello/voice',method='POST',json={'voice':'female'}).status_code,403)
  self.assertEqual(self.post({'voice':'arbitrary-voice'}).status_code,400)
  self.assertEqual(self.post({'voice':[]}).status_code,400)
  self.assertEqual(self.post(ident='missing-sticker').status_code,404)
 def test_failure_removes_generation_claim_and_can_retry(self):
  with patch('requests.post',return_value=Mock(status_code=503,content=b'')):
   self.assertEqual(self.post().status_code,503)
  with app.app.app_context(),m.database() as c:self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM sticker_voice_audio').fetchone()['n'],0)
  with patch('requests.post',return_value=self.provider()):self.assertEqual(self.post().status_code,200)
 def test_concurrent_generation_is_reported_pending_without_another_call(self):
  key=hashlib.sha256(('azure-v1:es-ES-ElviraNeural:'+phrase_for('hello')).encode()).hexdigest()
  with app.app.app_context(),m.database() as c:c.execute('INSERT INTO sticker_voice_audio(cache_key,created_at) VALUES(?,?)',(key,m.stamp(m.now_utc())))
  with patch('requests.post') as request:self.assertEqual(self.post().status_code,202);request.assert_not_called()
