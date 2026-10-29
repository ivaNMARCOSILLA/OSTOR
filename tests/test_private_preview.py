"""Free test accounts can publish/watch privately while the public premiere and billing stay closed."""
import base64,json
from unittest.mock import patch
import test_full_service_access as full
import app,membership as m

class PrivatePreviewTests(full.FullServiceTests):
 def setUp(self):
  super().setUp()
  import streamers
  with app.app.app_context():streamers.init_database()
 def test_two_accounts_publish_and_watch_without_public_launch(self):
  first=self.member('prueba');second=self.member('prueba2');other=self.member('ordinary-user');self.migration()
  with patch.dict('os.environ',{'OL_LIVE_PREMIERE':'1','LIVEKIT_URL':'wss://preview.invalid','LIVEKIT_API_KEY':'local_key','LIVEKIT_API_SECRET':'x'*40,'MAGGY_STREAMERS_ENABLED':'1','OL_PAYMENTS_ENABLED':'0'}):
   self.assertEqual(first.get('/api/streamers').status_code,200)
   self.assertIn(other.get('/api/streamers').status_code,(402,409))
   created=self.post(first,'/api/streamers/me',{'title':'Dos dispositivos','category':'entretenimiento'});self.assertEqual(created.status_code,200);channel=created.json['channel']['id']
   publisher=self.post(first,'/api/streamers/'+channel+'/token',{'publish':True})
   with patch('live_access.verified_broadcast',return_value=True):self.assertEqual(self.post(first,'/api/streamers/me/live',{'live':True}).status_code,200)
   viewer=self.post(second,'/api/streamers/'+channel+'/token',{'publish':False})
   self.assertEqual(publisher.status_code,200);self.assertEqual(viewer.status_code,200)
   def claims(response):
    data=response.json['token'].split('.')[1];return json.loads(base64.urlsafe_b64decode(data+'='*(-len(data)%4)))
   self.assertTrue(claims(publisher)['video']['canPublish']);self.assertFalse(claims(viewer)['video']['canPublish']);self.assertEqual(claims(publisher)['video']['room'],claims(viewer)['video']['room'])
   self.assertEqual(self.post(second,'/api/streamers/'+channel+'/token',{'publish':True}).status_code,403)
   self.assertEqual(len(second.get('/api/live/catalogue').json['channels']),1)
   public=app.app.test_client().get('/api/live/catalogue').json;self.assertEqual(public['channels'],[]);self.assertTrue(public['premiere'])
   self.assertFalse(first.get('/api/payments/status').json['enabled'])
 def test_private_permission_does_not_bypass_missing_video_configuration(self):
  c=self.member('prueba');self.migration()
  with patch.dict('os.environ',{'OL_LIVE_PREMIERE':'1','MAGGY_STREAMERS_ENABLED':'0'}):
   channel=self.post(c,'/api/streamers/me',{'title':'Private setup'}).json['channel']['id']
   self.assertEqual(self.post(c,'/api/streamers/'+channel+'/token',{'publish':True}).status_code,503)
