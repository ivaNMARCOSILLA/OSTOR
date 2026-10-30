"""Tiny verified-session JPEG previews must not expose private or ended streams."""
import base64,unittest
from io import BytesIO
from datetime import timedelta
from unittest.mock import patch
from PIL import Image
import app,streamers as st,membership as m
from auth_support import authenticated_client

class LiveThumbnailTests(unittest.TestCase):
 def setUp(self):
  self.owner=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.owner.post('/api/streamers/me',json={'title':'Miniatura del directo'})
  self.channel=self.owner.get('/api/streamers').json['mine']['id']
  self.url='/api/streamers/'+self.channel+'/thumbnail'
  self.start=m.stamp(m.now_utc()-timedelta(seconds=2))
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO live_broadcast_sessions(channel_id,started_at) VALUES(?,?)',(self.channel,self.start))
   conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(minutes=2)),self.channel))
  buffer=BytesIO();Image.new('RGB',(320,180),(100,180,100)).save(buffer,format='JPEG')
  self.jpeg='data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode()
 def upload(self,**extra):return self.owner.post('/api/streamers/me/thumbnail',json={'session_start':self.start,'image':self.jpeg}|extra)
 def test_owner_preview_public_image_bounded_and_deleted_on_end(self):
  self.assertEqual(self.upload().status_code,200)
  public=app.app.test_client().get(self.url)
  self.assertEqual(public.status_code,200);self.assertEqual(public.mimetype,'image/jpeg')
  self.assertIn('no-store',public.headers['Cache-Control']);self.assertEqual(public.headers['X-Content-Type-Options'],'nosniff')
  with Image.open(BytesIO(public.data)) as image:self.assertEqual(image.size,(320,180))
  self.assertEqual(self.owner.get('/api/live/catalogue').json['channels'][0]['thumbnail_url'],self.url)
  self.owner.post('/api/streamers/me/live',json={'live':False})
  self.assertEqual(app.app.test_client().get(self.url).status_code,404)
  with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM live_channel_thumbnails').fetchone()['n'],0)
 def test_rejects_stale_session_svg_invalid_bytes_and_excess_uploads(self):
  self.assertEqual(self.upload(session_start='an-earlier-session').status_code,409)
  for image in ['data:image/svg+xml;base64,PHN2Zy8+','data:image/jpeg;base64,bm90YW5pbWFnZQ==','data:image/jpeg;base64,%%%%']:
   self.assertEqual(self.upload(image=image).status_code,400)
  for _ in range(4):self.assertEqual(self.upload().status_code,200)
  self.assertEqual(self.upload(username='different-bucket').status_code,429)
 def test_expired_or_previous_session_image_never_returned(self):
  self.assertEqual(self.upload().status_code,200)
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE live_channel_thumbnails SET updated_at=?',(m.stamp(m.now_utc()-timedelta(seconds=91)),))
  self.assertEqual(app.app.test_client().get(self.url).status_code,404)
  self.assertEqual(self.upload().status_code,200)
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE live_broadcast_sessions SET started_at=?',(m.stamp(m.now_utc()),))
  self.assertEqual(app.app.test_client().get(self.url).status_code,404)
 def test_private_and_adult_previews_require_access(self):
  self.assertEqual(self.upload().status_code,200)
  with app.app.app_context(),m.database() as conn:conn.execute('INSERT INTO channel_subscription_settings(channel_id,exclusive_live,subscriber_chat) VALUES(?,1,0)',(self.channel,))
  self.assertEqual(app.app.test_client().get(self.url).status_code,401)
  with app.app.app_context(),m.database() as conn:
   conn.execute('UPDATE channel_subscription_settings SET exclusive_live=0 WHERE channel_id=?',(self.channel,))
   conn.execute('INSERT INTO adult_channel_rules(channel_id,adult_content,version) VALUES(?,1,?)',(self.channel,'adult-version'))
  self.assertEqual(app.app.test_client().get(self.url).status_code,401)
 def test_guest_cannot_upload_and_private_preflight_is_rejected(self):
  guest=app.app.test_client();csrf=guest.get('/api/account/me').json['csrf']
  self.assertIn(guest.post('/api/streamers/me/thumbnail',json={'session_start':self.start,'image':self.jpeg},headers={'X-CSRF-Token':csrf}).status_code,(401,402,403))
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=NULL WHERE id=?',(self.channel,))
  self.assertEqual(self.upload().status_code,409)
