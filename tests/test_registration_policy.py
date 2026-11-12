"""The real application gate preserves account recovery and stable owner identity."""
from datetime import datetime, timedelta, timezone
import json
import secrets
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as application
import membership as m
import registration_fee as fee
import streamers
from auth_support import authenticated_client


class RegistrationPolicyTests(unittest.TestCase):
    PASSWORD = 'registration-policy-local-password-123'
    MIGRATION = 'owner-account-registration-fee-2026-11-12-v1'

    def setUp(self):
        self.app = application.app
        self.instant = datetime(2031, 2, 3, 12, 0, tzinfo=timezone.utc)
        settings = patch.dict('os.environ', {
            'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0',
            'OL_ACCOUNT_REPORT_EMAILS': '0', 'OL_REGISTRATION_FEE_ENABLED': '1',
        })
        settings.start()
        self.addCleanup(settings.stop)
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        with self.app.app_context():
            streamers.init_database()
        for mocked in [patch.object(fee, 'now_utc', side_effect=lambda: self.instant),
                       patch.object(fee, 'payment_available', return_value=False),
                       patch('email_security.send_security_mail', return_value=False),
                       patch('notifications.notify', return_value=False),
                       patch('membership.notify', return_value=False),
                       patch('notifications.deliver_to', side_effect=AssertionError('No email in policy tests')),
                       patch('requests.request', side_effect=AssertionError('No external HTTP in policy tests'))]:
            result = mocked.start()
            self.addCleanup(mocked.stop)
            if mocked.attribute == 'request':
                self.external_http = result
        self.addCleanup(lambda: self.external_http.assert_not_called())

    def account(self, username, origin='self_service', enrolled=True):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (ident, username, generate_password_hash(self.PASSWORD), m.stamp(self.instant)))
            if enrolled:
                fee.enroll(conn, ident, origin=origin)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(member_id=ident, session_version=0)
        return client, ident

    def post(self, client, path, data):
        token = client.get('/api/account/me').json['csrf']
        return client.post(path, json=data, headers={'X-CSRF-Token': token})

    def marker(self, ident):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM registration_access WHERE member_id=?', (ident,)).fetchone()
            return dict(row) if row else None

    def state(self, ident):
        with self.app.app_context():
            return fee.state(ident)

    def finances(self):
        with self.app.app_context(), m.database() as conn:
            return {table: sorted([dict(row) for row in conn.execute('SELECT * FROM '+table).fetchall()],
                                  key=lambda row: json.dumps(row, sort_keys=True))
                    for table in ['members', 'payments', 'streamer_access', 'live_entitlements']}

    def test_real_video_configuration_gate_allows_grace_and_blocks_at_exact_five_minutes(self):
        client, ident = self.account('gate-participant')
        self.assertEqual(self.app.test_client().get('/api/videos/config').status_code, 200)
        first = client.get('/api/videos/config')
        self.assertEqual(first.status_code, 200, first.json)
        deadline = self.marker(ident)['due_at']
        self.assertEqual(datetime.fromisoformat(deadline), self.instant+timedelta(seconds=300))
        self.instant += timedelta(seconds=299)
        self.assertEqual(client.get('/api/videos/config').status_code, 200)
        self.instant += timedelta(seconds=1)
        for _ in range(2):
            response = client.get('/api/videos/config')
            self.assertEqual(response.status_code, 402, response.json)
            self.assertEqual(response.json['code'], 'registration_fee_required')
            self.assertFalse(response.json['registration_fee']['in_grace'])
            self.assertEqual(self.marker(ident)['due_at'], deadline)
            self.instant += timedelta(seconds=1)

    def test_due_participant_can_still_open_account_update_profile_login_payments_and_help(self):
        client, ident = self.account('recoverable-participant')
        self.assertEqual(client.get('/api/videos/config').status_code, 200)
        self.instant += timedelta(seconds=301)
        self.assertEqual(client.get('/api/videos/config').status_code, 402)
        deadline = self.marker(ident)['due_at']
        for path in ['/account', '/api/account/me', '/api/account/registration-fee', '/api/payments/status']:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.close()
        profile = self.post(client, '/api/account/profile', {
            'password': self.PASSWORD, 'email': '', 'nickname': 'Nuevo apodo',
        })
        self.assertEqual(profile.status_code, 200, profile.json)
        help_response = self.post(client, '/api/account/access-help', {
            'identifier': 'recoverable-participant', 'contact_email': 'contact@example.invalid',
            'category': 'payment', 'details': 'Necesito ayuda para completar el alta.',
        })
        self.assertEqual(help_response.status_code, 200, help_response.json)
        login = self.post(client, '/api/account/login', {
            'username': 'recoverable-participant', 'password': self.PASSWORD,
        })
        self.assertEqual(login.status_code, 200, login.json)
        self.assertEqual(client.get('/api/account/me').status_code, 200)
        self.assertEqual(self.marker(ident)['due_at'], deadline)
        self.assertEqual(client.get('/api/videos/config').status_code, 402)

    def test_first_authenticated_me_request_starts_legacy_grace_once(self):
        client, ident = self.account('legacy-authenticated', enrolled=False)
        self.assertIsNone(self.marker(ident))
        first = client.get('/api/account/me')
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(first.json['user']['id'], ident)
        self.assertTrue(first.json['registration_fee']['required'])
        self.assertEqual(first.json['registration_fee']['grace_seconds'], 300)
        original = self.marker(ident)
        self.assertEqual(original['origin'], 'legacy_unknown')
        self.instant += timedelta(seconds=90)
        second = client.get('/api/account/me')
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json['registration_fee']['grace_seconds'], 210)
        self.assertEqual(self.marker(ident), original)

    def test_owner_invitation_and_friend_grant_still_pay_while_admin_and_active_supervisor_pass(self):
        invitation = self.admin.post('/api/admin/invite', json={'username': 'owner-invited-participant'})
        self.assertEqual(invitation.status_code, 201, invitation.json)
        token = invitation.json['path'].split('#invite=', 1)[1]
        invited = self.app.test_client()
        accepted = self.post(invited, '/api/account/accept-invite', {
            'token': token, 'password': self.PASSWORD,
        })
        self.assertEqual(accepted.status_code, 200, accepted.json)
        invited_id = invited.get('/api/account/me').json['user']['id']
        friend, friend_id = self.account('owner-free-grant')
        grant = self.admin.post('/api/admin/friend-access', json={'member_id': friend_id, 'active': True})
        self.assertEqual(grant.status_code, 200, grant.json)
        half_admin, half_admin_id = self.account('active-half-admin')
        for client in [invited, friend, half_admin]:
            self.assertEqual(client.get('/api/videos/config').status_code, 200)
        self.instant += timedelta(seconds=301)
        for client, ident in [(invited, invited_id), (friend, friend_id)]:
            self.assertFalse(self.state(ident)['exempt'])
            self.assertEqual(client.get('/api/videos/config').status_code, 402)
        self.assertEqual(self.admin.get('/api/videos/config').status_code, 200)
        self.assertEqual(half_admin.get('/api/videos/config').status_code, 402)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO ol_supervisors VALUES(?,?,?,?,NULL)',
                         (half_admin_id, self.admin_id, m.stamp(self.instant), 1))
        self.assertEqual(half_admin.get('/api/videos/config').status_code, 200)
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE ol_supervisors SET revoked_at=?,can_review=0 WHERE member_id=?',
                         (m.stamp(self.instant), half_admin_id))
        self.assertEqual(half_admin.get('/api/videos/config').status_code, 402)

    def test_owner_policy_captures_rosas_once_and_preserves_password_role_and_annual_records(self):
        _, original_id = self.account('rosas', enrolled=False)
        instant = m.stamp(self.instant)
        annual_end = m.stamp(self.instant+timedelta(days=365))
        with self.app.app_context(), m.database() as conn:
            conn.execute('DELETE FROM owner_access_migrations WHERE id=?', (self.MIGRATION,))
            conn.execute("DELETE FROM member_identity_links WHERE identity='rosas'")
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), original_id, 'annual', 2500, instant,
                          annual_end, instant, self.admin_id, 'policy-preserved-annual'))
            conn.execute('INSERT INTO streamer_access VALUES(?,?)', (original_id, annual_end))
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)', (original_id, instant))
        before = self.finances()
        with self.app.app_context():
            m.apply_registration_policy()
        self.assertEqual(self.finances(), before)
        self.assertEqual(self.marker(original_id)['exempt_reason'], 'owner_rosas')
        self.assertTrue(self.state(original_id)['exempt'])
        with self.app.app_context(), m.database() as conn:
            migration = dict(conn.execute('SELECT * FROM owner_access_migrations WHERE id=?', (self.MIGRATION,)).fetchone())
            conn.execute('UPDATE members SET username=? WHERE id=?', ('renamed-stable-owner', original_id))
        self.assertEqual(json.loads(migration['result'])['rosas_member_id'], original_id)
        _, new_id = self.account('rosas')
        after_rename = self.finances()
        with self.app.app_context():
            m.apply_registration_policy()
        self.assertEqual(self.finances(), after_rename)
        self.assertTrue(self.state(original_id)['exempt'])
        self.assertFalse(self.state(new_id)['exempt'])
        self.assertTrue(self.state(new_id)['required'])
        with self.app.app_context(), m.database() as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM owner_access_migrations WHERE id=?', (self.MIGRATION,)).fetchone()), migration)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM owner_access_migrations WHERE id=?', (self.MIGRATION,)).fetchone()['n'], 1)


if __name__ == '__main__':
    unittest.main()
