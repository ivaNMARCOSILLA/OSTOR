import unittest
from unittest.mock import patch
import app,membership as m,streamers as st
from auth_support import authenticated_client

class OperationsTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
 def post(self,client,path,data):
  if path=='/api/account/register':
   from registration_support import registration_data
   data=registration_data(client,data)
  token=client.get('/api/account/me').json['csrf'];return client.post(path,json=data,headers={'X-CSRF-Token':token})
 def test_maintenance_scopes_admin_recovery_and_no_lost_webhooks(self):
  public=app.app.test_client();data={'scope':'all','message':'Ol en mantenimiento. Volvemos pronto.'}
  self.assertEqual(self.post(public,'/api/admin/maintenance',data).status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/maintenance',data).status_code,200)
  r=public.get('/');self.assertEqual(r.status_code,503);self.assertEqual(r.headers['Retry-After'],'60');self.assertIn(b'Ol en mantenimiento',r.data)
  self.assertEqual(self.admin.get('/').status_code,200)
  self.assertEqual(public.get('/account').status_code,200)
  self.assertEqual(public.get('/api/status').status_code,200)
  self.assertEqual(public.get('/api/payments/status').status_code,200)
  self.assertFalse(public.get('/api/payments/status').json['enabled'])
  self.assertEqual(public.post('/api/payments/webhook/platform',json={}).status_code,400)
  self.assertEqual(self.post(self.admin,'/api/admin/maintenance',dict(data,scope='off')).status_code,200)
  self.assertEqual(public.get('/').status_code,200)
 def test_retired_supervisor_cannot_be_assigned_or_review_agreements(self):
  self.assertEqual(self.post(self.admin,'/api/admin/supervisor',{'username':'retired-role','can_review':True}).status_code,410)
  self.assertTrue(self.admin.get('/api/admin/supervisor').json['retired'])
  from operations import supervisor_review
  with app.app.app_context(),m.database() as conn:self.assertFalse(supervisor_review(conn,None))
 def test_no_fabricated_android_signing_certificate(self):
  with patch.dict('os.environ',{'OL_ANDROID_SHA256':''}):self.assertEqual(app.app.test_client().get('/.well-known/assetlinks.json').status_code,404)
  with patch.dict('os.environ',{'OL_ANDROID_SHA256':':'.join(['AB']*32)}):
   r=app.app.test_client().get('/.well-known/assetlinks.json');self.assertEqual(r.status_code,200);self.assertEqual(r.json[0]['target']['package_name'],'com.electronicama.ol')

 def test_optional_fan_alias_is_own_preference_and_never_changes_login(self):
  self.assertEqual(app.app.test_client().get('/api/account/fan-alias').status_code,401)
  self.assertEqual(self.post(self.admin,'/api/account/fan-alias',{'alias':'Admin'}).status_code,400)
  self.assertEqual(self.post(self.admin,'/api/account/fan-alias',{'alias':'Loles'}).status_code,200)
  self.assertEqual(self.admin.get('/api/account/fan-alias').json['alias'],'Loles')
  self.assertEqual(self.admin.get('/api/account/me').json['user']['username'],'test-admin')
  self.assertEqual(self.post(self.admin,'/api/account/fan-alias',{'alias':''}).status_code,200)

 def test_maintenance_report_is_admin_only_read_only_and_no_store(self):
  public=app.app.test_client()
  self.assertEqual(public.get('/api/admin/maintenance-report').status_code,403)
  with app.app.app_context(),m.database() as c:
   before=c.execute('SELECT COUNT(*) AS n FROM members').fetchone()['n']
  with patch('notifications.mail_ready',return_value=False),patch('streamers.live_ready',return_value=False):
   response=self.admin.get('/api/admin/maintenance-report')
  self.assertEqual(response.status_code,200)
  self.assertEqual(response.headers['Cache-Control'],'no-store')
  report=response.json
  self.assertTrue(report['configuration_only'])
  rows={row['name']:row for row in report['checks']}
  self.assertEqual(rows['Base de datos']['status'],'ok')
  self.assertEqual(rows['Archivos esenciales']['status'],'ok')
  self.assertEqual(rows['Correos']['status'],'pending')
  self.assertEqual(rows['Ol Livis']['status'],'pending')
  self.assertNotIn('SECRET',response.get_data(as_text=True))
  with app.app.app_context(),m.database() as c:
   self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM members').fetchone()['n'],before)
