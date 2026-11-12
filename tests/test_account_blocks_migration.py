"""The owner's targeted block binds one existing identity and preserves evidence."""
from datetime import datetime, timedelta
import json
import secrets
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash, generate_password_hash

import app as application
import account_blocks as blocks
import membership as m
import streamers
from auth_support import authenticated_client


class AccountBlockMigrationTests(unittest.TestCase):
    PASSWORD = 'account-block-existing-password-123'

    def setUp(self):
        settings = patch.dict('os.environ', {
            'VERCEL': '0', 'VERCEL_ENV': 'development',
            'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0',
            'OL_ACCOUNT_REPORT_EMAILS': '0', 'OL_REGISTRATION_FEE_ENABLED': '0',
            'LIVEKIT_URL': '', 'LIVEKIT_API_KEY': '', 'LIVEKIT_API_SECRET': '',
            'MAGGY_STREAMERS_ENABLED': '0',
        })
        settings.start()
        self.addCleanup(settings.stop)
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        with self.app.app_context():
            streamers.init_database()
            blocks.init_database()
        self.cutoff = datetime.fromisoformat(blocks.OWNER_BLOCK_CUTOFF)
        for mocked in [patch('notifications.deliver_to', side_effect=AssertionError('No email in block tests')),
                       patch('requests.request', side_effect=AssertionError('No external HTTP in block tests'))]:
            result = mocked.start()
            self.addCleanup(mocked.stop)
            if mocked.attribute == 'request':
                self.http = result
        self.addCleanup(lambda: self.http.assert_not_called())

    def account(self, username='loladrones', role='member', created_at=None,
                activated=True, version=0):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO members
                (id,username,password_hash,role,created_at,session_version)
                VALUES(?,?,?,?,?,?)''',
                         (ident, username, generate_password_hash(self.PASSWORD) if activated else None,
                          role, created_at or m.stamp(self.cutoff-timedelta(days=1)), version))
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(member_id=ident, session_version=version)
        return ident, client

    def migrate(self, vercel='1', environment='production'):
        with self.app.app_context(), patch.dict('os.environ', {
                'VERCEL': vercel, 'VERCEL_ENV': environment}):
            blocks.apply_owner_block_migration()

    def row(self, table, ident, key='member_id'):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM '+table+' WHERE '+key+'=?', (ident,)).fetchone()
            return dict(row) if row else None

    def outcome_row(self):
        return self.row('owner_access_migrations', blocks.OWNER_BLOCK_MIGRATION_ID, 'id')

    def outcome(self):
        row = self.outcome_row()
        return json.loads(row['result']) if row else None

    def blocked(self, ident):
        with self.app.app_context(), m.database() as conn:
            return blocks.is_blocked(conn, ident)

    def snapshot(self, tables):
        with self.app.app_context(), m.database() as conn:
            return {table: sorted([dict(row) for row in conn.execute('SELECT * FROM '+table).fetchall()],
                                  key=lambda row: json.dumps(row, sort_keys=True))
                    for table in tables}

    def privileges(self, ident, number=1):
        instant = m.stamp(self.cutoff-timedelta(hours=1))
        expiry = m.stamp(self.cutoff+timedelta(days=365))
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET access_until=? WHERE id=?', (expiry, ident))
            conn.execute('INSERT INTO pricing_moderators VALUES(?,?,?,NULL)', (ident, self.admin_id, instant))
            conn.execute('INSERT INTO moderator_permissions VALUES(?,?,?,?)',
                         (ident, 'approve_agreements', self.admin_id, instant))
            conn.execute('INSERT INTO ol_supervisors VALUES(?,?,?,?,NULL)', (ident, self.admin_id, instant, 1))
            conn.execute('INSERT INTO service_grants VALUES(?,?,?,NULL)', (ident, instant, self.admin_id))
            conn.execute('INSERT INTO friend_access VALUES(?,?,?,NULL)', (ident, instant, self.admin_id))
            conn.execute('INSERT INTO streamer_access VALUES(?,?)', (ident, expiry))
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)', (ident, instant))
            conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)', (ident, number, instant))
            conn.execute('INSERT INTO founder_ownership(member_id,number,assigned_at) VALUES(?,?,?)', (ident, number, instant))
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), ident, 'annual', 2500, instant,
                          expiry, instant, self.admin_id, 'preserve-block-payment-'+ident))
            notice = secrets.token_hex(16)
            conn.execute('''INSERT INTO admin_notifications
                (id,kind,title,detail,event_key,created_at,status) VALUES(?,?,?,?,?,?,?)''',
                         (notice, 'payment', 'Historial conservado', 'Evidencia del pago',
                          'block-notice-'+ident, instant, 'pending'))
            conn.execute('INSERT INTO admin_notification_members VALUES(?,?)', (notice, ident))
        return expiry

    def channel(self, ident, live=True):
        channel_id = secrets.token_hex(16)
        room = 'old-block-room-'+channel_id
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO streamer_channels
                (id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)''',
                         (channel_id, ident, 'Canal previo', room,
                          m.stamp(self.cutoff+timedelta(days=1)) if live else None,
                          m.stamp(self.cutoff)))
        return channel_id, room

    def test_development_preview_and_missing_vercel_flag_have_no_effects(self):
        ident, _ = self.account(role='admin')
        before = self.snapshot(['members', 'account_blocks', 'account_block_livekit_jobs',
                                'member_archives', 'owner_access_migrations'])
        for vercel, environment in [('0', 'production'), ('1', 'preview'), ('1', 'development')]:
            with self.subTest(vercel=vercel, environment=environment):
                self.migrate(vercel, environment)
                self.assertFalse(self.blocked(ident))
                self.assertEqual(before, self.snapshot(list(before)))

    def test_missing_account_is_recorded_once_and_does_not_target_later_registration(self):
        self.migrate()
        self.assertEqual(self.outcome()['status'], 'skipped_missing_existing_account')
        marker = self.outcome_row()
        ident, _ = self.account(created_at=blocks.OWNER_BLOCK_CUTOFF)
        before = self.row('members', ident, 'id')
        self.migrate()
        self.assertEqual(self.outcome_row(), marker)
        self.assertFalse(self.blocked(ident))
        self.assertEqual(self.row('members', ident, 'id'), before)

    def test_future_naive_and_malformed_creation_dates_skip_without_retrospective_retry(self):
        ident, _ = self.account()
        values = [m.stamp(self.cutoff+timedelta(seconds=1)),
                  self.cutoff.replace(tzinfo=None).isoformat(), 'unknown-created-at']
        for created_at in values:
            with self.subTest(created_at=created_at):
                with self.app.app_context(), m.database() as conn:
                    conn.execute('DELETE FROM owner_access_migrations WHERE id=?', (blocks.OWNER_BLOCK_MIGRATION_ID,))
                    conn.execute('UPDATE members SET created_at=? WHERE id=?', (created_at, ident))
                self.migrate()
                self.assertEqual(self.outcome()['status'], 'skipped_new_or_unknown_account')
                self.assertFalse(self.blocked(ident))
                marker = self.outcome_row()
                with self.app.app_context(), m.database() as conn:
                    conn.execute('UPDATE members SET created_at=? WHERE id=?',
                                 (m.stamp(self.cutoff-timedelta(days=1)), ident))
                self.migrate()
                self.assertEqual(self.outcome_row(), marker)
                self.assertFalse(self.blocked(ident))

    def test_account_renamed_to_requested_name_after_cutoff_is_not_blocked(self):
        ident, _ = self.account()
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO member_name_history
                (id,member_id,actor_id,former_username,new_username,changed_at) VALUES(?,?,?,?,?,?)''',
                         (secrets.token_hex(16), ident, self.admin_id, 'another-person',
                          'loladrones', m.stamp(self.cutoff+timedelta(seconds=1))))
        before = self.row('members', ident, 'id')
        self.migrate()
        self.assertEqual(self.outcome()['status'], 'skipped_renamed_account')
        self.assertFalse(self.blocked(ident))
        self.assertEqual(self.row('members', ident, 'id'), before)

    def test_target_admin_is_demoted_and_revoked_without_changing_password_finances_or_others(self):
        ident, old_session = self.account(role='admin', created_at=blocks.OWNER_BLOCK_CUTOFF, version=3)
        other, other_session = self.account('unrelated-admin', role='admin')
        self.privileges(ident, 1)
        self.privileges(other, 2)
        _, old_room = self.channel(ident)
        other_channel, _ = self.channel(other)
        before = self.row('members', ident, 'id')
        other_before = self.row('members', other, 'id')
        other_channel_before = self.row('streamer_channels', other_channel, 'id')
        evidence = self.snapshot(['payments', 'founder_ownership', 'admin_notifications',
                                  'admin_notification_members', 'member_name_history'])
        self.assertEqual(old_session.get('/api/admin/members').status_code, 200)
        self.migrate()
        self.assertTrue(self.blocked(ident))
        after = self.row('members', ident, 'id')
        self.assertEqual(after['role'], 'member')
        self.assertEqual(after['session_version'], before['session_version']+1)
        self.assertEqual(after['password_hash'], before['password_hash'])
        self.assertTrue(check_password_hash(after['password_hash'], self.PASSWORD))
        self.assertLessEqual(datetime.fromisoformat(after['access_until']), m.now_utc())
        self.assertEqual(self.snapshot(list(evidence)), evidence)
        self.assertEqual(self.row('members', other, 'id'), other_before)
        self.assertEqual(self.row('streamer_channels', other_channel, 'id'), other_channel_before)
        for table in ['pricing_moderators', 'service_grants', 'friend_access', 'live_entitlements', 'live_founders']:
            self.assertIsNotNone(self.row(table, ident)['revoked_at'], table)
            self.assertIsNone(self.row(table, other)['revoked_at'], table)
        supervisor = self.row('ol_supervisors', ident)
        self.assertEqual(supervisor['can_review'], 0)
        self.assertIsNotNone(supervisor['revoked_at'])
        self.assertIsNone(self.row('moderator_permissions', ident))
        self.assertIsNotNone(self.row('moderator_permissions', other))
        access = self.row('streamer_access', ident)
        self.assertTrue(access is None or datetime.fromisoformat(access['until_at']) <= m.now_utc())
        self.assertIsNotNone(self.row('member_archives', ident))
        self.assertEqual(old_session.get('/api/admin/members').status_code, 403)
        blocked_me = old_session.get('/api/account/me')
        self.assertEqual(blocked_me.status_code, 403)
        self.assertEqual(blocked_me.json['code'], 'account_blocked')
        self.assertEqual(other_session.get('/api/admin/members').status_code, 200)
        result = self.outcome()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['member_id'], ident)
        self.assertEqual(result['previous_role'], 'admin')
        self.assertEqual(result['role'], 'member')
        job = self.row('account_block_livekit_jobs', ident)
        self.assertIn(old_room, job['rooms_json'])

    def test_already_archived_target_still_invalidates_sessions_and_queues_old_room(self):
        ident, _ = self.account(version=7)
        channel_id, old_room = self.channel(ident, live=False)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)',
                         (ident, m.stamp(self.cutoff-timedelta(hours=2)), self.admin_id, 'already_archived'))
        before_archive = self.row('member_archives', ident)
        self.migrate()
        self.assertTrue(self.blocked(ident))
        self.assertEqual(self.row('members', ident, 'id')['session_version'], 8)
        self.assertEqual(self.row('member_archives', ident), before_archive)
        channel = self.row('streamer_channels', channel_id, 'id')
        self.assertIsNone(channel['live_until'])
        self.assertNotEqual(channel['room_name'], old_room)
        job = self.row('account_block_livekit_jobs', ident)
        self.assertIsNotNone(job)
        rooms = json.loads(job['rooms_json'])
        self.assertTrue(any(room.get('room_name') == old_room for room in rooms))
        self.assertGreater(datetime.fromisoformat(job['retry_until']), datetime.fromisoformat(job['blocked_at']))
        self.assertEqual(job['attempts'], 0)
        self.assertIsNone(job['last_success_at'])

    def test_unactivated_target_is_blocked_by_id_once_and_new_same_name_stays_untouched(self):
        ident, _ = self.account(activated=False)
        self.migrate()
        self.assertTrue(self.blocked(ident))
        marker = self.outcome_row()
        durable = self.snapshot(['account_blocks', 'account_block_livekit_jobs', 'member_archive_events'])
        version = self.row('members', ident, 'id')['session_version']
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('blocked-renamed-identity', ident))
        later_id, _ = self.account()
        later_before = self.row('members', later_id, 'id')
        self.migrate()
        self.assertTrue(self.blocked(ident))
        self.assertFalse(self.blocked(later_id))
        self.assertEqual(self.outcome_row(), marker)
        self.assertEqual(self.snapshot(list(durable)), durable)
        self.assertEqual(self.row('members', ident, 'id')['session_version'], version)
        self.assertEqual(self.row('members', later_id, 'id'), later_before)


if __name__ == '__main__':
    unittest.main()
