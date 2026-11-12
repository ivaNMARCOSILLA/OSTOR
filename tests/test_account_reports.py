"""Isolated private account reports: fixed recipient, durable markers, no secrets."""
import json
import secrets
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify

import account_reports as reports
import membership as members
import notifications
import registration_fee


class AccountReportTests(unittest.TestCase):
    def setUp(self):
        enabled=patch.dict('os.environ',{'OL_ACCOUNT_REPORT_EMAILS':'1'});enabled.start();self.addCleanup(enabled.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='isolated-account-report-secret',
                               MEMBERSHIP_DATABASE=str(Path(temporary.name) / 'reports.sqlite3'),
                               MEMBERSHIP_DATABASE_URL=None)
        with self.app.app_context():
            members.init_database()
            registration_fee.init_database()
            reports.init_database()
        reports.install(self.app)
        self.app.before_request(members.verify_csrf)

        @self.app.get('/api/admin/report-test')
        @members.require_admin
        def admin_page():
            return jsonify(ok=True)

        @self.app.get('/public-report-test')
        def public_page():
            return jsonify(ok=True)

        @self.app.post('/api/account/report-test')
        def new_account():
            ident = secrets.token_hex(16)
            with members.database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',
                             (ident, 'automatic-new-account', members.stamp(members.now_utc())))
                reports.queue_account(conn, ident)
            return jsonify(ok=True), 201

        self.ready_patch = patch.object(notifications, 'mail_ready', return_value=False)
        self.ready = self.ready_patch.start()
        self.addCleanup(self.ready_patch.stop)
        self.delivery_patch = patch.object(notifications, 'deliver_to')
        self.delivery = self.delivery_patch.start()
        self.addCleanup(self.delivery_patch.stop)

    def member(self, name, role='member', private_profile=False):
        ident = secrets.token_hex(16)
        with self.app.app_context(), members.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (ident, name, 'never-mail-this-password-hash', role, members.stamp(members.now_utc())))
            if private_profile:
                conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',
                             (ident, name + '@example.test', 'Apodo privado', members.stamp(members.now_utc())))
                conn.execute('INSERT INTO member_legal_names(member_id,legal_name,updated_at) VALUES(?,?,?)',
                             (ident, 'Nombre Legal de Prueba', members.stamp(members.now_utc())))
        return ident

    def client(self, ident):
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(member_id=ident, session_version=0, csrf='isolated-report-csrf')
        return client

    def initial(self):
        with self.app.app_context(), members.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return reports.queue_initial(conn)

    def queue(self, ident, event='registration'):
        with self.app.app_context(), members.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return reports.queue_account(conn, ident, event)

    def rows(self):
        with self.app.app_context(), members.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM account_report_queue ORDER BY event_key').fetchall()]

    def test_schema_never_snapshots_or_sends_mail(self):
        self.member('schema-account')
        with self.app.app_context():
            reports.init_database()
            self.assertEqual(reports.status()['total'], 0)
            self.assertFalse(reports.status()['initial_queued'])
        self.delivery.assert_not_called()

    def test_initial_snapshot_batches_existing_ids_once_and_survives_notice_deletion(self):
        for index in range(205):
            self.member('batch-account-' + str(index))
        self.assertEqual(self.initial(), 3)
        self.assertEqual([len(json.loads(row['body'].split('\n\n', 1)[1])) for row in self.rows()], [100, 100, 5])
        self.member('registered-after-snapshot')
        with self.app.app_context(), members.database() as conn:
            conn.execute('DELETE FROM admin_notifications')
        self.assertEqual(self.initial(), 0)
        with self.app.app_context(), members.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM account_report_members').fetchone()['n'], 205)
            self.assertEqual(reports.status()['initial_accounts'], 205)
        self.assertNotIn('registered-after-snapshot', ''.join(row['body'] for row in self.rows()))

    def test_snapshot_selects_allowed_profile_and_payment_fields_only(self):
        ident = self.member('private-account', private_profile=True)
        owner = self.member('payment-owner', role='admin')
        instant = members.stamp(members.now_utc())
        with self.app.app_context(), members.database() as conn:
            conn.execute('INSERT INTO registration_access(member_id,origin,paid_at) VALUES(?,?,?)', (ident, 'self_service', instant))
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), ident, 'annual', 2500, instant, instant, instant, owner, 'private-payment-reference'))
            conn.execute('INSERT INTO email_tokens VALUES(?,?,?,?,?,?,?)',
                         ('never-mail-this-reset-token-hash', ident, 'reset', 'private-account@example.test', 0, instant, instant))
        self.assertTrue(self.queue(ident))
        body = self.rows()[0]['body']
        for expected in ('private-account@example.test', 'Nombre Legal de Prueba', 'Apodo privado', 'pagada', '2500'):
            self.assertIn(expected, body)
        for secret in ('never-mail-this-password-hash', 'never-mail-this-reset-token-hash', 'private-payment-reference'):
            self.assertNotIn(secret, body)
        self.assertFalse(self.queue(ident))
        self.assertTrue(self.queue(ident, 'activation'))

    def test_initial_summary_does_not_repeat_a_new_account_already_queued(self):
        old_account = self.member('existing-before-summary', private_profile=True)
        new_account = self.member('new-already-reported', private_profile=True)
        self.assertTrue(self.queue(new_account))
        self.assertEqual(self.initial(), 1)
        messages = self.rows()
        self.assertEqual(sum(row['body'].count(old_account) for row in messages), 1)
        self.assertEqual(sum(row['body'].count(new_account) for row in messages), 1)
        self.assertEqual(self.initial(), 0)

    def test_missing_provider_keeps_truthful_pending_state(self):
        self.queue(self.member('pending-account'))
        with self.app.app_context():
            result = reports.flush_pending()
        self.assertEqual(result, {'email_ready': False, 'attempted': 0, 'sent': 0, 'failed': 0, 'pending': 1})
        self.assertEqual(self.rows()[0]['attempts'], 0)
        self.delivery.assert_not_called()

    def test_delivery_uses_only_fixed_recipient_outside_database_lock_and_purges_body(self):
        ident = self.member('delivered-account', private_profile=True)
        self.queue(ident)
        self.ready.return_value = True

        def deliver(recipient, title, body):
            self.assertEqual(recipient, notifications.RECIPIENT)
            self.assertIn('delivered-account@example.test', body)
            # A second writer can acquire the lock while the provider is called.
            with members.database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                conn.execute('UPDATE members SET username=username WHERE id=?', (ident,))
            # A concurrent delivery request must not claim this same message.
            self.assertEqual(reports.flush_pending()['attempted'], 0)

        self.delivery.side_effect = deliver
        with self.app.app_context():
            result = reports.flush_pending()
        self.assertEqual((result['sent'], result['pending']), (1, 0))
        row = self.rows()[0]
        self.assertEqual((row['status'], row['body'], row['attempts']), ('sent', '', 1))
        self.assertFalse(self.queue(ident))

    def test_failed_delivery_retries_without_leaking_provider_error(self):
        self.queue(self.member('retry-account'))
        self.ready.return_value = True
        self.delivery.side_effect = RuntimeError('private-provider-credentials')
        with self.app.app_context():
            result = reports.flush_pending()
            self.assertEqual((result['failed'], result['pending']), (1, 1))
            self.assertNotIn('private-provider-credentials', str(result))
            self.assertEqual(reports.flush_pending()['attempted'], 0)
            self.delivery.side_effect = None
            result = reports.flush_pending(retry_failed=True)
        self.assertEqual((result['sent'], result['pending']), (1, 0))
        self.assertEqual(self.rows()[0]['attempts'], 2)

    def test_stale_delivery_lease_is_recoverable_and_flush_is_bounded(self):
        for index in range(3):
            self.queue(self.member('bounded-account-' + str(index)))
        with self.app.app_context(), members.database() as conn:
            conn.execute("UPDATE account_report_queue SET status='sending',last_attempt=?,lease_token='stale' WHERE event_key=?",
                         (members.stamp(members.now_utc() - timedelta(minutes=11)), self.rows()[0]['event_key']))
        self.ready.return_value = True
        with self.app.app_context():
            result = reports.flush_pending(limit=100)
        self.assertEqual((result['attempted'], result['sent'], result['pending']), (2, 2, 1))

    def test_admin_endpoints_enforce_auth_csrf_rate_and_never_return_profile_bodies(self):
        ident = self.member('api-private-account', private_profile=True)
        self.queue(ident)
        owner = self.member('reports-admin', role='admin')
        admin = self.client(owner)
        self.assertEqual(self.app.test_client().get('/api/admin/account-reports').status_code, 403)
        self.assertEqual(self.client(ident).get('/api/admin/account-reports').status_code, 403)
        self.assertEqual(admin.post('/api/admin/account-reports/send', json={}).status_code, 403)
        result = admin.get('/api/admin/account-reports')
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('api-private-account', result.get_data(as_text=True))
        with patch.object(reports, 'allow_attempt', return_value=False):
            self.assertEqual(admin.post('/api/admin/account-reports/send', json={}, headers={'X-CSRF-Token': 'isolated-report-csrf'}).status_code, 429)
        self.ready.return_value = True
        result = admin.post('/api/admin/account-reports/send', json={'recipient': 'ignored@example.test'}, headers={'X-CSRF-Token': 'isolated-report-csrf'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual((result.json['queued'], result.json['sent'], result.json['pending']), (1, 2, 0))
        self.assertTrue(all(call.args[0] == notifications.RECIPIENT for call in self.delivery.call_args_list))

    def test_real_admin_request_queues_initial_but_public_request_does_not(self):
        owner = self.member('automatic-admin', role='admin')
        self.app.test_client().get('/public-report-test')
        self.assertEqual(self.rows(), [])
        admin = self.client(owner)
        self.assertEqual(admin.get('/api/admin/report-test').status_code, 200)
        self.assertEqual(len(self.rows()), 1)
        self.delivery.assert_not_called()
        self.ready.return_value = True
        admin.get('/api/admin/report-test')
        admin.get('/api/admin/report-test')
        self.assertEqual(self.delivery.call_count, 1)

    def test_new_account_report_is_sent_after_committed_request_without_admin_session(self):
        self.ready.return_value = True
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['csrf'] = 'new-account-test-csrf'
        result = client.post('/api/account/report-test', json={}, headers={'X-CSRF-Token': 'new-account-test-csrf'})
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.delivery.call_count, 1)
        self.assertEqual(self.rows()[0]['status'], 'sent')
        with self.app.app_context():
            self.assertFalse(reports.status()['initial_queued'])


if __name__ == '__main__':
    unittest.main()
