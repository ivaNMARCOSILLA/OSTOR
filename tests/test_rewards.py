import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import app
import membership as m
import rewards as r
import streamers as st
from auth_support import authenticated_client

class RewardTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
 def post(self,client,path,data):
  token=client.get('/api/account/me').json['csrf']
  return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def test_server_time_cannot_be_multiplied_by_tabs_or_client_supplied_points(self):
  start=datetime(2026,10,26,12,tzinfo=timezone.utc)
  with patch.object(r,'now_utc',return_value=start):self.post(self.admin,'/api/rewards/heartbeat',{'points':99999})
  with patch.object(r,'now_utc',return_value=start+timedelta(seconds=60)):
   first=self.post(self.admin,'/api/rewards/heartbeat',{}).json
   second=self.post(self.admin,'/api/rewards/heartbeat',{}).json
  self.assertEqual(first['points'],10);self.assertEqual(second['points'],10)
  self.assertEqual(first['unlocked'],2)
  with patch.object(r,'now_utc',return_value=start+timedelta(hours=5)):
   self.assertEqual(self.post(self.admin,'/api/rewards/heartbeat',{}).json['points'],10)
 def test_rewards_require_a_free_account_but_no_subscription(self):
  visitor=app.app.test_client()
  self.assertEqual(visitor.get('/api/rewards').status_code,401)
  self.post(visitor,'/api/account/register',{'username':'reward-member','password':'reward-member-password-123'})
  self.assertEqual(visitor.get('/api/rewards').status_code,200)
  ident=visitor.get('/api/account/me').json['user']['id']
  self.post(self.admin,'/api/admin/friend-access',{'member_id':ident,'active':True})
  self.assertEqual(visitor.get('/api/rewards').json['points'],0)
  self.assertEqual(visitor.get('/api/rewards').json['unlocked'],1)
 def test_stickers_cannot_be_sent_locked_and_do_not_accept_arbitrary_urls(self):
  result=self.post(self.admin,'/api/streamers/me',{'title':'Test reward channel','bio':''})
  channel=result.json['channel']['id']
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(minutes=5)),channel))
  url='/api/streamers/'+channel+'/comments'
  self.assertEqual(self.post(self.admin,url,{'kind':'sticker','text':'crown'}).status_code,403)
  self.assertEqual(self.post(self.admin,url,{'kind':'sticker','text':'../../evil.svg'}).status_code,403)
  self.assertTrue(self.post(self.admin,url,{'kind':'sticker','text':'hello'}).json['accepted'])
  result=self.admin.get(url).json['comments']
  self.assertEqual(result[0]['kind'],'sticker');self.assertEqual(result[0]['body'],'hello')

 def test_admin_can_add_raster_designs_but_creator_sticker_remains_free(self):
  import base64,io
  from PIL import Image
  output=io.BytesIO();Image.new('RGBA',(8,8),(50,100,180,255)).save(output,format='PNG')
  image=base64.b64encode(output.getvalue()).decode()
  result=self.post(self.admin,'/api/admin/stickers',{'name':'Diseño de prueba','points':10,'image':image})
  self.assertEqual(result.status_code,200);ident=result.json['id']
  with self.admin.get('/api/stickers/'+ident+'/image') as response:
   self.assertEqual(response.status_code,200);self.assertEqual(response.mimetype,'image/webp')
  album=self.admin.get('/api/rewards').json
  self.assertEqual(album['stickers'][0]['id'],'hello');self.assertEqual(album['stickers'][0]['points'],0)
  self.assertFalse(next(item for item in album['stickers'] if item['id']==ident)['unlocked'])
  result=self.post(self.admin,'/api/admin/stickers',{'id':'hello','name':'Creador','points':10,'image':image})
  self.assertEqual(result.status_code,400)
  result=self.post(self.admin,'/api/admin/stickers',{'id':ident,'name':'Otro diseño','points':20,'image':image})
  self.assertEqual(result.status_code,409)
  result=self.post(self.admin,'/api/admin/stickers',{'name':'SVG','points':0,'image':base64.b64encode(b'<svg onload="alert(1)"/>').decode()})
  self.assertEqual(result.status_code,400)
  self.assertEqual(self.post(app.app.test_client(),'/api/admin/stickers',{'name':'Ataque','points':0,'image':image}).status_code,403)

 def test_large_catalogue_is_paginated_searchable_and_owned_only_is_private(self):
  drawings=[{'id':f'emoji_{i:04}','name':f'Emoción espacial {i:04}','minutes':i,'points':i*10,'image':f'/assets/stickers/costumes/test-{i}.webp','series':'Espacio'} for i in range(1,1000)]
  with patch.object(r,'illustrated_catalogue',return_value=drawings):
   first=self.admin.get('/api/rewards').json
   self.assertEqual(first['total'],1000);self.assertEqual(len(first['stickers']),24);self.assertEqual(first['pages'],42)
   self.assertEqual(first['stickers'][0]['id'],'hello')
   last=self.admin.get('/api/rewards?page=99999').json
   self.assertEqual(last['page'],42);self.assertEqual(len(last['stickers']),16)
   owned=self.admin.get('/api/rewards?owned=1').json
   self.assertEqual(owned['filtered_total'],1);self.assertEqual(len(owned['stickers']),1)
   result=self.admin.get('/api/rewards?q=1000').json
   self.assertEqual(result['filtered_total'],1);self.assertEqual(result['stickers'][0]['number'],1000)
   result=self.admin.get('/api/rewards?q=emocion&series=Espacio').json
   self.assertEqual(result['filtered_total'],999)
   manager=self.admin.get('/api/admin/stickers?page=2').json
   self.assertEqual(len(manager['stickers']),24);self.assertEqual(manager['total'],1000)
   self.assertEqual(self.admin.get('/api/rewards?series=NoExiste').json['filtered_total'],0)
