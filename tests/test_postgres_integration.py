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
from legacy_support import legacy_payment

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
        legacy=patch.dict(os.environ,{'OL_PAYMENT_PROVIDER':'legacy_paypal'});legacy.start();self.addCleanup(legacy.stop)
        code=patch("human_check.new_code",return_value="OL234");code.start();self.addCleanup(code.stop)
        ready=patch('streamers.streamer_sales_ready',return_value=True);ready.start();self.addCleanup(ready.stop)
        self.app=application.app
        with self.app.app_context(),m.database() as connection:
            for table in ['visitor_sessions','visitor_devices','live_channel_thumbnails','community_likes','live_guest_invites','live_broadcast_sessions','live_recordings','community_report_details','interface_revisions','adult_age_declarations','adult_channel_rules','live_channel_views','community_retention_clock','stripe_order_names','annual_access_emails','fan_aliases','stripe_reversals','stripe_events','stripe_orders','stripe_connect_states','stripe_accounts','ol_supervisors','ol_operations','moderator_permissions','two_factor_recovery','member_two_factor','community_audiences','creator_subscriptions','channel_subscription_settings','subscription_approvals','subscription_agreements','pricing_moderators','founder_slot_history','live_launch','creator_daily_activity','founder_activity','live_entitlements','human_challenges','promotion_metrics','online_presence','founder_signatures','live_founders','live_channel_settings','sticker_designs','member_rewards','admin_notifications','community_messages','streamer_channels','streamer_access','friend_access','payments','invitations','login_attempts','members']:
                connection.execute('DELETE FROM '+table)
        with self.app.app_context():
            m.create_admin('pg-admin','postgres-admin-password-123')
        self.admin=self.admin_client()
        self.client=self.app.test_client()
        self.post(self.client,'/api/account/register',{'username':'pg-client','password':'postgres-client-password-123'})
        self.member=self.client.get('/api/account/me').json['user']

    def post(self,client,path,data):
        if path=='/api/account/register':
         from registration_support import registration_data
         data=registration_data(client,data)
        csrf=client.get('/api/account/me').json['csrf']
        if path in {'/api/live/founders/claim','/api/account/live-trial'}:
            data=dict(data,human_id=client.get('/api/account/human-check').json['id'],human_answer='OL234')
        return client.post(path,json=data,headers={'X-CSRF-Token':csrf})

    def admin_client(self):
        client=self.app.test_client()
        self.assertEqual(self.post(client,'/api/account/login',{'username':'pg-admin','password':'postgres-admin-password-123'}).status_code,200)
        return client

    def grant(self,client,plan,reference):
        return legacy_payment(self.app,client,self.member['id'],plan,reference)

    def annual_fixture(self,client):
        ident=client.get('/api/account/me').json['user']['id']
        with self.app.app_context(),m.database() as c:
            c.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.end_of_plan(m.now_utc(),'annual')),ident))
            c.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?) ON CONFLICT(member_id) DO UPDATE SET paid_at=excluded.paid_at',(ident,m.stamp(m.now_utc())))
        return ident

    def test_retired_trial_rejected_and_paid_founder_expiry_reallocated(self):
        self.assertEqual(self.post(self.client,'/api/account/live-trial',{}).status_code,410)
        self.assertEqual(self.post(self.client,'/api/live/founders/claim',{}).status_code,409)
        self.annual_fixture(self.client)
        claim=self.post(self.client,'/api/live/founders/claim',{})
        self.assertEqual(claim.status_code,200,claim.json)
        with self.app.app_context(),m.database() as conn:
            conn.execute('UPDATE members SET access_until=? WHERE id=?',(m.stamp(m.now_utc()-m.timedelta(seconds=1)),self.member['id']))
        second=self.app.test_client()
        self.assertEqual(self.post(second,'/api/account/register',{'username':'pg-next-holder','password':'postgres-next-holder-password-123'}).status_code,201)
        self.annual_fixture(second)
        next_claim=self.post(second,'/api/live/founders/claim',{})
        self.assertEqual(next_claim.status_code,200,next_claim.json)
        self.assertEqual(next_claim.json['number'],1)
        self.assertIsNone(self.client.get('/api/account/me').json['user']['founder_number'])
        history=self.admin.get('/api/admin/founders/history').json
        self.assertEqual(history['total'],1)
        self.assertEqual(history['history'][0]['reason'],'annual_expired')

    def test_managed_platform_payment_signed_receipt_survives_retries(self):
        import payments as gateway
        import hashlib,hmac,json,time
        with self.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO live_entitlements(member_id,trial_started_at,trial_until) VALUES(?,?,?)',(self.member['id'],m.stamp(m.now_utc()-m.timedelta(days=100)),m.stamp(m.now_utc()-m.timedelta(days=1))))
        with patch.dict(os.environ,{'OL_PAYMENT_PROVIDER':'stripe','STRIPE_WEBHOOK_SECRET':'whsec_postgres_local_test'}),patch.object(gateway,'ready',return_value=True),patch.object(gateway,'stripe',return_value={'id':'cs_postgres_local_test','url':'https://checkout.stripe.com/c/pay/local-test'}):
            result=self.post(self.client,'/api/payments/checkout',{'annual_terms':True,'legal_name':'Persona de Prueba'})
            self.assertEqual(result.status_code,200)
            with self.app.app_context(),m.database() as conn:order=conn.execute('SELECT * FROM stripe_orders WHERE checkout_id=?',('cs_postgres_local_test',)).fetchone()
            event={'id':'evt_postgres_local_test','livemode':True,'type':'checkout.session.completed','data':{'object':{'id':order['checkout_id'],'payment_status':'paid','amount_total':2500,'currency':'eur','metadata':{'ol_order':order['id']},'payment_intent':'pi_postgres_local_test'}}}
            raw=json.dumps(event).encode();timestamp=str(int(time.time()));sig=hmac.new(b'whsec_postgres_local_test',timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest();headers={'Content-Type':'application/json','Stripe-Signature':'t='+timestamp+',v1='+sig}
            first=self.app.test_client().post('/api/payments/webhook/platform',data=raw,headers=headers)
            self.assertEqual(first.status_code,200)
            second=self.app.test_client().post('/api/payments/webhook/platform',data=raw,headers=headers)
            self.assertTrue(second.json['duplicate'])
            me=self.client.get('/api/account/me').json
            self.assertTrue(me['user']['live_annual']);self.assertFalse(me['user']['live_lifetime']);self.assertEqual(len(me['payments']),1)
            with self.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM stripe_events').fetchone()['n'],1)

    def test_creator_agreement_receipt_and_private_benefits_persist(self):
        with self.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)',(self.member['id'],m.stamp(m.now_utc())))
        self.annual_fixture(self.client)
        gref=self.app.test_client();viewer=self.app.test_client()
        self.assertEqual(self.post(gref,'/api/account/register',{'username':'gref','password':'postgres-moderator-password-123'}).status_code,201)
        self.assertEqual(self.post(viewer,'/api/account/register',{'username':'pg-subscriber','password':'postgres-subscriber-password-123'}).status_code,201)
        self.assertEqual(self.post(self.admin,'/api/admin/subscription-moderator',{'username':'Gref'}).status_code,200)
        self.assertEqual(self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':['review_agreements','approve_agreements']}).status_code,200)
        channel=self.post(self.client,'/api/streamers/me',{'title':'PG creator channel','paypal_url':'https://paypal.me/CreatorOnly','owns_paypal':True}).json['channel']['id']
        agreement=self.post(self.client,'/api/channel-subscriptions/propose',{'price_cents':350,'period':'month','benefits':['badge','subscriber_chat']}).json['agreement_id']
        for client,party in [(self.client,'creator'),(self.admin,'admin'),(gref,'moderator')]:
            result=self.post(client,'/api/channel-subscriptions/approve',{'agreement_id':agreement,'party':party})
            self.assertEqual(result.status_code,200)
        self.assertTrue(result.json['agreement_activated'])
        receipt={'username':'pg-subscriber','reference':'PG-CREATOR-RECEIPT-001','amount_cents':350,'verified_receipt':True}
        self.assertEqual(self.post(self.client,'/api/channel-subscriptions/'+channel+'/confirm',receipt).status_code,200)
        self.assertEqual(self.post(self.client,'/api/channel-subscriptions/'+channel+'/confirm',receipt).status_code,409)
        public=viewer.get('/api/channel-subscriptions/'+channel).json
        self.assertEqual(public['subscriber_count'],1)
        self.assertIn('badge',public['mine'])
        self.assertEqual(gref.get('/api/channel-subscriptions/'+channel+'/members').status_code,403)
        self.assertEqual(viewer.get('/api/account/me').json['payments'],[])

    def test_optional_two_factor_counter_and_recovery_persist(self):
        import base64
        import two_factor as tf
        with patch.object(tf,'counter_now',return_value=1000000):
            setup=self.post(self.client,'/api/account/2fa/setup',{'password':'postgres-client-password-123'})
            self.assertEqual(setup.status_code,200)
            otp=tf.totp(base64.b32decode(setup.json['secret']),1000000)
            enabled=self.post(self.client,'/api/account/2fa/enable',{'otp':otp})
            self.assertEqual(enabled.status_code,200)
            other=self.app.test_client()
            login={'username':'pg-client','password':'postgres-client-password-123'}
            self.assertEqual(self.post(other,'/api/account/login',login).status_code,401)
            self.assertEqual(self.post(other,'/api/account/login',dict(login,otp=otp)).status_code,401)
            recovery=enabled.json['recovery_codes'][0]
            self.assertEqual(self.post(other,'/api/account/login',dict(login,recovery_code=recovery)).status_code,200)
            self.assertEqual(other.get('/api/account/2fa/status').json['recovery_remaining'],7)
            repeat=self.app.test_client()
            self.assertEqual(self.post(repeat,'/api/account/login',dict(login,recovery_code=recovery)).status_code,401)

    def test_statistics_and_presence_use_persistent_postgresql(self):
        visitor=self.app.test_client()
        result=self.post(visitor,'/api/presence',{'consent':True})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json,{'recorded':True});self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['guests'],1)
        self.post(visitor,'/api/presence',{'consent':True});self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['guests'],1)
        self.post(self.client,'/api/presence',{'consent':True});self.assertEqual(self.admin.get('/api/admin/statistics').json['online']['members'],1)
        self.assertEqual(self.grant(self.admin,'monthly','PG-STATISTICS-001').status_code,200)
        data=self.admin.get('/api/admin/statistics').json
        self.assertEqual(data['accounts']['registered'],1)
        self.assertEqual(data['payments']['total_cents'],600)
        self.assertEqual(sum(day['cents'] for day in data['days']),600)
        self.assertEqual(data['online']['total'],2)

    def test_founder_last_slot_is_serialized_and_signature_persists(self):
        with self.app.app_context(),m.database() as connection:
            for number in range(1,100):
                ident='pg-founder-'+str(number)
                connection.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(m.now_utc())))
                connection.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(m.now_utc())))
        other=self.app.test_client()
        self.assertEqual(self.post(other,'/api/account/register',{'username':'pg-other-founder','password':'postgres-other-password-123'}).status_code,201)
        self.annual_fixture(self.client);self.annual_fixture(other)
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
            self.assertEqual(self.post(self.client,'/api/streamers/me',{'title':'No autorizado'}).status_code,402)

    def test_concurrent_signed_annual_webhooks_grant_only_one_year(self):
        import payments as gateway
        import hashlib,hmac,json,time
        with patch.dict(os.environ,{'OL_PAYMENT_PROVIDER':'stripe','STRIPE_WEBHOOK_SECRET':'whsec_postgres_concurrent'}),patch.object(gateway,'ready',return_value=True),patch.object(gateway,'stripe',return_value={'id':'cs_postgres_concurrent','url':'https://checkout.stripe.com/c/pay/local-test'}):
            result=self.post(self.client,'/api/payments/checkout',{'annual_terms':True,'legal_name':'Persona de Prueba'})
            self.assertEqual(result.status_code,200,result.json)
            with self.app.app_context(),m.database() as conn:order=conn.execute('SELECT * FROM stripe_orders WHERE checkout_id=?',('cs_postgres_concurrent',)).fetchone()
            def send(index):
                event={'id':'evt_pg_concurrent_'+str(index),'livemode':True,'type':'checkout.session.completed','data':{'object':{'id':order['checkout_id'],'payment_status':'paid','amount_total':2500,'currency':'eur','metadata':{'ol_order':order['id']},'payment_intent':'pi_pg_concurrent'}}}
                raw=json.dumps(event).encode();timestamp=str(int(time.time()));sig=hmac.new(b'whsec_postgres_concurrent',timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
                return self.app.test_client().post('/api/payments/webhook/platform',data=raw,headers={'Content-Type':'application/json','Stripe-Signature':'t='+timestamp+',v1='+sig})
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(send,range(32)))
            self.assertEqual([r.status_code for r in results],[200]*32)
        data=self.client.get('/api/account/me').json
        self.assertTrue(data['user']['live_annual']);self.assertTrue(data['user']['streamer_active'])
        self.assertEqual(len(data['payments']),1);self.assertEqual(data['payments'][0]['amount_cents'],2500)

    def test_six_simultaneous_registrations_cannot_duplicate_username(self):
        devices=[self.app.test_client() for _ in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(lambda client:self.post(client,'/api/account/register',{'username':'pg-shared-name','password':'postgres-concurrent-password-123'}),devices))
        self.assertEqual(sorted(r.status_code for r in results),[201,400,400,400,400,400])
        with self.app.app_context(),m.database() as c:
            rows=c.execute('SELECT role FROM members WHERE username=?',('pg-shared-name',)).fetchall()
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['role'],'member')

    def test_concurrent_invitation_is_single_use(self):
        invite=self.post(self.admin,'/api/admin/invite',{'username':'pg-friend'}).json
        token=invite['path'].split('=',1)[1]
        devices=[self.app.test_client(),self.app.test_client()]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(self.post,device,'/api/account/accept-invite',{'token':token,'password':'postgres-friend-password-123'}) for device in devices]
            self.assertEqual(sorted(future.result().status_code for future in futures),[200,400])

    def test_private_email_verification_and_reset_persist_in_postgresql(self):
        import email_security
        from urllib.parse import urlsplit,parse_qs
        with patch.object(email_security,'mail_ready',return_value=True),patch.object(email_security,'deliver_to') as mail:
            client=self.app.test_client()
            result=self.post(client,'/api/account/register',{'username':'pg-email-user','email':'pg-private@example.test','nickname':'Ol Amigo','password':'postgres-email-password-123'})
            self.assertEqual(result.status_code,201)
            body=mail.call_args.args[2];link=next(line for line in body.splitlines() if line.startswith('https://'));token=parse_qs(urlsplit(link).fragment)['verify-email'][0]
            self.assertEqual(self.post(client,'/api/account/email/confirm',{'token':token}).status_code,200)
            self.assertTrue(client.get('/api/account/me').json['profile']['email_verified'])
            human=client.get('/api/account/human-check').json
            self.assertEqual(self.post(client,'/api/account/password/request',{'email':'pg-private@example.test','human_id':human['id'],'human_answer':'OL234'}).status_code,200)
            body=mail.call_args.args[2];link=next(line for line in body.splitlines() if line.startswith('https://'));token=parse_qs(urlsplit(link).fragment)['reset-password'][0]
            self.assertEqual(self.post(client,'/api/account/password/reset',{'token':token,'password':'postgres-new-email-password-123'}).status_code,200)
            self.assertIsNone(client.get('/api/account/me').json['user'])
            self.assertEqual(self.post(client,'/api/account/login',{'username':'pg-private@example.test','password':'postgres-new-email-password-123'}).status_code,200)

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
                legacy_payment(source,admin,ident,'welcome','SQLITE-MIGRATE-001')
                expected=client.get('/api/account/me').json['user']['access_until']
            with self.app.app_context(),m.database() as connection:
                for table in ['visitor_sessions','visitor_devices','live_channel_thumbnails','community_likes','live_guest_invites','live_broadcast_sessions','live_recordings','community_report_details','interface_revisions','adult_age_declarations','adult_channel_rules','live_channel_views','community_retention_clock','stripe_order_names','annual_access_emails','fan_aliases','stripe_reversals','stripe_events','stripe_orders','stripe_connect_states','stripe_accounts','ol_supervisors','ol_operations','moderator_permissions','two_factor_recovery','member_two_factor','community_audiences','creator_subscriptions','channel_subscription_settings','subscription_approvals','subscription_agreements','pricing_moderators','founder_slot_history','live_launch','creator_daily_activity','founder_activity','live_entitlements','human_challenges','promotion_metrics','founder_signatures','live_founders','live_channel_settings','sticker_designs','member_rewards','admin_notifications','community_messages','streamer_channels','streamer_access','friend_access','payments','invitations','login_attempts','members']:connection.execute('DELETE FROM '+table)
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

    def test_consented_visits_are_private_cascade_and_public_anonymous(self):
        result=self.post(self.client,'/api/visits',{'consent':True,'event':'page','page':'/'})
        self.assertEqual(result.status_code,200);self.assertTrue(result.json['recorded'])
        private=self.admin.get('/api/admin/visits').json
        self.assertEqual(private['summary']['sessions'],1)
        self.assertEqual(private['summary']['registered'],1)
        public=self.app.test_client().get('/api/visits/public').json
        self.assertEqual(public['summary']['sessions'],1)
        self.assertEqual(set(public['visits'][0]),{'at','device','page'})
        self.assertNotIn('pg-client',str(public))
        self.assertEqual(self.client.get('/api/admin/visits').status_code,403)
        self.assertEqual(self.post(self.client,'/api/visits/consent',{'allowed':False}).status_code,200)
        self.assertEqual(self.admin.get('/api/admin/visits').json['total'],0)

if __name__=='__main__':unittest.main(verbosity=2)
