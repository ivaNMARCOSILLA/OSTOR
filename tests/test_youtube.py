import unittest
from unittest.mock import Mock,patch
import app

class YouTubeTests(unittest.TestCase):
 def setUp(self):
  self.client=app.app.test_client();app._youtube_cache.clear();app._request_buckets.clear()
 def test_key_missing_has_actionable_error_and_no_provider_request(self):
  with patch.dict('os.environ',{'YOUTUBE_API_KEY':''}),patch.object(app.requests,'get') as get:
   r=self.client.get('/api/search?q=mozart&source=YOUTUBE');self.assertEqual(r.status_code,503);self.assertEqual(r.json['code'],'youtube_not_configured');get.assert_not_called()
 def test_embeddable_safe_music_search_private_key_pagination_and_cache(self):
  first=Mock(status_code=200);first.json.return_value={'items':[{'id':{'videoId':'abcdefghijk'},'snippet':{'title':'Piano &amp; light','channelTitle':'Artist'}},{'id':{'videoId':'bad'}}],'nextPageToken':'page-two'}
  second=Mock(status_code=200);second.json.return_value={'items':[{'id':{'videoId':'1234567890a'},'snippet':{'title':'Second'}}]}
  with patch.dict('os.environ',{'YOUTUBE_API_KEY':'test-private-server-key'}),patch.object(app.requests,'get',side_effect=[first,second]) as get:
   r=self.client.get('/api/search?q=piano&source=YOUTUBE');self.assertEqual(r.status_code,200);self.assertEqual(len(r.json),1);self.assertEqual(r.json[0]['video_id'],'abcdefghijk');self.assertEqual(r.json[0]['title'],'Piano & light');self.assertNotIn('test-private',r.get_data(as_text=True))
   params=get.call_args.kwargs['params'];self.assertEqual(params['videoEmbeddable'],'true');self.assertEqual(params['safeSearch'],'strict');self.assertEqual(params['maxResults'],50)
   self.client.get('/api/search?q=piano&source=YOUTUBE');self.assertEqual(get.call_count,1)
   r=self.client.get('/api/search?q=piano&source=YOUTUBE&page=2');self.assertEqual(r.json[0]['video_id'],'1234567890a');self.assertEqual(get.call_args.kwargs['params']['pageToken'],'page-two')
   self.assertEqual(self.client.get('/api/search?q=piano&source=YOUTUBE&page=3').json,[]);self.assertEqual(get.call_count,2)
 def test_quota_failure_does_not_leak_key_and_audio_extraction_is_absent(self):
  with patch.dict('os.environ',{'YOUTUBE_API_KEY':'test-private-server-key'}),patch.object(app.requests,'get',return_value=Mock(status_code=403)):
   r=self.client.get('/api/search?q=piano&source=YOUTUBE');self.assertEqual(r.status_code,503);self.assertEqual(r.json['code'],'youtube_access_or_quota');self.assertNotIn('test-private',r.get_data(as_text=True))
  self.assertEqual(self.client.get('/api/play/youtube_abcdefghijk').status_code,404)

 def test_diagnostic_requires_admin(self):
  self.assertEqual(self.client.get('/api/admin/youtube-diagnostic').status_code,403)

 def test_admin_diagnostic_checks_connection_without_returning_private_key(self):
  from auth_support import authenticated_client
  client=authenticated_client(app.app,self.addCleanup)
  response=Mock(status_code=200);response.json.return_value={'items':[]}
  with patch.dict('os.environ',{'YOUTUBE_API_KEY':'test-private-server-key'}),patch.object(app.requests,'get',return_value=response):
   result=client.get('/api/admin/youtube-diagnostic');self.assertEqual(result.status_code,200);self.assertTrue(result.json['connected']);self.assertNotIn('test-private',result.get_data(as_text=True))
