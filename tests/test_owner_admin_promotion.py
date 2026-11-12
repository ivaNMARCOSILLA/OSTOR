"""The owner's one-time grant cannot promote a later or different account."""
from datetime import datetime, timedelta
import json
import secrets
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

import app as application
import membership as m
from auth_support import authenticated_client


class OwnerAdminPromotionTests(unittest.TestCase):
    PASSWORD = 'owner-promotion-existing-password-123'

    def setUp(self):
        settings = patch.dict('os.environ', {'OL_LOGIN_EMAIL_REQUIRED': '0',
            'OL_LOGIN_AUDIT_EMAILS': '0', 'VERCEL': '0', 'VERCEL_ENV': 'development'})
        settings.start(); self.addCleanup(settings.stop)
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        self.cutoff = datetime.fromisoformat(m.OWNER_ADMIN_CUTOFF)

    def account(self, username='adminsiempre', *, role='member', created_at=None,
                activated=True, version=0):
        ident = secrets.token_hex(16)
        password = generate_password_hash(self.PASSWORD) if activated else None
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO members(id,username,password_hash,role,created_at,session_version)
                VALUES(?,?,?,?,?,?)''', (ident, username, password, role,
                created_at or m.stamp(self.cutoff-timedelta(days=1)), version))
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['member_id'] = ident; session['session_version'] = version
        return ident, client

    def migrate(self, vercel='1', environment='production'):
        with self.app.app_context(), patch.dict('os.environ', {
                'VERCEL': vercel, 'VERCEL_ENV': environment}):
            m.apply_owner_admin_migration()

    def row(self, ident):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM members WHERE id=?', (ident,)).fetchone()
            return dict(row) if row else None

    def outcome(self):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM owner_access_migrations WHERE id=?',
                               (m.OWNER_ADMIN_MIGRATION_ID,)).fetchone()
            return json.loads(row['result']) if row else None

    def snapshots(self, tables):
        with self.app.app_context(), m.database() as conn:
            return {table: [dict(row) for row in conn.execute('SELECT * FROM '+table).fetchall()]
                    for table in tables}

    def test_only_existing_target_gets_authority_preserving_password_and_payments(self):
        ident, old_session = self.account(created_at=m.OWNER_ADMIN_CUTOFF)
        other, other_session = self.account('ordinary-participant')
        instant = m.stamp(self.cutoff-timedelta(hours=1))
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',
                         (ident, 'existing-member@example.invalid', 'Sant Miguel', instant))
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), ident, 'annual', 2500, instant,
                          m.stamp(self.cutoff+timedelta(days=365)), instant,
                          self.admin_id, 'OWNER-ADMIN-PRESERVE-PAYMENT'))
        before = self.row(ident); other_before = self.row(other)
        evidence = self.snapshots(['payments', 'member_profiles'])
        self.assertEqual(old_session.get('/api/admin/members').status_code, 403)
        self.migrate()
        after = self.row(ident)
        self.assertEqual(after, before | {'role': 'admin', 'session_version': 1})
        self.assertEqual(self.row(other), other_before)
        self.assertEqual(self.snapshots(['payments', 'member_profiles']), evidence)
        self.assertTrue(check_password_hash(after['password_hash'], self.PASSWORD))
        self.assertEqual(old_session.get('/api/admin/members').status_code, 403)
        self.assertIsNone(old_session.get('/api/account/me').json['user'])
        self.assertEqual(other_session.get('/api/admin/members').status_code, 403)
        csrf = old_session.get('/api/account/me').json['csrf']
        login = old_session.post('/api/account/login', json={
            'username': 'adminsiempre', 'password': self.PASSWORD},
            headers={'X-CSRF-Token': csrf})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(old_session.get('/api/admin/members').status_code, 200)
        self.assertEqual(self.outcome(), {'status': 'granted', 'requested_username': 'adminsiempre',
            'member_id': ident, 'username': 'adminsiempre', 'previous_role': 'member',
            'role': 'admin', 'session_revoked': True})

    def test_enabled_two_factor_and_other_access_records_are_untouched(self):
        ident, _ = self.account()
        instant = m.stamp(self.cutoff-timedelta(hours=2))
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO member_two_factor(member_id,nonce,enabled_at,key_id,last_counter)
                VALUES(?,?,?,?,?)''', (ident, 'existing-encrypted-authenticator-fixture',
                                      instant, 'existing-key-fixture', 42))
            conn.execute('INSERT INTO two_factor_recovery(member_id,code_hash,used_at) VALUES(?,?,NULL)',
                         (ident, 'existing-recovery-hash-fixture'))
            conn.execute('INSERT INTO friend_access(member_id,granted_at,granted_by) VALUES(?,?,?)',
                         (ident, instant, self.admin_id))
        tables = ['member_two_factor', 'two_factor_recovery', 'friend_access',
                  'service_grants', 'streamer_access', 'live_entitlements', 'payments']
        before = self.snapshots(tables)
        self.migrate()
        self.assertEqual(self.row(ident)['role'], 'admin')
        self.assertEqual(self.snapshots(tables), before)

    def test_preview_development_and_non_vercel_do_not_write_a_result(self):
        ident, _ = self.account()
        before = self.row(ident)
        for vercel, environment in [('0', 'production'), ('1', 'preview'),
                                    ('1', 'development'), ('', '')]:
            with self.subTest(vercel=vercel, environment=environment):
                self.migrate(vercel, environment)
                self.assertEqual(self.row(ident), before)
                self.assertIsNone(self.outcome())

    def test_missing_account_is_not_created_or_promoted_on_a_later_registration(self):
        self.migrate()
        self.assertEqual(self.outcome()['status'], 'skipped_missing_existing_account')
        with self.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT id FROM members WHERE username=?', ('adminsiempre',)).fetchone())
        ident, _ = self.account()
        self.migrate()
        self.assertEqual(self.row(ident)['role'], 'member')
        self.assertEqual(self.row(ident)['session_version'], 0)
        self.assertEqual(self.outcome()['status'], 'skipped_missing_existing_account')

    def test_archived_unactivated_new_unknown_date_and_unexpected_role_are_skipped(self):
        cases = [
            ('archived', {}, 'skipped_archived_account'),
            ('unactivated', {'activated': False}, 'skipped_unactivated_account'),
            ('future', {'created_at': m.stamp(self.cutoff+timedelta(microseconds=1))}, 'skipped_new_or_unknown_account'),
            ('unknown_date', {'created_at': 'unknown-fixture-date'}, 'skipped_new_or_unknown_account'),
            ('naive_date', {'created_at': '2026-11-12T12:00:00'}, 'skipped_new_or_unknown_account'),
            ('unexpected_role', {'role': 'moderator'}, 'skipped_unexpected_role'),
        ]
        for name, options, expected in cases:
            with self.subTest(case=name):
                ident, _ = self.account(**options)
                if name == 'archived':
                    with self.app.app_context(), m.database() as conn:
                        conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)',
                            (ident, m.stamp(self.cutoff), self.admin_id, 'fixture_archived'))
                before = self.row(ident)
                self.migrate()
                self.assertEqual(self.row(ident), before)
                self.assertEqual(self.outcome()['status'], expected)
                # A skipped account cannot become eligible at a later restart.
                with self.app.app_context(), m.database() as conn:
                    conn.execute('DELETE FROM member_archives WHERE member_id=?', (ident,))
                    conn.execute("UPDATE members SET role='member',created_at=?,password_hash=? WHERE id=?",
                                 (m.stamp(self.cutoff-timedelta(days=1)), generate_password_hash(self.PASSWORD), ident))
                self.migrate()
                self.assertEqual(self.row(ident)['role'], 'member')
                self.assertEqual(self.outcome()['status'], expected)
                # Each subtest starts with a different isolated fixture subject.
                with self.app.app_context(), m.database() as conn:
                    conn.execute('DELETE FROM members WHERE id=?', (ident,))
                    conn.execute('DELETE FROM owner_access_migrations WHERE id=?', (m.OWNER_ADMIN_MIGRATION_ID,))

    def test_existing_admin_keeps_current_sessions(self):
        ident, client = self.account(role='admin', version=7)
        before = self.row(ident)
        self.assertEqual(client.get('/api/admin/members').status_code, 200)
        self.migrate()
        self.assertEqual(self.row(ident), before)
        self.assertEqual(client.get('/api/admin/members').status_code, 200)
        self.assertEqual(self.outcome()['status'], 'already_admin')
        self.assertNotIn('session_revoked', self.outcome())

    def test_grant_is_not_reapplied_after_revocation_or_name_reuse(self):
        original, _ = self.account()
        replacement, _ = self.account('another-old-account')
        self.migrate()
        first_outcome = self.outcome()
        with self.app.app_context(), m.database() as conn:
            conn.execute("UPDATE members SET username='former-target',role='member',session_version=session_version+1 WHERE id=?", (original,))
            conn.execute("UPDATE members SET username='adminsiempre' WHERE id=?", (replacement,))
        self.migrate(); self.migrate()
        self.assertEqual(self.row(original)['role'], 'member')
        self.assertEqual(self.row(original)['session_version'], 2)
        self.assertEqual(self.row(replacement)['role'], 'member')
        self.assertEqual(self.row(replacement)['session_version'], 0)
        self.assertEqual(self.outcome(), first_outcome)
        with self.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM owner_access_migrations WHERE id=?',
                                         (m.OWNER_ADMIN_MIGRATION_ID,)).fetchone()['n'], 1)

    def test_old_account_renamed_after_authorization_is_not_promoted(self):
        ident, _ = self.account()
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_name_history VALUES(?,?,?,?,?,?)',
                (secrets.token_hex(16), ident, self.admin_id, 'former-unrelated-name',
                 'adminsiempre', m.stamp(self.cutoff+timedelta(seconds=1))))
        before = self.row(ident)
        self.migrate()
        self.assertEqual(self.row(ident), before)
        self.assertEqual(self.outcome()['status'], 'skipped_renamed_account')


if __name__ == '__main__':
    unittest.main()
