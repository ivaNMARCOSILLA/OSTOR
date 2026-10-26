import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from legacy_support import legacy_payment
import app as application
import membership as m


class MembershipTests(unittest.TestCase):
    def setUp(self):
        ready=patch('streamers.streamer_sales_ready',return_value=True);ready.start();self.addCleanup(ready.stop)
        self.app = application.app
        self.temp = tempfile.TemporaryDirectory()
        self.original = self.app.config['MEMBERSHIP_DATABASE']
        original_url = self.app.config.get('MEMBERSHIP_DATABASE_URL')
        self.app.config['MEMBERSHIP_DATABASE_URL'] = None
        self.addCleanup(lambda: self.app.config.update(MEMBERSHIP_DATABASE_URL=original_url))
        self.app.config['MEMBERSHIP_DATABASE'] = str(Path(self.temp.name) / 'members.sqlite3')
        self.addCleanup(lambda: self.app.config.update(MEMBERSHIP_DATABASE=self.original))
        self.addCleanup(self.temp.cleanup)
        with self.app.app_context():
            m.init_database(); m.create_admin('admin-test', 'admin-test-password-123')
        self.admin = self.app.test_client(); self.client = self.app.test_client()
        self.post(self.admin, '/api/account/login', {'username':'admin-test','password':'admin-test-password-123'})
        self.post(self.client, '/api/account/register', {'username':'member-test','password':'member-test-password-123','role':'admin','access_until':'2099-01-01'})
        self.member = self.client.get('/api/account/me').json['user']

    def post(self, client, path, data):
        if path=='/api/account/register':
         from registration_support import registration_data
         data=registration_data(client,data)
        token = client.get('/api/account/me').json['csrf']
        return client.post(path, json=data, headers={'X-CSRF-Token':token})

    def grant(self, plan, reference='PAYPAL-TEST-001'):
        return legacy_payment(self.app,self.admin,self.member['id'],plan,reference)

    def test_music_is_free_but_ol_live_cannot_be_self_granted(self):
        self.assertEqual(self.member['role'],'member');self.assertFalse(self.member['active'])
        self.assertEqual(self.client.get('/api/resolve/audius_test').status_code,200)
        self.assertEqual(self.client.get('/api/streamers').status_code,402)
        self.assertEqual(self.post(self.client,'/api/admin/confirm-payment',{}).status_code,403)

    def test_legacy_welcome_period_and_history_are_preserved(self):
        instant = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
        with patch.object(m, 'now_utc', return_value=instant):
            result=self.grant('welcome')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json['access_until'], m.stamp(instant+timedelta(days=14)))
            self.assertEqual(self.client.get('/').status_code, 200)
            self.assertEqual(self.grant('welcome','PAYPAL-TEST-002').status_code, 409)
            with self.app.app_context(),m.database() as conn:
                self.assertEqual(conn.execute('SELECT amount_cents FROM payments').fetchone()[0],100)

    def test_legacy_month_end_calculation_is_preserved(self):
        instant = datetime(2027, 1, 31, 12, tzinfo=timezone.utc)
        with patch.object(m, 'now_utc', return_value=instant):
            result=self.grant('monthly')
            self.assertEqual(result.json['access_until'],'2027-02-28T12:00:00+00:00')
            result=self.grant('monthly','PAYPAL-TEST-002')
            self.assertEqual(result.json['access_until'],'2027-03-28T12:00:00+00:00')
            self.assertEqual(self.grant('monthly','PAYPAL-TEST-002').status_code,409)

    def test_expiry_is_enforced_without_browser_cooperation(self):
        instant=datetime(2026,10,25,12,tzinfo=timezone.utc)
        with patch.object(m,'now_utc',return_value=instant): self.grant('welcome')
        with patch.object(m,'now_utc',return_value=instant+timedelta(days=14)):
            self.assertFalse(self.client.get('/api/account/me').json['user']['active'])
            self.assertEqual(self.client.get('/api/streamers').status_code,402)

    def test_revoke_invalidates_another_device_session(self):
        self.grant('monthly')
        device=self.app.test_client()
        self.assertEqual(self.post(device,'/api/account/login',{'username':'member-test','password':'member-test-password-123'}).status_code,200)
        self.assertEqual(device.get('/').status_code,200)
        self.post(self.admin,'/api/admin/revoke',{'member_id':self.member['id']})
        self.assertIsNone(device.get('/api/account/me').json['user'])
        self.assertIsNone(self.client.get('/api/account/me').json['user'])
        self.assertEqual(device.get('/api/streamers').status_code,401)

    def test_admin_multi_device_login(self):
        device=self.app.test_client()
        self.assertEqual(self.post(device,'/api/account/login',{'username':'admin-test','password':'admin-test-password-123'}).status_code,200)
        self.assertEqual(device.get('/api/admin/members').status_code,200)
        self.assertEqual(self.admin.get('/api/admin/members').status_code,200)

    def test_invite_single_use_grants_free_friend_access(self):
        result=self.post(self.admin,'/api/admin/invite',{'username':'friend-test'})
        token=result.json['path'].split('=',1)[1]
        friend=self.app.test_client()
        result=self.post(friend,'/api/account/accept-invite',{'token':token,'password':'friend-password-123'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(friend.get('/api/account/me').json['user']['role'],'member')
        self.assertTrue(friend.get('/api/account/me').json['user']['active'])
        self.assertTrue(friend.get('/api/account/me').json['user']['complimentary'])
        self.assertEqual(friend.get('/api/account/me').json['payments'],[])
        self.assertEqual(friend.get('/api/admin/members').status_code,403)
        self.assertEqual(self.post(friend,'/api/account/accept-invite',{'token':token,'password':'friend-password-123'}).status_code,400)

    def test_csrf_login_checks_and_private_cache(self):
        self.assertEqual(self.admin.post('/api/admin/confirm-payment',json={}).status_code,403)
        self.assertEqual(self.app.test_client().get('/api/admin/members').status_code,403)
        self.assertEqual(self.app.test_client().get('/account').headers['Cache-Control'],'no-store')
        self.assertEqual(self.admin.get('/').headers['Cache-Control'],'no-store')
        self.assertEqual(self.post(self.client,'/api/account/login',{'username':'member-test','password':'wrong'}).status_code,401)

    def test_payment_reference_cannot_be_reused_on_another_user(self):
        self.grant('monthly')
        other=self.app.test_client();self.post(other,'/api/account/register',{'username':'another-test','password':'another-password-123'})
        ident=other.get('/api/account/me').json['user']['id']
        result=legacy_payment(self.app,self.admin,ident,'monthly','PAYPAL-TEST-001')
        self.assertEqual(result.status_code,409)
        self.assertFalse(other.get('/api/account/me').json['user']['active'])

    def test_free_friend_grant_revoke_and_history_are_independent(self):
        result=self.post(self.admin,'/api/admin/invite',{'username':'friend-history'})
        token=result.json['path'].split('=',1)[1];friend=self.app.test_client()
        self.post(friend,'/api/account/accept-invite',{'token':token,'password':'friend-password-123'})
        ident=friend.get('/api/account/me').json['user']['id']
        history=self.admin.get('/api/admin/invitations').json
        self.assertEqual(history['total'],1)
        self.assertNotIn('token_hash',history['invitations'][0])
        self.assertEqual(self.post(self.admin,'/api/admin/invitations/clear',{'completed':True}).status_code,200)
        self.assertTrue(friend.get('/api/account/me').json['user']['complimentary'])
        self.assertEqual(self.post(friend,'/api/admin/friend-access',{'member_id':ident,'active':True}).status_code,403)
        self.assertEqual(self.post(self.admin,'/api/admin/friend-access',{'member_id':ident,'active':False}).status_code,200)
        with self.app.app_context():m.init_database()
        self.post(friend,'/api/account/login',{'username':'friend-history','password':'friend-password-123'})
        self.assertFalse(friend.get('/api/account/me').json['user']['active'])
        self.assertEqual(friend.get('/api/account/me').json['payments'],[])

    def test_legacy_friend_invites_gain_access_but_revoked_accounts_do_not(self):
        self.post(self.client,'/api/account/register',{'username':'legacy-friend','password':'legacy-friend-password-123'})
        ident=self.client.get('/api/account/me').json['user']['id']
        with self.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO invitations(token_hash,member_id,expires_at,used_at) VALUES(?,?,?,?)',('legacy-token-hash',ident,'2000-01-01','2000-01-01'))
        with self.app.app_context():m.init_database()
        self.assertTrue(self.client.get('/api/account/me').json['user']['complimentary'])
        self.post(self.admin,'/api/admin/revoke',{'member_id':ident})
        with self.app.app_context():m.init_database()
        self.post(self.client,'/api/account/login',{'username':'legacy-friend','password':'legacy-friend-password-123'})
        self.assertFalse(self.client.get('/api/account/me').json['user']['active'])

    def test_pending_friend_invitation_can_be_reissued_without_resetting_active_accounts(self):
        first=self.post(self.admin,'/api/admin/invite',{'username':'reissued-friend'}).json['path'].split('=',1)[1]
        second=self.post(self.admin,'/api/admin/invite',{'username':'reissued-friend'}).json['path'].split('=',1)[1]
        client=self.app.test_client()
        self.assertEqual(self.post(client,'/api/account/accept-invite',{'token':first,'password':'reissued-password-123'}).status_code,400)
        self.assertEqual(self.post(client,'/api/account/accept-invite',{'token':second,'password':'reissued-password-123'}).status_code,200)
        self.assertTrue(client.get('/api/account/me').json['user']['complimentary'])
        self.assertEqual(self.post(self.admin,'/api/admin/invite',{'username':'reissued-friend'}).status_code,409)
