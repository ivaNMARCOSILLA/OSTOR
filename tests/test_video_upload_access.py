"""The owner's video grant cannot turn into general admin or paid access."""
from datetime import datetime, timedelta
import json
import secrets
import unittest
from unittest.mock import patch

import app as application
import membership as m
import registration_fee as fee
import video_upload_access as access
import videos
from auth_support import authenticated_client
from test_videos import FakeStore, MP4


class VideoUploadAccessTests(unittest.TestCase):
    def setUp(self):
        self.settings = patch.dict('os.environ', {
            'VERCEL': '0', 'VERCEL_ENV': 'development', 'OL_LOGIN_EMAIL_REQUIRED': '0',
            'OL_LOGIN_AUDIT_EMAILS': '0', 'OL_ACCOUNT_REPORT_EMAILS': '0',
            'OL_REGISTRATION_FEE_ENABLED': '1',
        })
        self.settings.start(); self.addCleanup(self.settings.stop)
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        with self.app.app_context():
            access.init_database(); videos.init_database()
        self.client, self.ident = self.account('adminsiempre')
        self.other, self.other_id = self.account('video-grant-other')
        self.store = FakeStore()
        settings = {'storage_ready': True, 'max_file_bytes': 5 * 1024 ** 4,
                    'allowed_mime_types': list(videos.MIME_EXTENSIONS)}
        for name, replacement in [('ready', lambda: True), ('configuration', lambda: settings)]:
            mocked = patch.object(videos.storage, name, side_effect=replacement)
            mocked.start(); self.addCleanup(mocked.stop)
        for name in ['start', 'presign_part', 'list_parts', 'complete', 'head', 'sample', 'abort', 'delete']:
            mocked = patch.object(videos.storage, name, side_effect=getattr(self.store, name))
            mocked.start(); self.addCleanup(mocked.stop)

    def account(self, username, *, created=None):
        ident = secrets.token_hex(16)
        cutoff = datetime.fromisoformat(access.OWNER_UPLOAD_CUTOFF)
        instant = m.stamp(cutoff - timedelta(days=1)) if created is None else created
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (ident, username, 'fixture-password-hash', 'member', instant))
            fee.enroll(conn, ident, 'self_service')
            conn.execute('UPDATE registration_access SET grace_started_at=?,due_at=? WHERE member_id=?',
                         (m.stamp(m.now_utc()-timedelta(minutes=10)), m.stamp(m.now_utc()-timedelta(minutes=5)), ident))
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(member_id=ident, session_version=0)
        return client, ident

    def migrate(self):
        with self.app.app_context(), patch.dict('os.environ', {'VERCEL': '1', 'VERCEL_ENV': 'production'}):
            return access.apply_owner_upload_migration()

    def grant(self):
        self.assertEqual(self.migrate()['status'], 'granted')

    def post(self, client, path, data=None):
        token = client.get('/api/account/me').json['csrf']
        return client.post(path, json={} if data is None else data, headers={'X-CSRF-Token': token})

    def begin(self):
        response = self.post(self.client, '/api/videos/uploads', {
            'title': 'Mi baile', 'description': 'Creación propia.', 'category': 'dance',
            'filename': 'baile.mp4', 'size_bytes': len(MP4), 'mime_type': 'video/mp4', 'rights_confirmed': True,
        })
        self.assertEqual(response.status_code, 201, response.json)
        return response.json['id']

    def test_full_upload_works_after_fee_expiry_and_stays_in_quarantine(self):
        self.assertEqual(self.client.get('/api/videos/config').status_code, 402)
        self.grant()
        self.assertEqual(self.client.get('/api/videos/config').status_code, 200)
        self.assertEqual(self.client.get('/api/videos/me').status_code, 200)
        ident = self.begin()
        self.assertEqual(self.post(self.client, f'/api/videos/uploads/{ident}/parts', {'part_number': 1}).status_code, 200)
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM community_videos WHERE id=?', (ident,)).fetchone()
            self.store.uploads[row['upload_id']]['parts'] = [{'PartNumber': 1, 'ETag': '"part-one"', 'Size': len(MP4)}]
        completed = self.post(self.client, f'/api/videos/uploads/{ident}/complete')
        self.assertEqual(completed.status_code, 200, completed.json)
        self.assertEqual(completed.json['video']['state'], 'quarantined')
        self.assertEqual(self.post(self.client, f'/api/videos/{ident}/delete').status_code, 200)

    def test_grant_never_adds_admin_review_general_fee_exemption_or_broadcast_access(self):
        self.grant()
        self.assertEqual(self.client.get('/api/admin/videos').status_code, 403)
        for path in ['/api/videos', '/api/search?q=music', '/api/streamers']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 402)
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT role FROM members WHERE id=?', (self.ident,)).fetchone()
            self.assertEqual(row['role'], 'member')
            self.assertTrue(fee.state(self.ident, conn)['required'])
            self.assertFalse(conn.execute('SELECT 1 FROM friend_access WHERE member_id=? AND revoked_at IS NULL', (self.ident,)).fetchone())

    def test_upload_does_not_bypass_storage_or_ownership(self):
        self.grant()
        with patch.object(videos.storage, 'ready', return_value=False):
            response = self.post(self.client, '/api/videos/uploads', {})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json['code'], 'storage_unavailable')
        ident = self.begin()
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE community_videos SET owner_id=? WHERE id=?', (self.other_id, ident))
        self.assertEqual(self.post(self.client, f'/api/videos/uploads/{ident}/parts', {'part_number': 1}).status_code, 404)
        self.assertEqual(self.post(self.client, f'/api/videos/{ident}/delete').status_code, 404)
        self.assertEqual(self.other.get('/api/videos/config').status_code, 402)

    def test_grant_is_stable_under_rename_and_not_inherited_by_reused_username(self):
        self.grant()
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('renamed-owner', self.ident))
            conn.execute('UPDATE members SET username=? WHERE id=?', ('adminsiempre', self.other_id))
        self.assertEqual(self.client.get('/api/videos/config').status_code, 200)
        self.assertEqual(self.other.get('/api/videos/config').status_code, 402)
        self.assertEqual(self.migrate()['member_id'], self.ident)

    def test_archive_block_and_explicit_grant_revocation_still_deny_access(self):
        self.grant()
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO account_blocks VALUES(?,?,?,?)', (self.ident, m.stamp(m.now_utc()), 'test', 'test'))
        self.assertEqual(self.client.get('/api/videos/config').status_code, 403)
        with self.app.app_context(), m.database() as conn:
            self.assertFalse(access.permits({'id': self.ident}, '/api/videos/uploads', 'POST'))
            conn.execute('DELETE FROM account_blocks WHERE member_id=?', (self.ident,))
            conn.execute('UPDATE video_upload_grants SET revoked_at=? WHERE member_id=?', (m.stamp(m.now_utc()), self.ident))
        self.assertEqual(self.client.get('/api/videos/config').status_code, 402)
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE video_upload_grants SET revoked_at=NULL WHERE member_id=?', (self.ident,))
            conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)', (self.ident, m.stamp(m.now_utc()), None, 'test'))
            self.assertFalse(access.permits({'id': self.ident}, '/api/videos/uploads', 'POST'))

    def test_prior_owner_admin_ledger_uses_its_stable_id_without_changing_role(self):
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('old-admin-renamed', self.ident))
            conn.execute('UPDATE members SET username=? WHERE id=?', ('adminsiempre', self.other_id))
            conn.execute('INSERT INTO owner_access_migrations VALUES(?,?,?)', (
                access.OWNER_ADMIN_MIGRATION_ID, m.stamp(m.now_utc()), json.dumps({'status': 'granted', 'member_id': self.ident})))
        self.assertEqual(self.migrate()['member_id'], self.ident)
        self.assertEqual(self.client.get('/api/videos/config').status_code, 200)
        self.assertEqual(self.other.get('/api/videos/config').status_code, 402)

    def test_missing_account_outcome_is_durable_without_later_name_retarget(self):
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('different-name', self.ident))
        self.assertEqual(self.migrate()['status'], 'skipped_missing_existing_account')
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('adminsiempre', self.ident))
        self.assertEqual(self.migrate()['status'], 'skipped_missing_existing_account')
        self.assertEqual(self.client.get('/api/videos/config').status_code, 402)

    def test_new_renamed_archived_or_malformed_prior_account_is_not_granted(self):
        for scenario in ['new', 'renamed', 'archived', 'malformed']:
            with self.subTest(scenario=scenario), self.app.app_context(), m.database() as conn:
                conn.execute('DELETE FROM owner_access_migrations WHERE id IN (?,?)',
                             (access.OWNER_UPLOAD_MIGRATION_ID, access.OWNER_ADMIN_MIGRATION_ID))
                conn.execute('DELETE FROM member_name_history WHERE member_id=?', (self.ident,))
                conn.execute('DELETE FROM member_archives WHERE member_id=?', (self.ident,))
                conn.execute('UPDATE members SET created_at=? WHERE id=?', ('2026-11-11T00:00:00+00:00', self.ident))
                if scenario == 'new':
                    conn.execute('UPDATE members SET created_at=? WHERE id=?', ('2026-11-13T00:00:00+00:00', self.ident))
                elif scenario == 'renamed':
                    conn.execute('INSERT INTO member_name_history VALUES(?,?,?,?,?,?)',
                                 (secrets.token_hex(16), self.ident, None, 'old-name', 'adminsiempre', '2026-11-13T00:00:00+00:00'))
                elif scenario == 'archived':
                    conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)', (self.ident, m.stamp(m.now_utc()), None, 'test'))
                else:
                    conn.execute('INSERT INTO owner_access_migrations VALUES(?,?,?)',
                                 (access.OWNER_ADMIN_MIGRATION_ID, m.stamp(m.now_utc()), '{invalid'))
            result = self.migrate()
            self.assertTrue(result['status'].startswith('skipped_'), result)

    def test_permissions_have_exact_methods_and_paths_and_no_query_prefix_bypass(self):
        self.grant()
        with self.app.app_context():
            for path, method in [('/api/videos/config/extra', 'GET'), ('/api/videos/me', 'POST'),
                                 ('/api/videos/uploads', 'GET'), ('/api/videos/uploads/not-an-id/complete', 'POST'),
                                 ('/api/admin/videos', 'GET'), ('/api/videos/'+'a'*32+'/play', 'GET')]:
                with self.subTest(path=path, method=method):
                    self.assertFalse(access.permits({'id': self.ident}, path, method))

    def test_preview_startup_never_applies_production_owner_grant(self):
        with self.app.app_context():
            self.assertIsNone(access.apply_owner_upload_migration())
            with m.database() as conn:
                self.assertFalse(conn.execute('SELECT 1 FROM video_upload_grants').fetchone())


if __name__ == '__main__':
    unittest.main()
