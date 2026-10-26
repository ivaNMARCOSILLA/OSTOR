import io
import wave
import unittest
from datetime import timedelta
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import app
import membership as m
import streamers as st
from auth_support import authenticated_client

class OlLiveBusinessTests(unittest.TestCase):
 def setUp(self):
  code=patch("human_check.new_code",return_value="OL234");code.start();self.addCleanup(code.stop)
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
 def post(self,client,path,data):
  csrf=client.get('/api/account/me').json['csrf']
  if path=='/api/live/founders/claim':data=dict(data,human_id=client.get('/api/account/human-check').json['id'],human_answer='OL234')
  return client.post(path,json=data,headers={'X-CSRF-Token':csrf})
 def member(self,name):
  client=app.app.test_client();self.assertEqual(self.post(client,'/api/account/register',{'username':name,'password':'ol-live-user-password-123'}).status_code,201);return client
 def test_all_new_premium_billing_is_blocked_before_live_is_ready(self):
  client=self.member('premium-pending');ident=client.get('/api/account/me').json['user']['id']
  with patch.object(st,'streamer_sales_ready',return_value=False):
   for plan in ['lifetime']:
    self.assertEqual(self.post(self.admin,'/api/admin/confirm-payment',{'member_id':ident,'plan':plan,'reference':'PENDING-'+plan}).status_code,409)
  self.assertEqual(client.get('/api/account/me').json['payments'],[])
  self.assertEqual(client.get('/api/resolve/audius_test').status_code,200)
  self.assertEqual(client.get('/api/rewards').status_code,200)
 def test_last_founder_place_is_atomic_and_number_is_not_recycled(self):
  with app.app.app_context(),m.database() as conn:
   for number in range(1,100):
    ident='seed-founder-'+str(number);conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(m.now_utc())))
    conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(m.now_utc())))
  first=self.member('founder-last-a');second=self.member('founder-last-b')
  with ThreadPoolExecutor(max_workers=2) as pool:
   results=[pool.submit(self.post,client,'/api/live/founders/claim',{}) for client in [first,second]]
   responses=[future.result() for future in results]
  self.assertEqual(sorted(result.status_code for result in responses),[200,409])
  winner=first if responses[0].status_code==200 else second
  info=winner.get('/api/account/me').json
  self.assertTrue(info['user']['founder_active']);self.assertTrue(info['user']['streamer_active']);self.assertEqual(info['user']['founder_number'],100);self.assertEqual(info['payments'],[])
  self.assertEqual(self.post(winner,'/api/live/founders/claim',{}).json['number'],100)
  self.post(self.admin,'/api/admin/revoke',{'member_id':info['user']['id']})
  state=app.app.test_client().get('/api/live/founders').json
  self.assertEqual(state['remaining'],0);self.assertEqual(state['claimed'],100)
 def test_founder_signature_keeps_official_number_and_public_category_is_real(self):
  owner=self.member('founder-art');result=self.post(owner,'/api/live/founders/claim',{})
  self.assertEqual(result.json['number'],1)
  result=self.post(owner,'/api/live/founders/signature',{'mode':'letra','letter':'A','caption':'Buenas vibras','number':99})
  self.assertEqual(result.status_code,200);self.assertEqual(result.json['number'],1)
  result=self.post(owner,'/api/streamers/me',{'title':'Mi partida','bio':'Jugamos juntos','category':'videojuegos'})
  self.assertEqual(result.status_code,200);channel=result.json['channel']['id']
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(minutes=2)),channel))
  self.assertEqual(self.post(owner,'/api/admin/live-channels/feature',{'channel_id':channel,'featured':True}).status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/live-channels/feature',{'channel_id':channel,'featured':True}).status_code,200)
  public=app.app.test_client().get('/api/live/catalogue').json['channels'][0]
  self.assertEqual(public['category'],'videojuegos');self.assertTrue(public['featured']);self.assertEqual(public['founder_number'],1);self.assertEqual(public['founder_signature']['letter'],'A')
  self.assertEqual(self.post(owner,'/api/live/founders/signature',{'mode':'cancion','caption':'Buen rollo','audio_url':'https://evil.example'}).status_code,400)
 def test_original_sticker_sounds_are_free_short_and_distinct(self):
  guest=app.app.test_client();blobs=[]
  for ident in ['hello','spark','heart']:
   response=guest.get('/api/stickers/'+ident+'/sound.wav');self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,'audio/wav');blobs.append(response.data)
   with wave.open(io.BytesIO(response.data)) as audio:self.assertLess(audio.getnframes()/audio.getframerate(),1)
  self.assertEqual(len(set(blobs)),3)
  self.assertEqual(guest.get('/api/stickers/not-a-sticker/sound.wav').status_code,404)
