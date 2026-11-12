"""Consented browser visits, network estimates and strictly anonymous public feed."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import app,membership as m,visitor_registry as vr
from auth_support import authenticated_client
from registration_support import registration_data

MOBILE='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'
DESKTOP='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'
TABLET='Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1'

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
 def test_compact_public_counter_reads_only_anonymous_sums_and_keeps_history(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=instant):
   for client in [self.guest,app.app.test_client(),app.app.test_client()]:self.post(client)
   initial=self.guest.get('/api/visits/public').json
  statements=[]
  @contextmanager
  def traced_database():
   with m.database() as conn:
    conn.set_trace_callback(statements.append)
    yield conn
  with patch('visitor_registry.now_utc',return_value=instant+timedelta(days=20)),patch('visitor_registry.database',traced_database),patch('visitor_registry.cleanup',side_effect=AssertionError('compact refresh must not clean personal detail')):
   response=self.guest.get('/api/visits/public?compact=1&history_page=1')
  self.assertEqual(response.status_code,200);data=response.json
  self.assertEqual(set(data),{'cumulative','history','consented_only','approximate'})
  self.assertEqual(data['cumulative'],initial['cumulative']);self.assertEqual(data['cumulative']['sessions'],3)
  self.assertEqual(data['history']['page'],1);self.assertEqual(data['history']['pages'],2)
  self.assertEqual(next(day['sessions'] for day in data['history']['days'] if day['day']=='2026-11-04'),3)
  self.assertIn('no-store',response.headers['Cache-Control']);self.assertNotIn('Set-Cookie',response.headers)
  for statement in statements:
   self.assertNotIn('visitor_sessions',statement.lower());self.assertNotIn('visitor_devices',statement.lower())
   self.assertNotIn('delete ',statement.lower());self.assertNotIn('count(',statement.lower())
  self.assertEqual(len(statements),4)
 def test_compact_first_read_seeds_real_counts_before_any_later_cleanup(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  self.seed_session('recoverable-old',instant-timedelta(days=10))
  self.seed_session('recent',instant-timedelta(hours=1))
  with patch('visitor_registry.now_utc',return_value=instant):
   with patch('visitor_registry.cleanup',side_effect=AssertionError('compact refresh must not clean personal detail')):
    compact=self.guest.get('/api/visits/public?compact=1').json
   self.assertEqual(compact['cumulative']['sessions'],2)
   self.assertEqual(sum(day['sessions'] or 0 for day in compact['history']['days']),2)
   full=self.guest.get('/api/visits/public?compact=0').json
   self.assertEqual(full['cumulative'],compact['cumulative']);self.assertEqual(full['history'],compact['history'])
   self.assertEqual(full['summary']['sessions'],1);self.assertEqual(len(full['visits']),1)
   for value in ['','true','-1','2','invalid']:
    self.assertEqual(self.guest.get('/api/visits/public?compact='+value).status_code,400)
   self.assertEqual(self.guest.get('/api/visits/public?compact=1&history_page=0').status_code,400)
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
 def test_cumulative_seeds_120_madrid_dates_once_before_first_new_visit(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  origin=datetime(2026,7,7,22,tzinfo=timezone.utc)  # 8 July midnight in Madrid, 120 dates including today.
  self.seed_session('before-history',origin-timedelta(seconds=1))
  self.seed_session('history-start',origin)
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
   self.assertEqual(empty['since'],'2026-03-03T23:00:00+00:00')  # 4 March midnight CET, before the DST change.
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
   self.assertEqual(initial['since'],'2025-11-27T23:00:00+00:00')
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
 def test_first_admin_read_preserves_available_history_before_retention_cleanup(self):
  # Old observations that still exist seed the anonymous history before the
  # seven-day personal-detail cleanup, including an interval crossing DST.
  instant=datetime(2026,10,25,22,30,tzinfo=timezone.utc)
  origin=datetime(2026,6,27,22,tzinfo=timezone.utc)
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
   history=self.guest.get('/api/visits/public').json['history']
   self.assertEqual(sum(row['sessions'] or 0 for row in history['days']),10)

 def test_history_expands_old_total_once_without_faking_erased_dates(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  old_origin=datetime(2026,11,1,23,tzinfo=timezone.utc)
  self.seed_session('older-one',datetime(2026,10,25,12,tzinfo=timezone.utc))
  self.seed_session('older-two',datetime(2026,11,1,12,tzinfo=timezone.utc))
  self.seed_session('old-total-one',datetime(2026,11,2,12,tzinfo=timezone.utc))
  self.seed_session('old-total-two',datetime(2026,11,3,12,tzinfo=timezone.utc))
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO visitor_public_totals(id,since,sessions) VALUES(?,?,?)',(vr.PUBLIC_TOTAL_ID,m.stamp(old_origin),12))
  with patch('visitor_registry.now_utc',return_value=instant):
   data=self.guest.get('/api/visits/public').json
   self.assertEqual(data['cumulative'],{'sessions':14,'since':'2026-07-07T22:00:00+00:00','time_zone':'Europe/Madrid'})
   history=data['history'];self.assertEqual(history['unassigned'],10)
   self.assertEqual(history['tracking_since'],'2026-11-05')
   self.assertEqual(history['total_days'],120);self.assertEqual(history['pages'],1)
   days={day['day']:day for day in history['days']}
   self.assertEqual(days['2026-10-21'],{'day':'2026-10-21','sessions':None,'complete':False})
   self.assertEqual(days['2026-10-25'],{'day':'2026-10-25','sessions':1,'complete':False})
   self.assertEqual(days['2026-11-02'],{'day':'2026-11-02','sessions':1,'complete':False})
   self.assertEqual(self.guest.get('/api/visits/public').json['cumulative'],data['cumulative'])
  with patch('visitor_registry.now_utc',return_value=instant+timedelta(days=30)):
   later=self.guest.get('/api/visits/public').json
   self.assertEqual(later['cumulative'],data['cumulative'])
   self.assertEqual(later['history']['total_days'],150);self.assertEqual(later['history']['pages'],2)
   future=[day for day in later['history']['days'] if day['day']>'2026-11-04']
   self.assertTrue(all(day['complete'] and day['sessions']==0 for day in future))
   oldest=self.guest.get('/api/visits/public?history_page=2').json['history']
   combined={day['day']:day for day in oldest['days']+later['history']['days']}
   self.assertEqual([combined[day['day']] for day in history['days']],history['days'])
   self.assertEqual(oldest['unassigned'],10)

 def test_older_existing_origin_is_preserved_and_undated_total_is_not_reallocated(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  origin='2026-04-30T22:00:00+00:00'
  self.seed_session('known-day',instant-timedelta(days=1))
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO visitor_public_totals VALUES(?,?,?)',(vr.PUBLIC_TOTAL_ID,origin,25))
  with patch('visitor_registry.now_utc',return_value=instant):
   data=self.guest.get('/api/visits/public').json
   self.assertEqual(data['cumulative']['since'],origin);self.assertEqual(data['cumulative']['sessions'],25)
   self.assertEqual(data['history']['unassigned'],24);self.assertEqual(data['history']['total_days'],188)
   self.assertEqual(data['history']['days'][0]['day'],'2026-07-08')
   oldest=self.guest.get('/api/visits/public?history_page=2').json['history']
   self.assertEqual(oldest['days'][0]['day'],'2026-05-01')
   self.assertTrue(all(day['sessions'] is None and not day['complete'] for day in oldest['days']))

 def test_initialized_short_calendar_expands_without_recounting_private_visits(self):
  initialized=datetime(2026,11,4,12,tzinfo=timezone.utc)
  transition=initialized+timedelta(days=10)
  old_origin='2026-10-20T22:00:00+00:00'
  self.seed_session('older-private-detail',datetime(2026,9,1,12,tzinfo=timezone.utc))
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO visitor_public_totals VALUES(?,?,?)',(vr.PUBLIC_TOTAL_ID,old_origin,321))
   conn.execute('INSERT INTO visitor_public_history VALUES(?,?,?,?)',(vr.PUBLIC_TOTAL_ID,old_origin,m.stamp(initialized),312))
   for day,count in [('2026-11-03',7),('2026-11-04',2)]:
    conn.execute('INSERT INTO visitor_public_days VALUES(?,?)',(day,count))
   # A read-only poll asks its caller to lock instead of changing the calendar.
   self.assertIsNone(vr.cumulative_visits(conn,transition,initialize=False))
   self.assertEqual(conn.execute('SELECT since FROM visitor_public_totals').fetchone()['since'],old_origin)
  statements=[]
  @contextmanager
  def traced_database():
   with m.database() as conn:
    conn.set_trace_callback(statements.append)
    yield conn
  with patch('visitor_registry.now_utc',return_value=transition),patch('visitor_registry.database',traced_database),patch('visitor_registry.cleanup',side_effect=AssertionError('calendar expansion must not erase detail')):
   response=self.guest.get('/api/visits/public?compact=1')
  self.assertEqual(response.status_code,200);data=response.json
  self.assertEqual(data['cumulative'],{'sessions':321,'since':'2026-07-07T22:00:00+00:00','time_zone':'Europe/Madrid'})
  self.assertEqual(data['history']['unassigned'],312)
  self.assertEqual(data['history']['tracking_since'],'2026-11-05')
  known={day['day']:day for day in data['history']['days']}
  self.assertEqual(known['2026-09-01'],{'day':'2026-09-01','sessions':None,'complete':False})
  self.assertEqual(known['2026-11-03'],{'day':'2026-11-03','sessions':7,'complete':False})
  self.assertEqual(known['2026-11-05'],{'day':'2026-11-05','sessions':0,'complete':True})
  self.assertTrue(any(statement=='BEGIN IMMEDIATE' for statement in statements))
  for statement in statements:
   self.assertNotIn('visitor_sessions',statement.lower())
   self.assertNotIn('visitor_devices',statement.lower())
   self.assertNotIn('delete ',statement.lower())
  with app.app.app_context(),m.database() as conn:
   history=dict(conn.execute('SELECT * FROM visitor_public_history').fetchone())
   self.assertEqual(history,{'id':vr.PUBLIC_TOTAL_ID,'since':'2026-07-07T22:00:00+00:00','initialized_at':m.stamp(initialized),'unassigned':312})
   self.assertEqual([(row['day'],row['sessions']) for row in conn.execute('SELECT * FROM visitor_public_days ORDER BY day').fetchall()],[('2026-11-03',7),('2026-11-04',2)])
   self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM visitor_sessions').fetchone()['n'],1)
  statements.clear()
  with patch('visitor_registry.now_utc',return_value=transition+timedelta(days=200)),patch('visitor_registry.database',traced_database):
   later=self.guest.get('/api/visits/public?compact=1').json
  self.assertEqual(later['cumulative'],data['cumulative'])
  self.assertEqual(later['history']['unassigned'],312)
  self.assertEqual(later['history']['tracking_since'],'2026-11-05')
  self.assertEqual(len(statements),4)
  self.assertFalse(any('update ' in statement.lower() or 'begin ' in statement.lower() for statement in statements))

 def test_initialized_origin_older_than_120_dates_remains_unchanged(self):
  initialized=datetime(2026,11,4,12,tzinfo=timezone.utc)
  origin='2025-01-01T23:00:00+00:00'
  with app.app.app_context(),m.database() as conn:
   conn.execute('INSERT INTO visitor_public_totals VALUES(?,?,?)',(vr.PUBLIC_TOTAL_ID,origin,17))
   conn.execute('INSERT INTO visitor_public_history VALUES(?,?,?,?)',(vr.PUBLIC_TOTAL_ID,origin,m.stamp(initialized),17))
   total=vr.cumulative_visits(conn,initialized+timedelta(days=80),initialize=False)
   self.assertEqual(total,{'sessions':17,'since':origin,'time_zone':'Europe/Madrid'})
   self.assertEqual(dict(conn.execute('SELECT * FROM visitor_public_history').fetchone()),
                    {'id':vr.PUBLIC_TOTAL_ID,'since':origin,'initialized_at':m.stamp(initialized),'unassigned':17})

 def test_history_pagination_keeps_all_dates_and_future_days_known(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=instant):
   self.post(self.guest)
   first=self.guest.get('/api/visits/public').json['history']
   self.assertEqual(first['days'][-1],{'day':'2026-11-04','sessions':1,'complete':False})
  with patch('visitor_registry.now_utc',return_value=instant+timedelta(days=125)):
   self.assertEqual(self.visits()['total'],0)
   response=self.post(self.guest);self.assertEqual(response.json['cumulative']['sessions'],2)
   pages=[self.guest.get('/api/visits/public?history_page='+str(page)).json['history'] for page in [1,2,3]]
   days=[day for page in reversed(pages) for day in page['days']]
   self.assertEqual(len(days),245);self.assertEqual(len({day['day'] for day in days}),245)
   self.assertEqual(days[0]['day'],'2026-07-08');self.assertEqual(days[-1]['day'],'2027-03-09')
   known={day['day']:day for day in days}
   self.assertEqual(known['2026-11-05'],{'day':'2026-11-05','sessions':0,'complete':True})
   self.assertEqual(known['2027-03-09'],{'day':'2027-03-09','sessions':1,'complete':True})
   self.assertEqual(known['2026-11-04'],{'day':'2026-11-04','sessions':1,'complete':False})
   self.assertEqual(self.guest.get('/api/visits/public?history_page=999').json['history']['page'],3)
   for value in ['invalid','0','-1']:
    self.assertEqual(self.guest.get('/api/visits/public?history_page='+value).status_code,400)

 def test_daily_history_uses_madrid_dates_and_survives_withdrawal(self):
  before_midnight=datetime(2026,11,4,22,59,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=before_midnight):self.post(self.guest)
  other=app.app.test_client()
  with patch('visitor_registry.now_utc',return_value=before_midnight+timedelta(minutes=2)):
   self.post(other)
   self.post(other,data={'consent':True,'event':'heartbeat','page':'/live'})
   self.post(self.guest,'/api/visits/consent',{'allowed':False})
   self.post(other,'/api/visits/consent',{'allowed':False})
   data=self.guest.get('/api/visits/public').json
   self.assertEqual(data['cumulative']['sessions'],2);self.assertEqual(data['visits'],[])
   days={day['day']:day for day in data['history']['days']}
   self.assertEqual(days['2026-11-04']['sessions'],1)
   self.assertEqual(days['2026-11-05'],{'day':'2026-11-05','sessions':1,'complete':True})

 def test_three_devices_on_same_network_and_account_share_one_total(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  devices=[app.app.test_client() for _ in range(3)]
  for client in devices:client.set_cookie('session',self.admin.get_cookie('session').value)
  with patch('visitor_registry.now_utc',return_value=instant):
   for index,(client,ua) in enumerate(zip(devices,[MOBILE,DESKTOP,TABLET]),1):
    response=self.post(client,headers={'User-Agent':ua})
    self.assertEqual(response.status_code,200);self.assertEqual(response.json['cumulative']['sessions'],index)
   for client in devices:
    self.assertEqual(client.get('/api/visits/public').json['cumulative']['sessions'],3)
    self.post(client,data={'consent':True,'page':'/','event':'heartbeat'})
   data=devices[0].get('/api/visits/public').json
   self.assertEqual(data['cumulative']['sessions'],3)
   self.assertEqual(data['history']['days'][-1]['sessions'],3)
   private=self.visits()
   self.assertEqual(private['summary']['browsers'],3)
   self.assertEqual({row['device'] for row in private['visits']},{'Móvil','Ordenador','Tableta'})

 def test_upgrade_withdrawal_keeps_available_old_daily_counts(self):
  instant=datetime(2026,11,4,12,tzinfo=timezone.utc)
  with patch('visitor_registry.now_utc',return_value=instant):
   self.post(self.guest)
   with app.app.app_context(),m.database() as conn:
    conn.execute('DELETE FROM visitor_public_history');conn.execute('DELETE FROM visitor_public_days')
   self.post(self.guest,'/api/visits/consent',{'allowed':False})
   data=self.guest.get('/api/visits/public').json
   self.assertEqual(data['cumulative']['sessions'],1)
   self.assertEqual(data['history']['days'][-1]['sessions'],1)
   self.assertEqual(data['history']['unassigned'],0)
