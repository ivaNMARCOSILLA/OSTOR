"""Consented browser visits, network estimates and strictly anonymous public feed."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import app,membership as m,visitor_registry as vr
from auth_support import authenticated_client
from registration_support import registration_data

MOBILE='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'
DESKTOP='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'

class VisitorRegistryTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup);self.guest=app.app.test_client()
  self.env=patch.dict(os.environ,{'VERCEL':'0'});self.env.start();self.addCleanup(self.env.stop)
 def post(self,client,path='/api/visits',data=None,ip='8.8.8.8',headers=None):
  csrf=client.get('/api/account/me').json['csrf']
  return client.post(path,json={'consent':True,'page':'/','event':'page'} if data is None else data,headers={'X-CSRF-Token':csrf,'User-Agent':MOBILE}|(headers or {}),environ_overrides={'REMOTE_ADDR':ip})
 def visits(self,**query):return self.admin.get('/api/admin/visits',query_string=query).json
 def cumulative(self):return self.guest.get('/api/visits/public').json['cumulative']
 def seed_session(self,ident,at):
  with app.app.app_context(),m.database() as conn:
   when=m.stamp(at)
   conn.execute('INSERT INTO visitor_devices(id,first_seen,last_seen) VALUES(?,?,?)',(ident,when,when))
   conn.execute('INSERT INTO visitor_sessions(id,device_id,member_id,account_kind,started_at,last_seen,pageviews,last_page,network_id,network_day,device,os,browser) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(ident,ident,None,'guest',when,when,1,'/',None,at.date().isoformat(),'Móvil','iOS','Safari'))
 def test_csrf_explicit_consent_and_private_admin_access(self):
  self.assertEqual(self.guest.post('/api/visits',json={'consent':True,'page':'/'}).status_code,403)
  declined=self.post(self.guest,data={'consent':False,'page':'/'})
  self.assertFalse(declined.json['recorded']);self.assertEqual(self.visits()['total'],0)
  self.assertEqual(self.guest.get('/api/admin/visits').status_code,403)
  response=self.post(self.guest);self.assertTrue(response.json['recorded']);self.assertIn('HttpOnly',response.headers['Set-Cookie']);self.assertIn('no-store',response.headers['Cache-Control'])
  record=self.visits()['visits'][0];self.assertEqual(record['device'],'Móvil');self.assertEqual(record['browser'],'Safari');self.assertEqual(record['os'],'iOS');self.assertEqual(record['pageviews'],1)
  self.assertNotIn('8.8.8.8',str(self.visits()));self.assertNotIn('Mozilla',str(self.visits()))
 def test_same_network_distinct_browsers_and_same_browser_returning(self):
  self.post(self.guest);other=app.app.test_client();self.post(other,headers={'User-Agent':DESKTOP})
  rows=self.visits();self.assertEqual(rows['summary']['browsers'],2);self.assertEqual(rows['total'],2)
  first,second=rows['visits'];self.assertEqual(first['network_id'],second['network_id']);self.assertNotEqual(first['device_id'],second['device_id'])
  self.post(self.guest,data={'consent':True,'page':'/live','event':'heartbeat'})
  rows=self.visits();self.assertEqual(rows['total'],2);self.assertEqual(sum(r['pageviews'] for r in rows['visits']),2)
  self.post(self.guest,data={'consent':True,'page':'/live','event':'page'});self.assertEqual(sum(r['pageviews'] for r in self.visits()['visits']),3)
  with patch('visitor_registry.now_utc',return_value=m.now_utc()+timedelta(minutes=31)):
   self.post(self.guest);rows=self.visits();self.assertEqual(rows['total'],3);self.assertEqual(rows['summary']['browsers'],2)
 def test_login_logout_split_sessions_without_inventing_extra_browser(self):
  self.post(self.guest)
  data=registration_data(self.guest,{'username':'visit-user','password':'visit-password-123'})
  self.assertEqual(self.post(self.guest,'/api/account/register',data).status_code,201)
  self.post(self.guest);self.post(self.guest,data={'consent':True,'page':'/account','event':'heartbeat'})
  rows=self.visits();self.assertEqual(rows['total'],2);self.assertEqual(rows['summary']['registered'],1);self.assertEqual(rows['summary']['browsers'],1)
  self.assertEqual(self.visits(kind='registered')['visits'][0]['username'],'visit-user')
  self.post(self.guest,'/api/account/logout',{})
  self.post(self.guest);self.post(self.guest,data={'consent':True,'page':'/','event':'heartbeat'})
  self.assertEqual(self.visits()['total'],3);self.assertEqual(self.visits()['summary']['browsers'],1)
 def test_networks_rotate_by_day_and_untrusted_headers_do_not_set_network(self):
  self.post(self.guest,headers={'X-Forwarded-For':'1.1.1.1','X-Vercel-Forwarded-For':'1.1.1.1'})
  first=self.visits()['visits'][0]['network_id']
  other=app.app.test_client();self.post(other);self.assertEqual(self.visits()['visits'][0]['network_id'],first)
  with patch('visitor_registry.now_utc',return_value=m.now_utc()+timedelta(days=1)):
   self.post(self.guest);rows=self.visits();self.assertTrue(any(row['network_id']!=first for row in rows['visits']))
  with patch.dict(os.environ,{'VERCEL':'1'}):
   client=app.app.test_client();self.post(client,ip='127.0.0.1',headers={'X-Vercel-Forwarded-For':'1.1.1.1'})
   trusted=self.visits()['visits'][0];self.assertIsNotNone(trusted['network_id'])
   client=app.app.test_client();self.post(client,ip='127.0.0.1',headers={'X-Vercel-Forwarded-For':'1.1.1.1, 8.8.8.8'})
   self.assertTrue(any(row['network_id'] is None for row in self.visits()['visits']))
 def test_public_feed_is_bounded_anonymous_and_minute_rounded(self):
  self.post(self.admin)
  for _ in range(22):self.post(app.app.test_client())
  response=app.app.test_client().get('/api/visits/public');self.assertEqual(response.status_code,200);data=response.json
  self.assertEqual(len(data['visits']),20);self.assertEqual(data['summary']['sessions'],23);self.assertTrue(data['consented_only']);self.assertIn('no-store',response.headers['Cache-Control'])
  for row in data['visits']:
   self.assertEqual(set(row),{'at','device','page'});self.assertTrue(row['at'].endswith(':00+00:00'))
  self.assertNotIn('test-admin',str(data));self.assertNotIn('network_id',str(data));self.assertNotIn('device_id',str(data));self.assertNotIn('8.8.8.8',str(data))
 def test_privacy_signals_withdrawal_and_retention_erase_current_browser(self):
  self.post(self.guest)
  for header in ['Sec-GPC','DNT']:
   self.assertFalse(self.post(self.guest,headers={header:'1'}).json['recorded']);self.assertEqual(self.visits()['total'],0)
   self.post(self.guest)
  self.assertEqual(self.post(self.guest,'/api/visits/consent',{'allowed':False}).status_code,200);self.assertEqual(self.visits()['total'],0)
  self.post(self.guest)
  with patch('visitor_registry.now_utc',return_value=m.now_utc()+timedelta(days=8)):
   self.assertEqual(self.visits()['total'],0);self.assertEqual(self.guest.get('/api/visits/public').json['summary']['sessions'],0)
 def test_invalid_sensitive_paths_and_unsigned_cookies_are_rejected(self):
  for page in ['/?q=private','/account#reset=secret','https://elsewhere.test',[],None]:self.assertEqual(self.post(self.guest,data={'consent':True,'page':page}).status_code,400)
  self.assertEqual(self.post(self.guest,data={'consent':True,'page':'/','event':[]}).status_code,400)
  self.assertEqual(self.visits()['total'],0)
  self.guest.set_cookie(vr.COOKIE,'forged');self.assertTrue(self.post(self.guest).json['recorded']);self.assertEqual(self.visits()['total'],1)
  self.assertEqual(self.admin.get('/api/admin/visits?kind=all-users').status_code,400)
  self.assertEqual(self.admin.get('/api/admin/visits?page=wrong').status_code,400)
 def test_rate_limit_is_bound_to_signed_browser_not_body_username(self):
  self.post(self.guest)
  raw=None
  with app.app.app_context(),m.database() as conn:
   ident=conn.execute('SELECT id FROM visitor_devices').fetchone()['id'];bucket=vr.protected(ident,'visit-rate')
   for _ in range(120):conn.execute('INSERT INTO login_attempts(bucket,attempted_at) VALUES(?,?)',(bucket,m.stamp(m.now_utc())))
  self.assertEqual(self.post(self.guest,data={'consent':True,'page':'/','username':'bypass'}).status_code,429)
 def test_cumulative_seeds_only_this_madrid_week_once_before_first_new_visit(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  origin=datetime(2026,11,1,23,tzinfo=timezone.utc)  # Monday midnight in Madrid.
  self.seed_session('previous-week',origin-timedelta(seconds=1))
  self.seed_session('week-start',origin)
  self.seed_session('this-week',instant-timedelta(hours=1))
  with patch('visitor_registry.now_utc',return_value=instant):
   self.assertEqual(self.post(self.guest).status_code,200)
   total=self.cumulative()
   self.assertEqual(total,{'sessions':3,'since':m.stamp(origin),'time_zone':'Europe/Madrid'})
   self.assertEqual(self.cumulative(),total)
   with app.app.app_context():vr.init_database()
   self.assertEqual(self.cumulative(),total)
   with app.app.app_context(),m.database() as conn:
    rows=conn.execute('SELECT * FROM visitor_public_totals').fetchall()
    self.assertEqual(len(rows),1);self.assertEqual(set(rows[0].keys()),{'id','since','sessions'})
 def test_cumulative_empty_origin_is_fixed_and_continuing_updates_do_not_increment(self):
  instant=datetime(2026,7,1,12,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=instant):
   empty=self.cumulative()
   self.assertEqual(empty['sessions'],0)
   self.assertEqual(empty['since'],'2026-06-28T22:00:00+00:00')  # CEST.
   self.post(self.guest)
   self.post(self.guest,data={'consent':True,'page':'/live','event':'heartbeat'})
   self.post(self.guest,data={'consent':True,'page':'/account','event':'page'})
   self.assertEqual(self.cumulative()['sessions'],1)
  with patch('visitor_registry.now_utc',return_value=instant+timedelta(minutes=31)):
   self.post(self.guest)
   self.assertEqual(self.cumulative(),dict(empty,sessions=2))
 def test_cumulative_survives_retention_next_week_and_daylight_saving_change(self):
  instant=datetime(2026,3,27,12,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=instant):
   self.post(self.guest);initial=self.cumulative()
   self.assertEqual(initial['since'],'2026-03-22T23:00:00+00:00')
  with patch('visitor_registry.now_utc',return_value=instant+timedelta(days=8)):
   self.assertEqual(self.visits()['total'],0)
   data=self.guest.get('/api/visits/public').json
   self.assertEqual(data['summary']['sessions'],0);self.assertEqual(data['visits'],[])
   self.assertEqual(data['cumulative'],initial)
   self.post(self.guest)
   self.assertEqual(self.cumulative(),dict(initial,sessions=2))
 def test_cumulative_is_anonymous_and_survives_consent_withdrawal(self):
  self.post(self.guest);other=app.app.test_client();self.post(other)
  initial=self.cumulative();self.assertEqual(initial['sessions'],2)
  self.post(self.guest,'/api/visits/consent',{'allowed':False})
  self.assertEqual(self.visits()['total'],1);self.assertEqual(self.cumulative(),initial)
  self.post(other,headers={'Sec-GPC':'1'})
  self.assertEqual(self.visits()['total'],0);self.assertEqual(self.cumulative(),initial)
  self.post(self.guest,data={'consent':False,'page':'/'})
  self.assertEqual(self.cumulative(),initial)
  self.post(self.guest)
  self.assertEqual(self.cumulative(),dict(initial,sessions=3))
 def test_first_post_upgrade_withdrawal_seeds_before_erasing_sessions(self):
  self.post(self.guest)
  with app.app.app_context(),m.database() as conn:
   conn.execute('DELETE FROM visitor_public_totals')  # Pre-upgrade state.
  self.post(self.guest,'/api/visits/consent',{'allowed':False})
  self.assertEqual(self.visits()['total'],0)
  self.assertEqual(self.cumulative()['sessions'],1)
 def test_first_admin_read_preserves_week_seed_before_fall_dst_retention_cleanup(self):
  # This Madrid week is 169 hours long. Its first half-hour has already passed
  # seven days of retention by Sunday night, but belongs to this week's seed.
  instant=datetime(2026,10,25,22,30,tzinfo=timezone.utc)
  origin=datetime(2026,10,18,22,tzinfo=timezone.utc)
  self.seed_session('early-in-long-week',origin)
  self.seed_session('recent-in-long-week',instant-timedelta(hours=1))
  with patch('visitor_registry.now_utc',return_value=instant):
   self.assertEqual(self.visits()['total'],1)
   self.assertEqual(self.cumulative(),{'sessions':2,'since':m.stamp(origin),'time_zone':'Europe/Madrid'})
 def test_concurrent_initial_read_and_new_sessions_increment_without_lost_updates(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  self.seed_session('existing-one',instant-timedelta(hours=2))
  self.seed_session('existing-two',instant-timedelta(hours=1))
  def enter(number):
   client=app.app.test_client()
   if number%2==0:self.assertEqual(client.get('/api/visits/public').status_code,200)
   return self.post(client).status_code
  with patch('visitor_registry.now_utc',return_value=instant):
   with ThreadPoolExecutor(max_workers=8) as pool:statuses=list(pool.map(enter,range(8)))
   self.assertEqual(statuses,[200]*8)
   self.assertEqual(self.cumulative()['sessions'],10)
