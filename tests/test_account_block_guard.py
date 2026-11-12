"""Blocked signed identities cannot regain public access through guest fallback."""
import secrets
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

import app as application
import membership as m
from auth_support import authenticated_client


class AccountBlockGuardTests(unittest.TestCase):
    PASSWORD = 'blocked-account-test-password-123'

    def setUp(self):
        settings = patch.dict('os.environ', {
            'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0',
            'OL_ACCOUNT_REPORT_EMAILS': '0', 'OL_REGISTRATION_FEE_ENABLED': '0',
        })
        settings.start(); self.addCleanup(settings.stop)
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,created_at) VALUES(?,?,?,?)',
                         (self.ident, 'blocked-fixture', generate_password_hash(self.PASSWORD), m.stamp(m.now_utc())))
            conn.execute('INSERT INTO account_blocks(member_id,blocked_at,reason,source) VALUES(?,?,?,?)',
                         (self.ident, m.stamp(m.now_utc()), 'test_access_block', 'test'))
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session.update(member_id=self.ident, session_version=0, csrf='block-test-csrf')

    def test_signed_block_denies_pages_media_and_admin_without_clearing_identity(self):
        for path in ['/', '/account', '/videos', '/streamers', '/assets/app.js',
                     '/api/account/me', '/api/admin/members', '/api/search?q=music',
                     '/api/streamers', '/api/videos']:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 403)
                self.assertIn('no-store', response.headers['Cache-Control'])
                if path.startswith('/api/'):
                    self.assertEqual(response.json['code'], 'account_blocked')
                else:
                    self.assertIn('Acceso bloqueado', response.get_data(as_text=True))
                    self.assertNotIn('<script', response.get_data(as_text=True))
        with self.client.session_transaction() as session:
            self.assertEqual(session['member_id'], self.ident)

    def test_outdated_cookie_and_post_are_denied_before_csrf_or_guest_fallback(self):
        with self.client.session_transaction() as session:
            session['session_version'] = -1
        response = self.client.post('/api/streamers/example/token', json={})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['code'], 'account_blocked')

    def test_other_admin_and_anonymous_pages_remain_available(self):
        self.assertEqual(self.admin.get('/api/admin/members').status_code, 200)
        self.assertEqual(self.app.test_client().get('/').status_code, 200)

    def test_denied_session_check_drives_media_expulsion_without_exposing_status(self):
        with patch('account_block_livekit.run_pending', return_value={'attempted': 1, 'completed': 0}) as runner:
            response = self.client.get('/api/account/me')
        runner.assert_called_once_with()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.json), {'code', 'error'})

    def test_media_service_failure_does_not_reopen_the_blocked_account(self):
        with patch('account_block_livekit.run_pending', side_effect=RuntimeError('unavailable')):
            response = self.client.get('/api/account/me')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['code'], 'account_blocked')

    def test_new_login_cannot_bypass_block_even_without_an_archive(self):
        client = self.app.test_client()
        csrf = client.get('/api/account/me').json['csrf']
        response = client.post('/api/account/login', json={
            'username': 'blocked-fixture', 'password': self.PASSWORD,
        }, headers={'X-CSRF-Token': csrf})
        self.assertEqual(response.status_code, 401)
        with client.session_transaction() as session:
            self.assertNotIn('member_id', session)

    def test_generic_archive_restore_and_deletion_cannot_remove_the_block(self):
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)',
                         (self.ident, m.stamp(m.now_utc()), None, 'blocked'))
        restored = self.admin.post('/api/admin/members/archive', json={
            'member_id': self.ident, 'archived': False,
        })
        self.assertEqual(restored.status_code, 409)
        self.assertEqual(restored.json['code'], 'account_blocked')
        removed = self.admin.post('/api/admin/members/delete', json={'member_id': self.ident})
        self.assertEqual(removed.status_code, 409)
        self.assertEqual(removed.json['code'], 'account_deletion_blocked')
        with self.app.app_context(), m.database() as conn:
            self.assertIsNotNone(conn.execute('SELECT 1 FROM account_blocks WHERE member_id=?', (self.ident,)).fetchone())

    def test_vercel_routes_direct_html_through_the_guard_before_static_files(self):
        root = Path(__file__).resolve().parents[1]
        routes = json.loads((root / 'vercel.json').read_text())['routes']
        for page in (root / 'assets').glob('*.html'):
            path = '/assets/' + page.name
            first = next(route for route in routes if route.get('handle') == 'filesystem' or
                         ('src' in route and re.fullmatch(route['src'], path)))
            self.assertEqual(first.get('dest'), '/api/index.py', path)
            self.assertEqual(first.get('headers', {}).get('Cache-Control'), 'no-store')
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403)
            self.assertIn('no-store', response.headers['Cache-Control'])


if __name__ == '__main__':
    unittest.main()
