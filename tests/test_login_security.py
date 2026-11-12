"""Email proof gates sessions; the private audit never contains authentication secrets."""
import os
import re
import secrets
import unittest
from datetime import timedelta
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as application
import login_security as security
import membership as members
from auth_support import authenticated_client


PASSWORD = 'isolated-email-login-password-123'


class EmailLoginSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = application.app
        legacy = patch.dict(os.environ, {'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0'})
        legacy.start(); self.addCleanup(legacy.stop)
        self.admin = authenticated_client(self.app, self.addCleanup)
        strict = patch.dict(os.environ, {'OL_LOGIN_EMAIL_REQUIRED': '1', 'OL_LOGIN_AUDIT_EMAILS': '0'})
        strict.start(); self.addCleanup(strict.stop)
        self.messages = []
        for target, kwargs in [
            ('email_security.mail_ready', {'return_value': True}),
            ('email_security.deliver_to', {'side_effect': lambda recipient, title, body: self.messages.append((recipient, title, body))}),
        ]:
            mock = patch(target, **kwargs); mock.start(); self.addCleanup(mock.stop)
        self.member_id = self.create_member('email-person', 'person@example.test')
        self.client = self.app.test_client()

    def create_member(self, username, email=None):
        ident = secrets.token_hex(16)
        with self.app.app_context(), members.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (ident, username, generate_password_hash(PASSWORD), members.stamp(members.now_utc())))
            if email:
                conn.execute('INSERT INTO member_profiles(member_id,email,email_verified,updated_at) VALUES(?,?,1,?)',
                             (ident, email, members.stamp(members.now_utc())))
        return ident

    def post(self, client, path, data):
        csrf = client.get('/api/account/me').json['csrf']
        return client.post(path, json=data, headers={'X-CSRF-Token': csrf})

    def start(self, client=None, username='email-person', **extra):
        return self.post(client or self.client, '/api/account/login',
                         {'username': username, 'password': PASSWORD, **extra})

    def code(self):
        return re.search(r'(?<!\d)(\d{6})(?!\d)', self.messages[-1][2]).group(1)

    def verify(self, challenge, code=None, client=None):
        return self.post(client or self.client, '/api/account/login/verify',
                         {'challenge_id': challenge, 'code': code or self.code()})

    def test_password_does_not_create_session_and_code_is_single_use(self):
        response = self.start()
        self.assertEqual(response.status_code, 202)
        challenge = response.json['challenge_id']; code = self.code()
        self.assertIsNone(self.client.get('/api/account/me').json['user'])
        self.assertNotIn(code, response.get_data(as_text=True))
        with self.app.app_context(), members.database() as conn:
            row = conn.execute('SELECT * FROM security_login_challenges WHERE id=?', (challenge,)).fetchone()
            self.assertNotEqual(row['code_hash'], code)
        self.assertEqual(self.verify(challenge, code).status_code, 200)
        self.assertEqual(self.client.get('/api/account/me').json['user']['id'], self.member_id)
        self.assertEqual(self.verify(challenge, code).status_code, 401)

    def test_wrong_password_does_not_send_code(self):
        response = self.post(self.client, '/api/account/login', {'username': 'email-person', 'password': 'wrong'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.messages, [])
        self.assertIsNone(self.client.get('/api/account/me').json['user'])

    def test_supplied_address_never_replaces_existing_recipient(self):
        self.assertEqual(self.start(verification_email='different@example.test').status_code, 202)
        self.assertEqual(self.messages[-1][0], 'person@example.test')

    def test_first_email_enrollment_requires_password_and_code(self):
        ident = self.create_member('first-email')
        self.assertEqual(self.start(username='first-email').json['code'], 'verification_email_required')
        response = self.start(username='first-email', verification_email='first@example.test')
        self.assertEqual(response.status_code, 202)
        with self.app.app_context(), members.database() as conn:
            self.assertIsNone(conn.execute('SELECT email FROM member_profiles WHERE member_id=?', (ident,)).fetchone())
        self.assertEqual(self.verify(response.json['challenge_id']).status_code, 200)
        with self.app.app_context(), members.database() as conn:
            row = conn.execute('SELECT email,email_verified FROM member_profiles WHERE member_id=?', (ident,)).fetchone()
            self.assertEqual(row['email'], 'first@example.test'); self.assertEqual(row['email_verified'], 1)

    def test_code_cannot_be_used_in_another_browser(self):
        response = self.start(); challenge = response.json['challenge_id']; code = self.code()
        other = self.app.test_client()
        self.assertEqual(self.verify(challenge, code, other).status_code, 401)
        self.assertIsNone(other.get('/api/account/me').json['user'])
        self.assertEqual(self.verify(challenge, code).status_code, 200)

    def test_expired_code_does_not_grant_access(self):
        response = self.start(); challenge = response.json['challenge_id']
        with self.app.app_context(), members.database() as conn:
            conn.execute('UPDATE security_login_challenges SET expires_at=? WHERE id=?',
                         (members.stamp(members.now_utc()-timedelta(seconds=1)), challenge))
        self.assertEqual(self.verify(challenge).status_code, 401)
        self.assertIsNone(self.client.get('/api/account/me').json['user'])

    def test_session_version_change_invalidates_pending_code(self):
        response = self.start(); challenge = response.json['challenge_id']
        with self.app.app_context(), members.database() as conn:
            conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?', (self.member_id,))
        self.assertEqual(self.verify(challenge).status_code, 401)

    def test_removing_existing_email_invalidates_its_pending_code(self):
        response = self.start(); challenge = response.json['challenge_id']
        with self.app.app_context(), members.database() as conn:
            conn.execute('UPDATE member_profiles SET email=NULL,email_verified=0 WHERE member_id=?', (self.member_id,))
        self.assertEqual(self.verify(challenge).status_code, 401)
        with self.app.app_context(), members.database() as conn:
            self.assertIsNone(conn.execute('SELECT email FROM member_profiles WHERE member_id=?', (self.member_id,)).fetchone()['email'])

    def test_five_wrong_codes_exhaust_the_challenge(self):
        response = self.start(); challenge = response.json['challenge_id']; code = self.code()
        wrong = '000000' if code != '000000' else '111111'
        for _ in range(5):
            self.assertEqual(self.verify(challenge, wrong).status_code, 401)
        self.assertEqual(self.verify(challenge, code).status_code, 401)

    def test_resend_is_throttled_and_invalidates_the_previous_code(self):
        with patch('login_security.secrets.randbelow', side_effect=[123456, 654321]):
            response = self.start(); challenge = response.json['challenge_id']; old = self.code()
            self.assertEqual(self.post(self.client, '/api/account/login/resend', {'challenge_id': challenge}).status_code, 429)
            with self.app.app_context(), members.database() as conn:
                conn.execute('UPDATE security_login_challenges SET last_sent_at=? WHERE id=?',
                             (members.stamp(members.now_utc()-timedelta(seconds=61)), challenge))
            # The throttled call draws a code before checking its cooldown.
        with patch('login_security.secrets.randbelow', return_value=987654):
            self.assertEqual(self.post(self.client, '/api/account/login/resend', {'challenge_id': challenge}).status_code, 202)
        self.assertEqual(self.verify(challenge, old).status_code, 401)
        self.assertEqual(self.verify(challenge).status_code, 200)

    def test_unavailable_or_failed_mail_never_falls_back_to_password_login(self):
        with patch('email_security.mail_ready', return_value=False):
            self.assertEqual(self.start().status_code, 503)
        self.assertIsNone(self.client.get('/api/account/me').json['user'])
        with patch('email_security.deliver_to', side_effect=RuntimeError('isolated mail unavailable')):
            self.assertEqual(self.start().status_code, 503)
        self.assertIsNone(self.client.get('/api/account/me').json['user'])

    def test_cancel_invalidates_the_pending_code(self):
        response = self.start(); challenge = response.json['challenge_id']; code = self.code()
        self.assertEqual(self.post(self.client, '/api/account/login/cancel', {}).status_code, 200)
        self.assertEqual(self.verify(challenge, code).status_code, 401)

    def test_audit_is_private_masked_and_has_no_authentication_secrets(self):
        response = self.start(); code = self.code()
        self.verify(response.json['challenge_id'], code)
        self.assertEqual(self.app.test_client().get('/api/admin/login-audit').status_code, 403)
        self.assertEqual(self.client.get('/api/admin/login-audit').status_code, 403)
        audit = self.admin.get('/api/admin/login-audit')
        self.assertEqual(audit.status_code, 200)
        text = audit.get_data(as_text=True)
        for secret in [PASSWORD, code, 'person@example.test', '127.0.0.1', 'code_hash', 'binding_hash']:
            self.assertNotIn(secret, text)
        self.assertGreaterEqual(audit.json['total'], 2)

    def test_audit_delivery_failure_is_persisted_and_can_be_retried(self):
        self.start()
        with patch('notifications.mail_ready', return_value=True), patch('notifications.deliver', side_effect=RuntimeError('offline')):
            result = self.post(self.admin, '/api/admin/login-audit/retry-email', {})
        self.assertEqual(result.status_code, 200); self.assertGreater(result.json['failed'], 0)
        delivered = []
        with patch('notifications.mail_ready', return_value=True), patch('notifications.deliver', side_effect=lambda title, body: delivered.append(body)):
            result = self.post(self.admin, '/api/admin/login-audit/retry-email', {})
        self.assertGreater(result.json['sent'], 0)
        self.assertNotIn(self.code(), '\n'.join(delivered))
        self.assertEqual(result.json['pending'], 0)

    def test_csrf_and_oversized_metadata_are_denied_and_audited(self):
        response = self.client.post('/api/account/login', json={'username': 'email-person', 'password': PASSWORD})
        self.assertEqual(response.status_code, 403)
        response = self.post(self.client, '/api/account/login', {'username': 'email-person', 'padding': 'x'*70000})
        self.assertEqual(response.status_code, 413)
        self.assertIsNone(self.client.get('/api/account/me').json['user'])
        self.assertGreater(self.admin.get('/api/admin/login-audit').json['total'], 0)


if __name__ == '__main__':
    unittest.main()
