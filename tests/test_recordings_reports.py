import json,os,unittest
from datetime import timedelta
from unittest.mock import patch,Mock
import app,membership as m,streamers as st,recordings
from auth_support import authenticated_client
CFG={'OL_RECORDINGS_ENABLED':'1','OL_RECORDING_RETENTION_CONFIRMED':'1','R2_ENDPOINT':'https://test.r2.cloudflarestorage.com','R2_BUCKET':'private-test','R2_ACCESS_KEY_ID':'test-only','R2_SECRET_ACCESS_KEY':'test-secret-only'}

class RecordingReportTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.admin.post('/api/streamers/me',json={'title':'Canal de revisión'})
  self.channel=self.admin.get('/api/streamers').json['mine'];self.owner=self.admin.get('/api/account/me').json['user']
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(hours=1)),self.channel['id']));self.channel=dict(conn.execute('SELECT * FROM streamer_channels WHERE id=?',(self.channel['id'],)).fetchone())
 def test_disabled_never_starts_egress(self):
  with app.app.app_context(),patch.dict(os.environ,{'OL_RECORDINGS_ENABLED':'0'}),patch.object(recordings,'rpc') as rpc:recordings.ensure_started(self.channel,self.owner);rpc.assert_not_called()
 def test_recording_state_private_link_expiry_and_cleanup(self):
  with app.app.app_context(),patch.dict(os.environ,CFG),patch.object(recordings,'rpc',side_effect=[{'egress_id':'eg-test','status':1},{'items':[{'status':1}]}]) as rpc:
   recordings.ensure_started(self.channel,self.owner);recordings.ensure_started(self.channel,self.owner);self.assertEqual(rpc.call_count,2)
  with app.app.app_context(),m.database() as conn:row=dict(conn.execute('SELECT * FROM live_recordings').fetchone());self.assertEqual(row['state'],'active')
  with patch.dict(os.environ,CFG),patch.object(recordings,'rpc',return_value={'items':[{'status':3}]}):self.assertEqual(self.admin.post('/api/admin/recordings/reconcile',json={'id':row['id']}).status_code,200)
  store=Mock();store.generate_presigned_url.return_value='https://private.invalid/temporary'
  with patch.dict(os.environ,CFG),patch.object(recordings,'storage',return_value=store):
   result=self.admin.get('/api/admin/recordings/'+row['id']+'/link');self.assertEqual(result.status_code,200);self.assertEqual(result.json['expires_in'],120)
   self.assertEqual(app.app.test_client().get('/api/admin/recordings/'+row['id']+'/link').status_code,403)
   with app.app.app_context(),m.database() as conn:conn.execute('UPDATE live_recordings SET expires_at=? WHERE id=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),row['id']))
   self.assertEqual(self.admin.get('/api/admin/recordings/'+row['id']+'/link').status_code,410)
   self.assertEqual(self.admin.post('/api/admin/recordings/cleanup',json={}).json['deleted'],1);store.delete_object.assert_called_once()
 def test_timeout_is_not_retried_blindly(self):
  with app.app.app_context(),patch.dict(os.environ,CFG),patch.object(recordings,'rpc',side_effect=RuntimeError('timeout')) as rpc:
   with self.assertRaises(RuntimeError):recordings.ensure_started(self.channel,self.owner)
   with self.assertRaises(RuntimeError):recordings.ensure_started(self.channel,self.owner)
   self.assertEqual(rpc.call_count,1)
 def test_detailed_report_goes_only_to_admin_queue(self):
  path='/api/streamers/'+self.channel['id']+'/comments'
  with patch('community.notify',return_value=False) as notify:
   result=self.admin.post(path,json={'kind':'report','text':'Revisar el comportamiento del directo'})
  self.assertEqual(result.status_code,200);self.assertFalse(result.json['mail_sent']);self.assertTrue(result.json['report_id'])
  detail=notify.call_args.args[2];self.assertIn(self.owner['username'],detail);self.assertIn('reporter',detail);self.assertIn('reported',detail);self.assertNotIn('password',detail)
  with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM community_report_details').fetchone()['n'],1)

 def test_comment_report_email_has_both_parties_and_original_context(self):
  path='/api/streamers/'+self.channel['id']+'/comments'
  self.admin.post(path,json={'kind':'comment','text':'Comentario que debe revisarse'})
  message=self.admin.get(path).json['comments'][0]['id']
  reporter=app.app.test_client();csrf=reporter.get('/api/account/me').json['csrf']
  from registration_support import registration_data
  reporter.post('/api/account/register',json=registration_data(reporter,{'username':'report-author','password':'report-author-password-123'}),headers={'X-CSRF-Token':csrf})
  csrf=reporter.get('/api/account/me').json['csrf']
  with patch('notifications.mail_ready',return_value=True),patch('notifications.deliver') as delivery:
   result=reporter.post(path,json={'kind':'report','text':'Solicito revisión del comentario','target_message_id':message},headers={'X-CSRF-Token':csrf})
  self.assertEqual(result.status_code,200);self.assertTrue(result.json['mail_sent']);delivery.assert_called_once()
  email=delivery.call_args.args[1];self.assertIn('report-author',email);self.assertIn(self.owner['username'],email);self.assertIn('Comentario que debe revisarse',email)
  report=next(row for row in self.admin.get('/api/admin/moderation').json['records'] if row['id']==result.json['report_id'])
  self.assertEqual(report['report']['reporter']['username'],'report-author')
  self.assertEqual(report['report']['message']['body'],'Comentario que debe revisarse')
  self.assertEqual(reporter.get('/api/admin/recordings').status_code,403)
