"""Access support works without a session and never emails supplied recipients."""
import hashlib
import os
import secrets
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

import access_help
import membership as members
import notifications


PATH = '/api/account/access-help'


class AccessHelpTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Flask(__name__)
        self.app.secret_key = 'isolated-access-help-session-key'
        self.app.config.update(
            MEMBERSHIP_DATABASE=str(Path(temporary.name) / 'help.sqlite3'),
            MEMBERSHIP_DATABASE_URL=None, MAX_CONTENT_LENGTH=65536,
            TESTING=True,
        )
        with self.app.app_context():
            members.init_database()
        self.app.before_request(members.verify_csrf)
        self.app.before_request(members.restrict_music)
        access_help.install(self.app)
        self.client = self.new_client()
        environment = patch.dict(os.environ, {'VERCEL': '0'})
        environment.start(); self.addCleanup(environment.stop)
        ready = patch.object(notifications, 'mail_ready', return_value=False)
        ready.start(); self.addCleanup(ready.stop)
        delivery = patch.object(notifications, 'deliver_to')
        self.delivery = delivery.start(); self.addCleanup(delivery.stop)

    def new_client(self, member=None):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['csrf'] = 'isolated-csrf-token'
            if member:
                session.update(member_id=member, session_version=0)
        return client

    def member(self, username='known-person', email='known@example.test'):
        ident = secrets.token_hex(16)
        with self.app.app_context(), members.database() as conn:
            instant = members.stamp(members.now_utc())
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (ident, username, 'private-password-hash', instant))
            if email:
                conn.execute('INSERT INTO member_profiles(member_id,email,email_verified,updated_at) VALUES(?,?,1,?)',
                             (ident, email, instant))
        return ident

    def post(self, data=None, client=None, ip='192.0.2.25', path=PATH, headers=None):
        data = {'identifier': 'help-person', 'contact_email': 'contact@example.test',
                'category': 'code', 'details': 'El correo de acceso no llega.'} if data is None else data
        return (client or self.client).post(
            path, json=data,
            headers={'X-CSRF-Token': 'isolated-csrf-token', **(headers or {})},
            environ_overrides={'REMOTE_ADDR': ip},
        )

    def notices(self):
        with self.app.app_context(), members.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM admin_notifications ORDER BY created_at,id').fetchall()]

    def attempts(self):
        with self.app.app_context(), members.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM login_attempts').fetchall()]

    def test_guest_request_is_durable_and_unconfigured_mail_is_queued(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'ok': True, 'delivery': 'queued', 'message': access_help.GENERIC_MESSAGE})
        self.delivery.assert_not_called()
        row = self.notices()[0]
        self.assertEqual((row['kind'], row['status'], row['attempts']), ('access_help', 'pending', 0))
        self.assertRegex(row['event_key'], r'^access-help:[0-9a-f]{32}$')
        self.assertIn('help-person', row['detail'])
        self.assertIn('contact@example.test', row['detail'])
        self.assertNotIn('contact@example.test', response.get_data(as_text=True))
        self.assertEqual(self.client.get(PATH).status_code, 405)

    def test_guest_requires_contact_and_email_identifier_can_supply_it(self):
        response = self.post({'identifier': 'guest-person', 'category': 'other'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.attempts(), [])
        response = self.post({'identifier': ' Person@Example.Test ', 'category': 'password'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Correo de contacto: person@example.test', self.notices()[0]['detail'])

    def test_signed_in_request_uses_only_its_own_profile_and_links_actor(self):
        actor = self.member('actor-person', 'actor@example.test')
        other = self.member('another-person', 'other@example.test')
        response = self.post({'identifier': 'another-person', 'category': 'two_factor'}, client=self.new_client(actor))
        self.assertEqual(response.status_code, 200)
        notice = self.notices()[0]
        self.assertIn('actor@example.test', notice['detail'])
        self.assertNotIn('other@example.test', notice['detail'])
        with self.app.app_context(), members.database() as conn:
            linked = [row['member_id'] for row in conn.execute('SELECT member_id FROM admin_notification_members WHERE notification_id=?', (notice['id'],)).fetchall()]
        self.assertEqual(linked, [actor])
        self.assertNotIn(other, linked)

    def test_signed_in_account_without_email_can_still_request_help(self):
        actor = self.member(email=None)
        response = self.post({'identifier': 'known-person', 'category': 'payment'}, client=self.new_client(actor))
        self.assertEqual(response.status_code, 200)
        self.assertIn('cuenta con sesión iniciada', self.notices()[0]['detail'])

    def test_unknown_and_known_accounts_receive_the_same_result(self):
        self.member()
        known = self.post({'identifier': 'known@example.test', 'category': 'code'})
        unknown = self.post({'identifier': 'absent@example.test', 'category': 'code'})
        self.assertEqual(known.status_code, 200)
        self.assertEqual(known.json, unknown.json)
        self.assertNotEqual(self.notices()[0]['event_key'], self.notices()[1]['event_key'])
        with self.app.app_context(), members.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM admin_notification_members').fetchone()['n'], 0)

    def test_csrf_is_required_for_both_guests_and_signed_in_accounts(self):
        actor = self.member()
        for client in [self.client, self.new_client(actor)]:
            response = client.post(PATH, json={'identifier': 'known@example.test', 'category': 'code'})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json['code'], 'csrf_expired')
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.attempts(), [])

    def test_fields_are_strictly_validated_before_consuming_quota(self):
        base = {'identifier': 'person-name', 'contact_email': 'contact@example.test', 'category': 'other'}
        invalid = [
            {}, [], {'identifier': None}, {'identifier': 17},
            {**base, 'identifier': 'bad name'}, {**base, 'identifier': 'bad@example'},
            {**base, 'identifier': 'a' * 255}, {**base, 'contact_email': []},
            {**base, 'contact_email': 'x@example.test\r\nBcc: bad@example.test'},
            {**base, 'category': 'admin'}, {**base, 'category': {}},
            {**base, 'details': 'x' * 501}, {**base, 'details': {'password': 'never-record-this'}},
            {**base, 'details': 'control\x00character'},
        ]
        invalid += [{**base, key: 'never-record-this'} for key in ('password', 'code', 'token', 'csrf', 'recipient')]
        for data in invalid:
            with self.subTest(data=data):
                self.assertEqual(self.post(data).status_code, 400)
        self.assertEqual(self.notices(), [])
        self.assertEqual(self.attempts(), [])
        for _ in range(3):
            self.assertEqual(self.post(base).status_code, 200)

    def test_bounded_body_and_non_json_are_rejected_without_consuming_quota(self):
        response = self.client.post(PATH, data=b' ' * (access_help.MAX_BODY_BYTES + 1),
                                    content_type='application/json', headers={'X-CSRF-Token': 'isolated-csrf-token'})
        self.assertEqual(response.status_code, 413)
        response = self.client.post(PATH, data='identifier=person',
                                    headers={'X-CSRF-Token': 'isolated-csrf-token'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.attempts(), [])

    def test_all_categories_and_payment_references_are_accepted(self):
        for index, category in enumerate(['code', 'password', 'two_factor', 'payment', 'other']):
            response = self.post({'identifier': 'person@example.test', 'category': category,
                                  'details': 'Recibo de Stripe 123456789012. No aparece mi acceso.'}, ip='192.0.2.' + str(index + 1))
            self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.notices()), 5)

    def test_mail_uses_fixed_owner_recipient_even_with_query_and_contact(self):
        with patch.object(notifications, 'mail_ready', return_value=True):
            response = self.post(path=PATH + '?recipient=attacker@example.test')
        self.assertEqual(response.json['delivery'], 'sent')
        self.delivery.assert_called_once()
        self.assertEqual(self.delivery.call_args.args[0], notifications.RECIPIENT)
        self.assertNotEqual(self.delivery.call_args.args[0], 'contact@example.test')
        self.assertNotIn('attacker@example.test', self.notices()[0]['detail'])
        self.assertEqual(self.notices()[0]['status'], 'sent')

    def test_smtp_failure_preserves_incident_and_reports_queued_for_retry(self):
        with patch.object(notifications, 'mail_ready', return_value=True), patch.object(notifications, 'deliver_to', side_effect=RuntimeError('private-smtp-credential')):
            response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['delivery'], 'queued')
        notice = self.notices()[0]
        self.assertEqual((notice['status'], notice['attempts']), ('failed', 1))
        self.assertNotIn('private-smtp-credential', str(response.json) + notice['detail'])
        with patch.object(notifications, 'mail_ready', return_value=True), self.app.app_context():
            self.assertTrue(notifications.send_one(notice['id']))
        self.assertEqual(self.notices()[0]['status'], 'sent')

    def test_notifier_and_mail_run_after_the_rate_transaction_has_closed(self):
        original = notifications.notify

        def unlocked_notify(*args, **kwargs):
            # A second writer cannot begin if the route still holds its lock.
            conn = sqlite3.connect(self.app.config['MEMBERSHIP_DATABASE'], timeout=0.05)
            try:
                conn.execute('BEGIN IMMEDIATE')
                conn.rollback()
            finally:
                conn.close()
            return original(*args, **kwargs)

        with patch.object(notifications, 'notify', side_effect=unlocked_notify):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(len(self.notices()), 1)

    def test_hard_ip_quota_cannot_be_reset_with_body_cookies_or_forwarded_headers(self):
        self.app.wsgi_app = ProxyFix(self.app.wsgi_app, x_for=1)
        for index in range(3):
            response = self.post({'identifier': 'person-' + str(index), 'contact_email': str(index) + '@example.test',
                                  'category': 'code'}, client=self.new_client(),
                                 headers={'X-Forwarded-For': '198.51.100.' + str(index + 1)})
            self.assertEqual(response.status_code, 200)
        response = self.post(client=self.new_client(), headers={'X-Forwarded-For': '203.0.113.12'})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(len(self.notices()), 3)
        attempts = self.attempts()
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len({row['bucket'] for row in attempts}), 1)
        self.assertRegex(attempts[0]['bucket'], r'^[0-9a-f]{64}$')
        self.assertNotEqual(attempts[0]['bucket'], hashlib.sha256(b'192.0.2.25').hexdigest())
        self.assertNotIn('192.0.2.25', str(attempts))
        self.assertEqual(self.post(ip='192.0.2.26').status_code, 200)

    def test_quota_expires_after_fifteen_minutes(self):
        instant = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
        with patch.object(access_help, 'now_utc', return_value=instant):
            for _ in range(3):
                self.assertEqual(self.post().status_code, 200)
        with patch.object(access_help, 'now_utc', return_value=instant + timedelta(minutes=15, seconds=-1)):
            self.assertEqual(self.post().status_code, 429)
        with patch.object(access_help, 'now_utc', return_value=instant + timedelta(minutes=15)):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(len(self.attempts()), 1)

    def test_concurrent_requests_share_the_same_atomic_quota(self):
        clients = [self.new_client() for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as workers:
            responses = list(workers.map(lambda client: self.post(client=client), clients))
        self.assertEqual(sorted(response.status_code for response in responses), [200] * 3 + [429] * 5)
        self.assertEqual(len(self.notices()), 3)
        self.assertEqual(len(self.attempts()), 3)

    def test_vercel_uses_only_its_edge_owned_address_header(self):
        with patch.dict(os.environ, {'VERCEL': '1'}):
            for _ in range(3):
                self.assertEqual(self.post(headers={'X-Vercel-Forwarded-For': '198.51.100.25'}).status_code, 200)
            self.assertEqual(self.post(ip='192.0.2.26', headers={'X-Vercel-Forwarded-For': '198.51.100.25',
                                                               'X-Forwarded-For': '203.0.113.27'}).status_code, 429)
            self.assertEqual(self.post(headers={'X-Vercel-Forwarded-For': '198.51.100.26'}).status_code, 200)

    def test_server_credentials_and_auth_headers_never_enter_owner_notice(self):
        actor = self.member()
        response = self.post(client=self.new_client(actor), headers={'Authorization': 'Bearer private-auth-token',
                                                                    'X-Access-Code': '654321'})
        self.assertEqual(response.status_code, 200)
        detail = self.notices()[0]['detail']
        for secret in ['private-password-hash', 'private-auth-token', 'isolated-csrf-token',
                       self.app.secret_key, '654321']:
            self.assertNotIn(secret, detail)

    def test_storage_failure_does_not_claim_a_saved_or_queued_request(self):
        with patch.object(notifications, 'notify', side_effect=RuntimeError('private-storage-detail')), self.assertLogs(self.app.logger, level='WARNING') as captured:
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('ok', response.json)
        self.assertNotIn('delivery', response.json)
        self.assertNotIn('private-storage-detail', str(response.json))
        self.assertNotIn('private-storage-detail', str(captured.output))
        self.assertEqual(self.notices(), [])


if __name__ == '__main__':
    unittest.main()
