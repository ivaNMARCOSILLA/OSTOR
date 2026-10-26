"""Real PostgreSQL checks. Only a dedicated loopback maggy_test database is allowed."""
import os
import tempfile
from pathlib import Path
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import urlsplit
from flask import Flask
import app as application
import membership as m

URL=os.getenv('MAGGY_TEST_POSTGRES_URL')


@unittest.skipUnless(URL,'PostgreSQL integration URL not supplied')
class PostgresMembershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parsed=urlsplit(URL)
        if parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.path!='/maggy_test':
            raise RuntimeError('Integration tests require a dedicated loopback maggy_test database.')
        if application.app.config.get('MEMBERSHIP_DATABASE_URL')!=URL:
            raise RuntimeError('The application is not connected to the selected test database.')

    def setUp(self):
        ready=patch('streamers.streamer_sales_ready',return_value=True);ready.start();self.addCleanup(ready.stop)
        self.app=application.app
        with self.app.app_context(),m.database() as connection:
            for table in ['founder_signatures','live_founders','live_channel_settings','sticker_designs','member_rewards','admin_notifications','community_messages','streamer_channels','streamer_access','friend_access','payments','invitations','login_attempts','members']:
                connection.execute('DELETE FROM '+table)
        with self.app.app_context():
            m.create_admin('pg-admin','postgres-admin-password-123')
        self.admin=self.admin_client()
        self.client=self.app.test_client()
        self.post(self.client,'/api/account/register',{'username':'pg-client','password':'postgres-client-password-123'})
        self.member=self.client.get('/api/account/me').json['user']

    def post(self,client,path,data):
        csrf=client.get('/api/account/me').json['csrf']
        return client.post(path,json=data,headers={'X-CSRF-Token':csrf})

    def admin_client(self):
        client=self.app.test_client()
        self.assertEqual(self.post(client,'/api/account/login',{'username':'pg-admin','password':'postgres-admin-password-123'}).status_code,200)
        return client

    def grant(self,client,plan,reference):
        return self.post(client,'/api/admin/confirm-payment',{'member_id':self.member['id'],'plan':plan,'reference':reference})

    def test_founder_last_slot_is_serialized_and_signature_persists(self):
        with self.app.app_context(),m.database() as connection:
            for number in range(1,100):
                ident='pg-founder-'+str(number)
                connection.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(m.now_utc())))
                connection.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(m.now_utc())))
        other=self.app.test_client()
        self.assertEqual(self.post(other,'/api/account/register',{'username':'pg-other-founder','password':'postgres-other-password-123'}).status_code,201)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.post,client,'/api/live/founders/claim',{}) for client in [self.client,other]]
            results=[future.result() for future in futures]
        self.assertEqual(sorted(result.status_code for result in results),[200,409])
        winner=self.client if results[0].status_code==200 else other
        self.assertEqual(self.post(winner,'/api/live/founders/signature',{'mode':'letra','letter':'O','caption':'Buenas vibras'}).status_code,200)
        mine=winner.get('/api/live/founders').json['mine']
        self.assertEqual(mine['number'],100)
        self.assertEqual(mine['signature']['letter'],'O')
        self.assertTrue(winner.get('/api/account/me').json['user']['streamer_active'])
        self.assertEqual(winner.get('/api/account/me').json['payments'],[])

    def test_streamer_eight_euro_upgrade_and_revocation(self):
        with patch.dict(os.environ,{'LIVEKIT_URL':'wss://test.example.org','LIVEKIT_API_KEY':'test-key','LIVEKIT_API_SECRET':'x'*40,'MAGGY_STREAMERS_ENABLED':'1','MAGGY_STREAMER_SALES_ENABLED':'1'}):
            self.assertEqual(self.grant(self.admin,'monthly','PG-NORMAL-STREAMER-001').status_code,200)
            self.assertEqual(self.grant(self.admin,'streamer','PG-STREAMER-001').status_code,200)
            data=self.client.get('/api/account/me').json
            self.assertTrue(data['user']['streamer_active'])
            self.assertEqual(next(x for x in data['payments'] if x['plan']=='streamer')['amount_cents'],800)
            self.assertEqual(self.grant(self.admin,'streamer','PG-STREAMER-001').status_code,409)
            self.assertEqual(self.post(self.admin,'/api/admin/revoke',{'member_id':self.member['id']}).status_code,200)
            with self.app.app_context(),m.database() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) AS n FROM streamer_access').fetchone()['n'],0)

    def test_payment_activation_expiry_and_duplicate_reference(self):
        instant=datetime(2027,1,31,12,tzinfo=timezone.utc)
        with patch.object(m,'now_utc',return_value=instant):
            self.assertEqual(self.grant(self.admin,'monthly','PG-PAY-001').json['access_until'],'2027-02-28T12:00:00+00:00')
            self.assertEqual(self.grant(self.admin,'monthly','PG-PAY-001').status_code,409)
            self.assertEqual(self.grant(self.admin,'monthly','PG-PAY-002').json['access_until'],'2027-03-28T12:00:00+00:00')
            self.assertTrue(self.client.get('/api/account/me').json['user']['active'])
        with patch.object(m,'now_utc',return_value=datetime(2027,3,28,12,tzinfo=timezone.utc)):
            self.assertFalse(self.client.get('/api/account/me').json['user']['active'])
            self.assertEqual(self.client.get('/api/streamers').status_code,402)

    def test_concurrent_welcome_cannot_grant_twice(self):
        devices=[self.admin_client(),self.admin_client()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.grant,device,'welcome',f'PG-WELCOME-{index}') for index,device in enumerate(devices)]
            self.assertEqual(sorted(future.result().status_code for future in futures),[200,409])
        with self.app.app_context(),m.database() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) AS count FROM payments').fetchone()['count'],1)

    def test_concurrent_invitation_is_single_use(self):
        invite=self.post(self.admin,'/api/admin/invite',{'username':'pg-friend'}).json
        token=invite['path'].split('=',1)[1]
        devices=[self.app.test_client(),self.app.test_client()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.post,device,'/api/account/accept-invite',{'token':token,'password':'postgres-friend-password-123'}) for device in devices]
            self.assertEqual(sorted(future.result().status_code for future in futures),[200,400])

    def test_cookie_and_accounts_survive_an_independent_app_instance(self):
        fresh=Flask('another_vercel_instance',static_folder=self.app.static_folder)
        m.install(fresh)
        another=fresh.test_client()
        another.set_cookie('session',self.admin.get_cookie('session').value)
        self.assertEqual(another.get('/api/admin/members').status_code,200)
        self.assertEqual(another.get('/api/account/me').json['user']['username'],'pg-admin')

    def test_sqlite_migration_preserves_passwords_payments_and_refuses_overwrite(self):
        from tools.migrate_sqlite import migrate
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'DATABASE_URL':'','VERCEL':'0','MAGGY_DATA_DIR':folder,'MAGGY_COOKIE_SECURE':'0'}):
                source=Flask('local_windows_source',static_folder=self.app.static_folder)
                m.install(source)
                with source.app_context():m.create_admin('source-admin','source-admin-password-123')
                admin=source.test_client();client=source.test_client()
                self.post(admin,'/api/account/login',{'username':'source-admin','password':'source-admin-password-123'})
                self.post(client,'/api/account/register',{'username':'source-client','password':'source-client-password-123'})
                ident=client.get('/api/account/me').json['user']['id']
                self.post(admin,'/api/admin/confirm-payment',{'member_id':ident,'plan':'welcome','reference':'SQLITE-MIGRATE-001'})
                expected=client.get('/api/account/me').json['user']['access_until']
            with self.app.app_context(),m.database() as connection:
                for table in ['founder_signatures','live_founders','live_channel_settings','sticker_designs','member_rewards','admin_notifications','community_messages','streamer_channels','streamer_access','friend_access','payments','invitations','login_attempts','members']:connection.execute('DELETE FROM '+table)
            counts=migrate(Path(folder)/'members.sqlite3',self.app)
            self.assertEqual(counts['members'],2);self.assertEqual(counts['payments'],1)
            migrated=self.app.test_client()
            self.assertEqual(self.post(migrated,'/api/account/login',{'username':'source-client','password':'source-client-password-123'}).status_code,200)
            self.assertEqual(migrated.get('/api/account/me').json['user']['access_until'],expected)
            with self.assertRaisesRegex(ValueError,'ya contiene datos'):
                migrate(Path(folder)/'members.sqlite3',self.app)

    def test_private_admin_bootstrap_is_single_use_and_does_not_overwrite(self):
        with self.app.app_context():
            path=m.prepare_admin_invitation('cloud-admin')
            with self.assertRaises(ValueError):m.prepare_admin_invitation('pg-client')
        client=self.app.test_client()
        data={'token':path.split('=',1)[1],'password':'cloud-admin-password-123'}
        self.assertEqual(self.post(client,'/api/account/accept-invite',data).status_code,200)
        self.assertEqual(client.get('/api/account/me').json['user']['role'],'admin')
        self.assertEqual(client.get('/api/admin/members').status_code,200)
        self.assertEqual(self.post(client,'/api/account/accept-invite',data).status_code,400)
        with self.app.app_context():
            with self.assertRaises(ValueError):m.prepare_admin_invitation('cloud-admin')

    def test_revoke_invalidates_other_devices(self):
        self.assertEqual(self.grant(self.admin,'welcome','PG-REVOKE').status_code,200)
        self.assertTrue(self.client.get('/api/account/me').json['user']['active'])
        self.post(self.admin,'/api/admin/revoke',{'member_id':self.member['id']})
        self.assertIsNone(self.client.get('/api/account/me').json['user'])
        self.assertEqual(self.client.get('/api/streamers').status_code,401)


    def test_friend_access_is_free_persistent_and_independently_revocable(self):
        result=self.post(self.admin,'/api/admin/friend-access',{'member_id':self.member['id'],'active':True})
        self.assertEqual(result.status_code,200)
        data=self.client.get('/api/account/me').json
        self.assertTrue(data['user']['active']);self.assertTrue(data['user']['complimentary'])
        self.assertEqual(data['payments'],[])
        with self.app.app_context():m.init_database()
        self.assertTrue(self.client.get('/api/account/me').json['user']['complimentary'])
        self.post(self.admin,'/api/admin/friend-access',{'member_id':self.member['id'],'active':False})
        self.post(self.client,'/api/account/login',{'username':'pg-client','password':'postgres-client-password-123'})
        self.assertFalse(self.client.get('/api/account/me').json['user']['active'])

    def test_simultaneous_reward_heartbeats_count_one_account_clock(self):
        import rewards as rewards
        from datetime import timedelta
        start=datetime(2027,1,1,12,tzinfo=timezone.utc)
        another=self.admin_client()
        with patch.object(rewards,'now_utc',return_value=start):
            self.post(self.admin,'/api/rewards/heartbeat',{})
        with patch.object(rewards,'now_utc',return_value=start+timedelta(seconds=60)):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=[pool.submit(self.post,client,'/api/rewards/heartbeat',{}) for client in [self.admin,another]]
                self.assertEqual([future.result().json['points'] for future in results],[10,10])
        self.assertEqual(self.admin.get('/api/rewards').json['active_seconds'],60)

    def test_custom_sticker_image_survives_an_independent_app_instance(self):
        import base64,io
        from PIL import Image
        import rewards
        output=io.BytesIO();Image.new('RGBA',(16,16),(80,130,190,255)).save(output,format='PNG')
        result=self.post(self.admin,'/api/admin/stickers',{'name':'Diseño persistente','points':10,'image':base64.b64encode(output.getvalue()).decode()})
        self.assertEqual(result.status_code,200);ident=result.json['id']
        fresh=Flask('sticker_persistence',static_folder=self.app.static_folder)
        m.install(fresh);rewards.install(fresh)
        device=fresh.test_client();device.set_cookie('session',self.admin.get_cookie('session').value)
        with device.get('/api/stickers/'+ident+'/image') as image:
            self.assertEqual(image.status_code,200);self.assertEqual(image.mimetype,'image/webp')
        album=device.get('/api/rewards').json
        self.assertTrue(any(item['id']==ident for item in album['stickers']))
        self.assertEqual(album['stickers'][0]['id'],'hello');self.assertEqual(album['stickers'][0]['points'],0)

if __name__=='__main__':unittest.main(verbosity=2)
