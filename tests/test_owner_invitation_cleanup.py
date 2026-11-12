"""Owner cleanup removes only proved old friend invitations and preserves evidence."""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import json
import secrets
import threading
import unittest
from unittest.mock import patch

import app as application
import membership as m
import owner_invitation_cleanup as cleanup
import streamers
from auth_support import authenticated_client


class OwnerInvitationCleanupTests(unittest.TestCase):
    def setUp(self):
        settings = patch.dict('os.environ', {
            'VERCEL': '0', 'VERCEL_ENV': 'development', 'OL_LOGIN_EMAIL_REQUIRED': '0',
            'OL_LOGIN_AUDIT_EMAILS': '0', 'OL_ACCOUNT_REPORT_EMAILS': '0',
            'OL_REGISTRATION_FEE_ENABLED': '0', 'MAGGY_STREAMERS_ENABLED': '0',
        })
        settings.start(); self.addCleanup(settings.stop)
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        self.cutoff = datetime.fromisoformat(cleanup.OWNER_INVITATION_CUTOFF)
        self.old = m.stamp(self.cutoff - timedelta(days=2))
        with self.app.app_context():
            streamers.init_database()

    def account(self, username, *, origin='owner_invitation', friend=True, invitation=True,
                activated=True, role='member', created_at=None, granted_at=None):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (ident, username, 'used-fixture-password-hash' if activated else None,
                          role, created_at or self.old))
            if origin is not None:
                conn.execute('INSERT INTO registration_access(member_id,origin) VALUES(?,?)', (ident, origin))
            if friend:
                conn.execute('INSERT INTO friend_access VALUES(?,?,?,NULL)',
                             (ident, granted_at or self.old, self.admin_id))
            if invitation:
                conn.execute('INSERT INTO invitations VALUES(?,?,?,?)',
                             (secrets.token_hex(32), ident, m.stamp(self.cutoff + timedelta(days=1)),
                              self.old if activated else None))
        client = self.app.test_client()
        if activated:
            with client.session_transaction() as session:
                session.update(member_id=ident, session_version=0)
        return ident, client

    def migrate(self, vercel='1', environment='production'):
        with self.app.app_context(), patch.dict('os.environ', {'VERCEL': vercel, 'VERCEL_ENV': environment}):
            return cleanup.apply_owner_invitation_cleanup()

    def row(self, ident, table='members', column='id'):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM '+table+' WHERE '+column+'=?', (ident,)).fetchone()
            return dict(row) if row else None

    def status(self, result, ident):
        return next(row['status'] for row in result['accounts'] if row['member_id'] == ident)

    def test_deletes_activated_pending_and_proven_legacy_invites_and_invalidates_sessions(self):
        active, session = self.account('accepted-friend')
        pending, _ = self.account('pending-friend', activated=False)
        legacy, _ = self.account('legacy-friend', origin='legacy_unknown')
        no_origin, _ = self.account('earlier-friend', origin=None)
        result, rooms = self.migrate()
        self.assertEqual(result['counts'], {'deleted': 4})
        self.assertEqual(rooms, [])
        for ident in [active, pending, legacy, no_origin]:
            self.assertIsNone(self.row(ident))
        self.assertIsNone(session.get('/api/account/me').json['user'])
        self.assertEqual(self.admin.get('/api/admin/members').status_code, 200)

    def test_self_service_free_access_and_ambiguous_legacy_are_retained(self):
        ordinary, _ = self.account('real-registration', origin='self_service')
        free, _ = self.account('free-real-registration', origin='self_service', invitation=False)
        unknown, _ = self.account('unknown-free-origin', origin='legacy_unknown', invitation=False)
        no_proof, _ = self.account('old-free-no-history', origin=None, invitation=False)
        target, _ = self.account('actual-old-invite')
        before = {ident: self.row(ident) for ident in [ordinary, free, unknown, no_proof]}
        result, _ = self.migrate()
        self.assertEqual(self.status(result, target), 'deleted')
        self.assertEqual(self.status(result, unknown), 'kept_ambiguous_legacy')
        self.assertEqual(self.status(result, no_proof), 'kept_ambiguous_legacy')
        for ident, row in before.items():
            self.assertEqual(self.row(ident), row)
        self.assertNotIn(ordinary, {row['member_id'] for row in result['accounts']})

    def test_late_accounts_or_changed_grants_and_unknown_dates_are_not_deleted(self):
        later = m.stamp(self.cutoff + timedelta(seconds=1))
        newer, _ = self.account('newer-invitation', created_at=later)
        changed, _ = self.account('renewed-invitation', granted_at=later)
        malformed, _ = self.account('unknown-created-date', created_at='not-a-date')
        result, _ = self.migrate()
        for ident in [newer, changed, malformed]:
            self.assertIsNotNone(self.row(ident))
            self.assertTrue(self.status(result, ident).startswith('kept_'))

    def test_keeps_administrators_staff_blocked_owner_and_explicit_video_account(self):
        admin, _ = self.account('invited-admin', role='admin')
        moderator, _ = self.account('active-moderator')
        supervisor, _ = self.account('active-supervisor')
        blocked, _ = self.account('blocked-invite')
        rosas, _ = self.account('renamed-rosas')
        owner_exempt, _ = self.account('owner-by-exemption')
        video_owner, _ = self.account('renamed-video-admin')
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO pricing_moderators VALUES(?,?,?,NULL)', (moderator, self.admin_id, self.old))
            conn.execute('INSERT INTO ol_supervisors VALUES(?,?,?,?,NULL)', (supervisor, self.admin_id, self.old, 1))
            conn.execute('INSERT INTO account_blocks VALUES(?,?,?,?)', (blocked, self.old, 'preserve', 'test'))
            conn.execute('INSERT INTO member_identity_links VALUES(?,?)', ('flores', rosas))
            conn.execute("UPDATE registration_access SET exempt_reason='owner_rosas' WHERE member_id=?", (owner_exempt,))
            conn.execute('INSERT INTO video_upload_grants VALUES(?,?,?,NULL)', (video_owner, self.old, cleanup.VIDEO_OWNER_SOURCE))
        preserved = {ident: self.row(ident) for ident in [admin, moderator, supervisor, blocked, rosas, owner_exempt, video_owner]}
        result, _ = self.migrate()
        for ident, row in preserved.items():
            self.assertEqual(self.row(ident), row)
            self.assertTrue(self.status(result, ident).startswith('kept_'))
        self.assertEqual(self.status(result, rosas), 'kept_owner')
        self.assertEqual(self.status(result, blocked), 'kept_blocked')

    def test_financial_history_is_archived_preserved_and_hidden_from_both_panels(self):
        ident, session = self.account('paid-old-invite')
        ordinary, _ = self.account('normal-paid-client', origin='self_service', invitation=False)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), ident, 'annual', 2500, self.old,
                          m.stamp(self.cutoff + timedelta(days=365)), self.old, self.admin_id, 'KEEP-PAID-FRIEND'))
            payments = [dict(row) for row in conn.execute('SELECT * FROM payments').fetchall()]
        result, _ = self.migrate()
        self.assertEqual(self.status(result, ident), 'archived_protected_history')
        self.assertIsNotNone(self.row(ident))
        self.assertIsNotNone(self.row(ident, 'member_archives', 'member_id'))
        self.assertIsNone(session.get('/api/account/me').json['user'])
        listed = self.admin.get('/api/admin/members').json['members']
        self.assertNotIn(ident, {row['id'] for row in listed})
        self.assertIn(ordinary, {row['id'] for row in listed})
        invitation_list = self.admin.get('/api/admin/invitations').json['invitations']
        self.assertNotIn(ident, {row['member_id'] for row in invitation_list})
        statistics = self.admin.get('/api/admin/statistics')
        self.assertEqual(statistics.status_code, 200)
        self.assertEqual(statistics.json['accounts']['registered'], 1)
        with self.app.app_context(), m.database() as conn:
            self.assertEqual([dict(row) for row in conn.execute('SELECT * FROM payments').fetchall()], payments)

    def test_video_history_is_preserved_and_account_archived(self):
        ident, _ = self.account('old-invite-with-video')
        video = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO community_videos(id,owner_id,title,description,category,filename,
                mime_type,size_bytes,object_key,part_size,part_count,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (video, ident, 'Conservar vídeo', '', 'other',
                'private.mp4', 'video/mp4', 10, 'private/'+video, 10, 1, 'quarantined', self.old, self.old))
            before = dict(conn.execute('SELECT * FROM community_videos WHERE id=?', (video,)).fetchone())
        result, _ = self.migrate()
        self.assertEqual(self.status(result, ident), 'archived_protected_history')
        self.assertEqual(self.row(video, 'community_videos'), before)

    def test_one_time_empty_or_completed_snapshot_never_targets_new_names_or_invites(self):
        ident, _ = self.account('reusable-invite-name')
        result, _ = self.migrate()
        self.assertIsNone(self.row(ident))
        reused, _ = self.account('reusable-invite-name')
        later, _ = self.account('another-existing-invite')
        repeated, rooms = self.migrate()
        self.assertEqual(repeated, result)
        self.assertEqual(rooms, [])
        self.assertIsNotNone(self.row(reused))
        self.assertIsNotNone(self.row(later))
        with self.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM owner_access_migrations WHERE id=?',
                                         (cleanup.OWNER_INVITATION_CLEANUP_ID,)).fetchone()['n'], 1)

    def test_preview_and_non_vercel_runs_do_not_write_cleanup_ledger(self):
        ident, _ = self.account('preview-invite')
        for vercel, environment in [('0', 'production'), ('1', 'preview'), ('0', 'development')]:
            self.assertEqual(self.migrate(vercel, environment), (None, []))
        self.assertIsNotNone(self.row(ident))
        with self.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT 1 FROM owner_access_migrations WHERE id=?', (cleanup.OWNER_INVITATION_CLEANUP_ID,)).fetchone())

    def test_empty_initial_snapshot_also_never_targets_later_invites(self):
        result, rooms = self.migrate()
        self.assertEqual(result['accounts'], [])
        self.assertEqual(rooms, [])
        later, _ = self.account('invited-after-empty-snapshot')
        self.assertEqual(self.migrate(), (result, []))
        self.assertIsNotNone(self.row(later))

    def test_concurrent_workers_share_one_serialized_snapshot(self):
        ident, _ = self.account('concurrent-old-invite')
        barrier = threading.Barrier(2)
        def worker():
            with self.app.app_context():
                barrier.wait(timeout=5)
                return cleanup.apply_owner_invitation_cleanup()
        with patch.dict('os.environ', {'VERCEL': '1', 'VERCEL_ENV': 'production'}), ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker)
            second = pool.submit(worker)
            a, b = first.result(timeout=20), second.result(timeout=20)
        self.assertEqual(a, b)
        self.assertEqual(self.status(a[0], ident), 'deleted')
        self.assertIsNone(self.row(ident))

    def test_network_is_never_called_in_cleanup_and_live_rooms_are_returned_once(self):
        ident, _ = self.account('live-old-invite')
        channel = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)',
                         (channel, ident, 'Sala anterior', 'former-room', m.stamp(self.cutoff+timedelta(days=1)), self.old))
        with patch('requests.post', side_effect=AssertionError('No external request from cleanup')) as external:
            result, rooms = self.migrate()
        external.assert_not_called()
        self.assertEqual(self.status(result, ident), 'deleted')
        self.assertEqual(rooms, [{'room_name': 'former-room', 'owner': True, 'member_id': ident}])
        self.assertEqual(self.migrate()[1], [])


if __name__ == '__main__':
    unittest.main()
