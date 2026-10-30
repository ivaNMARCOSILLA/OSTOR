"""Account removal hides and disables accounts without deleting paid history."""
import hashlib
import base64
import json
import secrets
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, patch

import app
import email_security
import membership as m
import streamers
from auth_support import authenticated_client
from registration_support import registration_data


class AccountArchiveTests(unittest.TestCase):
    PASSWORD = 'archive-test-password-123'
    PATH = '/api/admin/members/archive'

    def setUp(self):
        self.admin = authenticated_client(app.app, self.addCleanup)
        self.env = patch.dict('os.environ', {
            'LIVEKIT_URL': '', 'LIVEKIT_API_KEY': '', 'LIVEKIT_API_SECRET': '',
            'MAGGY_STREAMERS_ENABLED': '0', 'MAGGY_STREAMER_SALES_ENABLED': '0',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        with app.app.app_context():
            streamers.init_database()
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']

    def post(self, client, path, body):
        if path in {'/api/account/register', '/api/account/password/request'}:
            body = registration_data(client, body)
        csrf = client.get('/api/account/me').json['csrf']
        return client.post(path, json=body, headers={'X-CSRF-Token': csrf})

    def member(self, name, **extra):
        client = app.app.test_client()
        response = self.post(client, '/api/account/register', {
            'username': name, 'password': self.PASSWORD, **extra,
        })
        self.assertEqual(response.status_code, 201, response.json)
        return client, client.get('/api/account/me').json['user']['id']

    def archive(self, member_id, archived=True):
        return self.post(self.admin, self.PATH, {
            'member_id': member_id, 'archived': archived,
        })

    def delete(self, member_id, client=None):
        return self.post(client or self.admin, '/api/admin/members/delete', {'member_id': member_id})

    def listed(self, include_archived=False):
        path = '/api/admin/members' + ('?archived=1' if include_archived else '')
        response = self.admin.get(path)
        self.assertEqual(response.status_code, 200)
        return {row['id']: row for row in response.json['members']}

    def migration(self, environment='production'):
        import account_archives
        with app.app.app_context(), patch.dict('os.environ', {'VERCEL_ENV': environment}):
            account_archives.apply_owner_cleanup_migration()

    def token(self, member_id, purpose='reset', session_version=None):
        value = secrets.token_urlsafe(32)
        with app.app.app_context(), m.database() as conn:
            if session_version is None:
                session_version = conn.execute(
                    'SELECT session_version FROM members WHERE id=?', (member_id,),
                ).fetchone()['session_version']
            conn.execute('''INSERT INTO email_tokens(
                token_hash,member_id,purpose,email,session_version,created_at,expires_at
                ) VALUES(?,?,?,?,?,?,?)''', (
                hashlib.sha256(value.encode()).hexdigest(), member_id, purpose,
                'archive@example.test', session_version, m.stamp(m.now_utc()),
                m.stamp(m.now_utc() + timedelta(hours=1)),
            ))
        return value

    def subscription_fixture(self):
        import subscriptions
        buyer, buyer_id = self.member('archive-channel-buyer')
        _, creator_id = self.member('archive-channel-creator')
        _, moderator_id = self.member('archive-channel-moderator')
        channel, agreement = secrets.token_hex(16), secrets.token_hex(16)
        now, expiry = m.stamp(m.now_utc()), m.stamp(m.now_utc() + timedelta(days=365))
        with app.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET access_until=? WHERE id=?', (expiry, buyer_id))
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,updated_at) VALUES(?,?,?,?,?)', (
                channel, creator_id, 'Canal con precio aprobado', 'approved-' + channel, now,
            ))
            conn.execute('INSERT INTO stripe_accounts VALUES(?,?,?)', (creator_id, 'acct_archived_creator', now))
            conn.execute('INSERT INTO pricing_moderators VALUES(?,?,?,NULL)', (moderator_id, self.admin_id, now))
            conn.execute('INSERT INTO moderator_permissions VALUES(?,?,?,?)', (moderator_id, 'approve_agreements', self.admin_id, now))
            conn.execute('INSERT INTO subscription_agreements VALUES(?,?,?,?,?,?,?,?,?,?)', (
                agreement, channel, 1, creator_id, moderator_id, 350, 'month',
                '["badge"]', 'stripe:acct_archived_creator', now,
            ))
            for party, ident in [('creator', creator_id), ('admin', self.admin_id), ('moderator', moderator_id)]:
                conn.execute('INSERT INTO subscription_approvals VALUES(?,?,?,?)', (agreement, party, ident, now))
            conn.execute('INSERT INTO channel_subscription_settings(channel_id,agreement_id) VALUES(?,?)', (channel, agreement))
            approved = conn.execute('SELECT * FROM subscription_agreements WHERE id=?', (agreement,)).fetchone()
            self.assertTrue(subscriptions.approvals_valid(conn, approved))
        return buyer, buyer_id, creator_id, moderator_id, channel, agreement

    def test_only_authenticated_admin_with_csrf_can_archive(self):
        member, ident = self.member('ordinary-account')
        anonymous = app.app.test_client()
        for client in (anonymous, member):
            response = self.post(client, self.PATH, {'member_id': ident, 'archived': True})
            self.assertEqual(response.status_code, 403)
        raw_admin = app.app.test_client()
        self.assertEqual(self.post(raw_admin, '/api/account/login', {
            'username': 'test-admin', 'password': 'test-password-only-123',
        }).status_code, 200)
        response = raw_admin.post(self.PATH, json={'member_id': ident, 'archived': True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json['code'], 'csrf_expired')
        self.assertIn(ident, self.listed())

    def test_invalid_payload_unknown_target_and_administrators_are_protected(self):
        _, ident = self.member('archive-target')
        for body in ({}, [], {'member_id': ident}, {'member_id': ident, 'archived': 'true'},
                     {'member_id': ident, 'archived': 1}):
            response = self.post(self.admin, self.PATH, body)
            self.assertEqual(response.status_code, 400, (body, response.json))
        self.assertEqual(self.archive('f' * 32).status_code, 404)
        self.assertEqual(self.archive(self.admin_id).status_code, 403)
        with app.app.app_context():
            m.create_admin('another-admin', self.PASSWORD)
            with m.database() as conn:
                second = conn.execute('SELECT id FROM members WHERE username=?', ('another-admin',)).fetchone()['id']
        self.assertEqual(self.archive(second).status_code, 403)
        self.assertIsNotNone(self.admin.get('/api/account/me').json['user'])

    def test_admin_nickname_does_not_make_a_client_an_administrator(self):
        member, ident = self.member('amigo', nickname='admin')
        self.assertEqual(member.get('/api/account/me').json['user']['role'], 'member')
        self.assertEqual(self.archive(ident).status_code, 200)
        self.assertNotIn(ident, self.listed())
        self.assertIsNone(member.get('/api/account/me').json['user'])

    def test_archive_hides_account_and_restore_never_revives_old_sessions(self):
        member, ident = self.member('returning-client')
        second_device = app.app.test_client()
        self.assertEqual(self.post(second_device, '/api/account/login', {
            'username': 'returning-client', 'password': self.PASSWORD,
        }).status_code, 200)
        self.assertEqual(self.archive(ident).status_code, 200)
        self.assertNotIn(ident, self.listed())
        included = self.listed(True)[ident]
        self.assertTrue(included['archived'])
        self.assertIsNotNone(included['archived_at'])
        self.assertIsNone(member.get('/api/account/me').json['user'])
        self.assertIsNone(second_device.get('/api/account/me').json['user'])
        fresh_device = app.app.test_client()
        self.assertEqual(self.post(fresh_device, '/api/account/login', {
            'username': 'returning-client', 'password': self.PASSWORD,
        }).status_code, 401)
        self.assertEqual(self.archive(ident, False).status_code, 200)
        self.assertIn(ident, self.listed())
        self.assertFalse(self.listed(True)[ident]['archived'])
        self.assertIsNone(second_device.get('/api/account/me').json['user'])
        self.assertEqual(self.post(fresh_device, '/api/account/login', {
            'username': 'returning-client', 'password': self.PASSWORD,
        }).status_code, 200)

    def test_paid_period_hash_stripe_receipt_and_moderation_survive_archive(self):
        _, ident = self.member('paid-archive-client')
        instant = m.stamp(m.now_utc())
        expires = m.stamp(m.now_utc() + timedelta(days=365))
        channel, comment = secrets.token_hex(16), secrets.token_hex(16)
        with app.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET access_until=? WHERE id=?', (expires, ident))
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)', (
                'archive-payment', ident, 'annual', 2500, instant, expires,
                instant, self.admin_id, 'archive-receipt',
            ))
            conn.execute('''INSERT INTO stripe_orders(
                id,member_id,kind,account_id,amount_cents,currency,created_at,
                checkout_id,payment_intent,paid_at,state) VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (
                'archive-order', ident, 'platform_annual', '', 2500, 'eur', instant,
                'cs_archive_fixture', 'pi_archive_fixture', instant, 'paid',
            ))
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)', (
                channel, ident, 'Historia conservada', 'archive-room', expires, instant,
            ))
            conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,created_at) VALUES(?,?,?,?,?,?)', (
                comment, channel, ident, 'comment', 'Texto conservado para moderación', instant,
            ))
            before = dict(conn.execute('SELECT password_hash,access_until FROM members WHERE id=?', (ident,)).fetchone())
            payment = dict(conn.execute('SELECT * FROM payments WHERE member_id=?', (ident,)).fetchone())
            order = dict(conn.execute('SELECT * FROM stripe_orders WHERE member_id=?', (ident,)).fetchone())
        self.assertEqual(self.archive(ident).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            self.assertEqual(dict(conn.execute('SELECT password_hash,access_until FROM members WHERE id=?', (ident,)).fetchone()), before)
            self.assertEqual(dict(conn.execute('SELECT * FROM payments WHERE member_id=?', (ident,)).fetchone()), payment)
            self.assertEqual(dict(conn.execute('SELECT * FROM stripe_orders WHERE member_id=?', (ident,)).fetchone()), order)
            self.assertEqual(conn.execute('SELECT body FROM community_messages WHERE id=?', (comment,)).fetchone()['body'], 'Texto conservado para moderación')
            self.assertIsNone(conn.execute('SELECT live_until FROM streamer_channels WHERE id=?', (channel,)).fetchone()['live_until'])
        self.assertEqual(self.archive(ident, False).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT live_until FROM streamer_channels WHERE id=?', (channel,)).fetchone()['live_until'])

    def test_pending_invites_tokens_guests_and_live_thumbnail_are_invalidated(self):
        _, ident = self.member('archive-host')
        _, guest = self.member('archive-guest')
        now, expiry = m.stamp(m.now_utc()), m.stamp(m.now_utc() + timedelta(hours=1))
        own, other = secrets.token_hex(16), secrets.token_hex(16)
        self.token(ident)
        with app.app.app_context(), m.database() as conn:
            for token_hash, used in [('unused-archive-invite', None), ('used-archive-invite', now)]:
                conn.execute('INSERT INTO invitations VALUES(?,?,?,?)', (token_hash, ident, expiry, used))
            for channel, owner in [(own, ident), (other, guest)]:
                conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)', (
                    channel, owner, 'Canal de archivo', 'room-' + channel, expiry, now,
                ))
                conn.execute('INSERT INTO live_broadcast_sessions VALUES(?,?)', (channel, now))
            conn.execute('INSERT INTO live_guest_invites VALUES(?,?,?)', (own, guest, now))
            conn.execute('INSERT INTO live_guest_invites VALUES(?,?,?)', (other, ident, now))
            conn.execute('INSERT INTO live_channel_thumbnails VALUES(?,?,?,?)', (own, now, 'test-thumbnail', now))
        self.assertEqual(self.archive(ident).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM invitations WHERE member_id=? AND used_at IS NULL', (ident,)).fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM invitations WHERE member_id=? AND used_at IS NOT NULL', (ident,)).fetchone()['n'], 1)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM email_tokens WHERE member_id=?', (ident,)).fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM live_guest_invites WHERE member_id=? OR channel_id=?', (ident, own)).fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM live_channel_thumbnails WHERE channel_id=?', (own,)).fetchone()['n'], 0)

    def test_verified_email_login_and_new_recovery_cannot_reactivate_archived_account(self):
        _, ident = self.member('archive-email', email='archive@example.test')
        with app.app.app_context(), m.database() as conn:
            conn.execute('UPDATE member_profiles SET email_verified=1 WHERE member_id=?', (ident,))
        self.assertEqual(self.archive(ident).status_code, 200)
        client = app.app.test_client()
        self.assertEqual(self.post(client, '/api/account/login', {
            'username': 'archive@example.test', 'password': self.PASSWORD,
        }).status_code, 401)
        with patch.object(email_security, 'mail_ready', return_value=True), patch.object(email_security, 'deliver_to') as delivered:
            result = self.post(client, '/api/account/password/request', {'email': 'archive@example.test'})
            self.assertEqual(result.status_code, 200)
            delivered.assert_not_called()
            with app.app.app_context():
                self.assertFalse(email_security.issue(ident, 'reset'))
            delivered.assert_not_called()

    def test_even_current_version_reset_token_cannot_restore_an_archived_account(self):
        _, ident = self.member('archived-token-client', email='archive@example.test')
        with app.app.app_context(), m.database() as conn:
            conn.execute('UPDATE member_profiles SET email_verified=1 WHERE member_id=?', (ident,))
        old_token = self.token(ident)
        self.assertEqual(self.archive(ident).status_code, 200)
        # A stale delivery/retry must not bypass the archive by using its new session version.
        current_token = self.token(ident)
        client = app.app.test_client()
        for token in (old_token, current_token):
            response = self.post(client, '/api/account/password/reset', {
                'token': token, 'password': 'cannot-restore-archived-account-123',
            })
            self.assertEqual(response.status_code, 400)
        self.assertNotIn(ident, self.listed())

    def test_archived_creator_cannot_receive_new_channel_checkout_by_direct_link(self):
        import payments
        import subscriptions
        buyer, buyer_id, creator, _, channel, agreement = self.subscription_fixture()
        with app.app.app_context(), m.database() as conn:
            user = conn.execute('SELECT * FROM members WHERE id=?', (buyer_id,)).fetchone()
            self.assertEqual(payments.validate_order(conn, user, channel)['amount_cents'], 350)
        self.assertEqual(self.archive(creator).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            user = conn.execute('SELECT * FROM members WHERE id=?', (buyer_id,)).fetchone()
            with self.assertRaises(payments.PaymentError):
                payments.validate_order(conn, user, channel)
            approved = conn.execute('SELECT * FROM subscription_agreements WHERE id=?', (agreement,)).fetchone()
            self.assertFalse(subscriptions.approvals_valid(conn, approved))
        body = registration_data(buyer, {'channel_id': channel})
        with patch.object(payments, 'provider', return_value='stripe'), patch.object(payments, 'ready', return_value=True), patch.object(payments, 'stripe') as stripe:
            self.assertEqual(self.post(buyer, '/api/payments/checkout', body).status_code, 409)
            stripe.assert_not_called()
        public = buyer.get('/api/channel-subscriptions/' + channel).json
        self.assertFalse(public['payments_enabled'])
        self.assertFalse(public['checkout_available'])
        self.assertIsNone(public['agreement'])
        self.assertEqual(self.archive(creator, False).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            approved = conn.execute('SELECT * FROM subscription_agreements WHERE id=?', (agreement,)).fetchone()
            self.assertTrue(subscriptions.approvals_valid(conn, approved))

    def test_archived_moderator_pauses_new_subscriptions_without_erasing_approval(self):
        import subscriptions
        _, _, _, moderator, _, agreement = self.subscription_fixture()
        self.assertEqual(self.archive(moderator).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            approved = conn.execute('SELECT * FROM subscription_agreements WHERE id=?', (agreement,)).fetchone()
            self.assertFalse(subscriptions.approvals_valid(conn, approved))
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM subscription_approvals WHERE agreement_id=?', (agreement,)).fetchone()['n'], 3)
        self.assertEqual(self.archive(moderator, False).status_code, 200)
        with app.app.app_context(), m.database() as conn:
            approved = conn.execute('SELECT * FROM subscription_agreements WHERE id=?', (agreement,)).fetchone()
            self.assertTrue(subscriptions.approvals_valid(conn, approved))

    def test_cleanup_migration_only_runs_in_production_for_existing_exact_usernames(self):
        accounts = [self.member(name)[1] for name in ('amigo', 'prueba', 'prueba2')]
        _, ordinary = self.member('unrelated-client', nickname='prueba')
        self.migration('preview')
        self.assertTrue(set(accounts).issubset(self.listed()))
        self.migration('production')
        active = self.listed()
        self.assertTrue(all(ident not in active for ident in accounts))
        self.assertIn(ordinary, active)
        self.assertIn(self.admin_id, active)
        with app.app.app_context(), m.database() as conn:
            import account_archives
            self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM members WHERE username IN ('amigo','prueba','prueba2')").fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM member_archives').fetchone()['n'], 0)
            result = json.loads(conn.execute('SELECT result FROM owner_access_migrations WHERE id=?', (account_archives.OWNER_CLEANUP_ID,)).fetchone()['result'])
            self.assertEqual(result, {'amigo': 'deleted', 'prueba': 'deleted', 'prueba2': 'deleted'})

    def test_migration_never_removes_an_admin_or_a_later_registration(self):
        with app.app.app_context():
            m.create_admin('amigo', self.PASSWORD)
            with m.database() as conn:
                other_admin = conn.execute('SELECT id FROM members WHERE username=?', ('amigo',)).fetchone()['id']
        self.migration()
        self.assertIn(other_admin, self.listed())
        _, later = self.member('prueba')
        self.migration()
        self.assertIn(later, self.listed())

    def test_deleted_test_username_can_be_reused_without_reapplying_cleanup(self):
        old_client, old_id = self.member('prueba2')
        self.migration()
        self.assertNotIn(old_id, self.listed(True))
        self.assertIsNone(old_client.get('/api/account/me').json['user'])
        self.assertEqual(self.archive(old_id, False).status_code, 404)
        _, new_id = self.member('prueba2')
        self.assertNotEqual(old_id, new_id)
        self.migration()
        self.assertIn(new_id, self.listed())

    def test_physical_delete_requires_admin_csrf_and_protects_administrators(self):
        member, ident = self.member('delete-client')
        self.assertEqual(self.delete(ident, member).status_code, 403)
        self.assertEqual(self.delete(ident, app.app.test_client()).status_code, 403)
        raw_admin = app.app.test_client()
        self.assertEqual(self.post(raw_admin, '/api/account/login', {
            'username': 'test-admin', 'password': 'test-password-only-123',
        }).status_code, 200)
        self.assertEqual(raw_admin.post('/api/admin/members/delete', json={'member_id': ident}).status_code, 403)
        self.assertEqual(self.delete(self.admin_id).status_code, 403)
        self.assertEqual(self.delete('f' * 32).status_code, 404)
        for body in ({}, [], {'member_id': True}):
            self.assertEqual(self.post(self.admin, '/api/admin/members/delete', body).status_code, 400)
        self.assertIn(ident, self.listed())

    def test_physical_delete_removes_only_unpaid_account_and_owned_children(self):
        member, ident = self.member('delete-owner', email='archive@example.test', nickname='admin')
        other, other_id = self.member('preserved-account')
        channel, other_channel = secrets.token_hex(16), secrets.token_hex(16)
        now, expiry = m.stamp(m.now_utc()), m.stamp(m.now_utc() + timedelta(hours=1))
        comment, order = secrets.token_hex(16), secrets.token_hex(16)
        self.token(ident)
        with app.app.app_context(), m.database() as conn:
            for cid, owner in [(channel, ident), (other_channel, other_id)]:
                conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)', (cid, owner, 'Prueba sin pago', 'room-' + cid, expiry, now))
                conn.execute('INSERT INTO live_broadcast_sessions VALUES(?,?)', (cid, now))
                conn.execute('INSERT INTO live_channel_thumbnails VALUES(?,?,?,?)', (cid, now, 'test-thumbnail', now))
            conn.execute('INSERT INTO live_guest_invites VALUES(?,?,?)', (other_channel, ident, now))
            conn.execute('INSERT INTO live_guest_invites VALUES(?,?,?)', (channel, other_id, now))
            conn.execute('INSERT INTO friend_access VALUES(?,?,?,NULL)', (ident, now, self.admin_id))
            conn.execute('INSERT INTO service_grants VALUES(?,?,?,NULL)', (ident, now, self.admin_id))
            conn.execute('INSERT INTO invitations VALUES(?,?,?,NULL)', ('test-delete-invite', ident, expiry))
            conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,created_at) VALUES(?,?,?,?,?,?)', (comment, channel, ident, 'comment', 'Prueba sin incidencia', now))
            conn.execute('INSERT INTO community_likes VALUES(?,?)', (comment, other_id))
            conn.execute('INSERT INTO stripe_orders(id,member_id,kind,account_id,amount_cents,currency,created_at,state) VALUES(?,?,?,?,?,?,?,?)', (order, ident, 'platform_annual', '', 2500, 'eur', now, 'expired'))
            conn.execute('INSERT INTO stripe_order_context VALUES(?,?)', (order, 'Europe/Madrid'))
            conn.execute('INSERT INTO stripe_order_names VALUES(?,?)', (order, 'Prueba Sin Pago'))
        self.assertEqual(self.archive(ident).status_code, 200)
        result = self.delete(ident)
        self.assertEqual(result.status_code, 200, result.json)
        self.assertTrue(result.json['deleted'])
        self.assertIsNone(member.get('/api/account/me').json['user'])
        self.assertIsNotNone(other.get('/api/account/me').json['user'])
        with app.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT * FROM members WHERE id=?', (ident,)).fetchone())
            for table in ('member_profiles', 'email_tokens', 'invitations', 'friend_access', 'service_grants', 'member_archives', 'member_archive_events'):
                self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM '+table+' WHERE member_id=?', (ident,)).fetchone()['n'], 0, table)
            self.assertIsNone(conn.execute('SELECT * FROM streamer_channels WHERE id=?', (channel,)).fetchone())
            self.assertIsNotNone(conn.execute('SELECT * FROM streamer_channels WHERE id=?', (other_channel,)).fetchone())
            self.assertIsNone(conn.execute('SELECT * FROM stripe_orders WHERE id=?', (order,)).fetchone())
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM stripe_order_names WHERE order_id=?', (order,)).fetchone()['n'], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM community_likes WHERE message_id=?', (comment,)).fetchone()['n'], 0)
        self.assertEqual(self.delete(ident).status_code, 404)

    def test_delete_blocks_payment_or_recording_and_leaves_account_intact(self):
        _, ident = self.member('paid-delete-client')
        now, expiry = m.stamp(m.now_utc()), m.stamp(m.now_utc() + timedelta(days=365))
        with app.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)', ('protected-payment', ident, 'annual', 2500, now, expiry, now, self.admin_id, 'must-survive-delete'))
        self.assertEqual(self.delete(ident).status_code, 409)
        self.assertIn(ident, self.listed())
        with app.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT reference FROM payments WHERE member_id=?', (ident,)).fetchone()['reference'], 'must-survive-delete')
        _, recorded = self.member('recorded-delete-client')
        channel = secrets.token_hex(16)
        with app.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,updated_at) VALUES(?,?,?,?,?)', (channel, recorded, 'Grabación protegida', 'recorded-room', now))
            conn.execute('INSERT INTO live_recordings(id,channel_id,owner_id,room_name,object_key,state,started_at,expires_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', ('protected-recording', channel, recorded, 'recorded-room', 'directos/protected.mp4', 'completed', now, expiry, now))
        self.assertEqual(self.delete(recorded).status_code, 409)
        self.assertIn(recorded, self.listed())

    def test_delete_preserves_report_evidence_and_external_actor_references(self):
        _, reported = self.member('reported-delete-client')
        now, channel, message = m.stamp(m.now_utc()), secrets.token_hex(16), secrets.token_hex(16)
        with app.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,updated_at) VALUES(?,?,?,?,?)', (channel, self.admin_id, 'Historial de denuncias', 'reports-room', now))
            conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,created_at) VALUES(?,?,?,?,?,?)', (message, channel, self.admin_id, 'report', 'Incidencia', now))
            conn.execute('INSERT INTO community_report_details VALUES(?,?)', (message, json.dumps({'reported': {'id': reported}})))
        self.assertEqual(self.delete(reported).status_code, 409)
        self.assertIn(reported, self.listed())
        _, actor = self.member('permission-actor')
        _, recipient = self.member('permission-recipient')
        with app.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO service_grants VALUES(?,?,?,NULL)', (recipient, now, actor))
        self.assertEqual(self.delete(actor).status_code, 409)
        with app.app.app_context(), m.database() as conn:
            self.assertEqual(conn.execute('SELECT granted_by FROM service_grants WHERE member_id=?', (recipient,)).fetchone()['granted_by'], actor)
            self.assertIsNotNone(conn.execute('SELECT id FROM members WHERE id=?', (actor,)).fetchone())

    def test_owner_deletion_skips_paid_accounts_and_records_result_once(self):
        _, ident = self.member('prueba')
        now, expiry = m.stamp(m.now_utc()), m.stamp(m.now_utc() + timedelta(days=365))
        with app.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)', ('owner-safety-payment', ident, 'annual', 2500, now, expiry, now, self.admin_id, 'owner-safety-receipt'))
        self.migration()
        self.assertIn(ident, self.listed())
        with app.app.app_context(), m.database() as conn:
            import account_archives
            row = conn.execute('SELECT result FROM owner_access_migrations WHERE id=?', (account_archives.OWNER_CLEANUP_ID,)).fetchone()
            self.assertEqual(json.loads(row['result'])['prueba'], 'blocked_financial_or_history')
            self.assertIsNone(conn.execute('SELECT * FROM member_archives WHERE member_id=?', (ident,)).fetchone())
        self.migration()
        self.assertIn(ident, self.listed())

    def test_room_delete_and_guest_remove_use_the_required_short_lived_server_grants(self):
        import account_archives
        response = MagicMock()
        response.status_code = 200
        response.__enter__.return_value = response
        with app.app.app_context(), patch.dict('os.environ', {'LIVEKIT_URL': 'wss://local-fixture.invalid', 'LIVEKIT_API_KEY': 'local-fixture', 'LIVEKIT_API_SECRET': 'x' * 40, 'MAGGY_STREAMERS_ENABLED': '1'}), patch.object(account_archives.requests, 'post', return_value=response) as request:
            self.assertTrue(account_archives.disconnect_rooms([
                {'owner': True, 'member_id': 'owner', 'room_name': 'owned-room'},
                {'owner': False, 'member_id': 'guest', 'room_name': 'guest-room'},
            ]))
        first, second = request.call_args_list
        self.assertTrue(first.args[0].endswith('/DeleteRoom'))
        self.assertTrue(second.args[0].endswith('/RemoveParticipant'))
        claims = []
        for call in (first, second):
            encoded = call.kwargs['headers']['Authorization'].split()[1].split('.')[1]
            payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
            self.assertLessEqual(payload['exp'] - payload['iat'], 45)
            claims.append(payload['video'])
        self.assertEqual(claims, [{'roomCreate': True}, {'roomAdmin': True, 'room': 'guest-room'}])
