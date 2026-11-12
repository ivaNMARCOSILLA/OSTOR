"""A server-timed registration fee is separate from annual creator access."""
import hashlib
import hmac
import json
import secrets
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app as application
import membership as m
import payments
import registration_fee as fee
import streamers
from auth_support import authenticated_client
from registration_support import registration_data


class RegistrationFeeTests(unittest.TestCase):
    def setUp(self):
        self.app = application.app
        self.instant = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
        self.serial = 0
        self.sessions = {}
        self.stripe_calls = []
        environment = patch.dict('os.environ', {
            'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0',
            'OL_REGISTRATION_FEE_ENABLED': '1',
            'STRIPE_WEBHOOK_SECRET': 'whsec_registration_fee_fixture',
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.admin = authenticated_client(self.app, self.addCleanup)
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        with self.app.app_context():
            streamers.init_database()
            payments.init_database()
            fee.init_database()
        patches = [patch.object(fee, 'now_utc', side_effect=lambda: self.instant),
                   patch.object(fee, 'payment_available', return_value=True),
                   patch.object(payments, 'provider', return_value='stripe'),
                   patch.object(payments, 'ready', return_value=True),
                   patch.object(payments, 'stripe', side_effect=self.fake_stripe),
                   patch('notifications.deliver_to'), patch('notifications.notify'),
                   patch('email_security.send_security_mail', return_value=False)]
        for mocked in patches:
            result = mocked.start()
            self.addCleanup(mocked.stop)
            if mocked.attribute == 'stripe':
                self.stripe = result
        self.member, self.member_id = self.account('new-self-service')
        self.guest = self.app.test_client()

    def account(self, username, activated=True, enrolled=True, role='member', origin='self_service'):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (ident, username, 'private-registration-password' if activated else None,
                          role, m.stamp(self.instant)))
            if enrolled:
                fee.enroll(conn, ident, origin=origin)
        client = self.app.test_client()
        with client.session_transaction() as session:
            session.update(member_id=ident, session_version=0)
        return client, ident

    def state(self, ident=None):
        with self.app.app_context():
            return fee.state(ident or self.member_id)

    def marker(self, ident=None):
        with self.app.app_context(), m.database() as conn:
            row = conn.execute('SELECT * FROM registration_access WHERE member_id=?',
                               (ident or self.member_id,)).fetchone()
            return dict(row) if row else None

    def activate(self, ident=None):
        with self.app.app_context():
            fee.activate(ident or self.member_id)

    def is_due(self, ident=None):
        with self.app.app_context():
            return fee.is_due(ident or self.member_id)

    def post(self, client=None, data=None, address=None):
        client = client or self.member
        token = client.get('/api/account/me').json['csrf']
        options = {'json': {'fee_terms': True} if data is None else data,
                   'headers': {'X-CSRF-Token': token}}
        if address:
            options['environ_overrides'] = {'REMOTE_ADDR': address}
        return client.post('/api/account/registration-fee/checkout', **options)

    def reconcile(self, client=None, data=None):
        client = client or self.member
        token = client.get('/api/account/me').json['csrf']
        return client.post('/api/account/registration-fee/reconcile',
                           json=data or {}, headers={'X-CSRF-Token': token})

    def fake_stripe(self, method, path, data=None, **options):
        self.stripe_calls.append((method, path, data, options))
        key = options.get('idempotency')
        if key not in self.sessions:
            self.serial += 1
            self.sessions[key] = {
                'id': 'cs_live_registration_fixture_'+str(self.serial),
                'url': 'https://checkout.stripe.com/c/pay/registration-fixture-'+str(self.serial),
                'livemode': True, 'mode': 'payment', 'status': 'open',
            }
        return dict(self.sessions[key])

    def orders(self):
        with self.app.app_context(), m.database() as conn:
            return [dict(row) for row in conn.execute(
                'SELECT * FROM registration_fee_orders ORDER BY created_at,id').fetchall()]

    def order(self, ident):
        return next(row for row in self.orders() if row['id'] == ident)

    def pending(self, member_id=None):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO registration_fee_orders
                (id,member_id,amount_cents,currency,created_at,checkout_id,state)
                VALUES(?,?,100,'eur',?,?,'pending')''',
                         (ident, member_id or self.member_id, m.stamp(self.instant),
                          'cs_live_registration_'+ident))
        return self.order(ident)

    def event(self, order, kind='checkout.session.completed', obj=None):
        if obj is None:
            obj = {'id': order['checkout_id'], 'livemode': True, 'mode': 'payment',
                   'payment_status': 'paid', 'currency': 'eur', 'amount_total': 100,
                   'client_reference_id': order['member_id'],
                   'payment_intent': 'pi_registration'+order['id'],
                   'metadata': {'registration_fee_id': order['id'], 'member_id': order['member_id']}}
        return {'id': 'evt_registration_'+secrets.token_hex(8), 'livemode': True,
                'type': kind, 'data': {'object': obj}}

    def handle(self, event):
        with self.app.app_context(), m.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return fee.handle_event(conn, event)

    def webhook(self, event, signed=True):
        raw = json.dumps(event).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b'whsec_registration_fee_fixture',
                             timestamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.guest.post('/api/payments/webhook/platform', data=raw, headers={
            'Content-Type': 'application/json',
            'Stripe-Signature': 't='+timestamp+',v1='+(signature if signed else 'wrong'),
        })

    def annual_snapshot(self):
        with self.app.app_context(), m.database() as conn:
            return {table: sorted([dict(row) for row in conn.execute('SELECT * FROM '+table).fetchall()],
                                  key=lambda row: json.dumps(row, sort_keys=True))
                    for table in ['members', 'payments', 'live_entitlements', 'live_founders',
                                  'streamer_access', 'friend_access', 'service_grants',
                                  'founder_activity', 'creator_subscriptions']}

    def test_pending_checkout_keeps_the_account_available_for_payment_confirmation(self):
        from account_archives import AccountDeletionBlocked, delete_unpaid_member
        response=self.post()
        self.assertEqual(response.status_code,200)
        with self.app.app_context(),m.database() as conn:
            with self.assertRaises(AccountDeletionBlocked):
                delete_unpaid_member(conn,self.member_id)
            self.assertIsNotNone(conn.execute('SELECT id FROM members WHERE id=?',(self.member_id,)).fetchone())
        self.assertEqual(self.order(response.json['id'])['state'],'pending')

    def test_five_minute_deadline_uses_server_time_and_cannot_be_reset_by_reads(self):
        self.activate()
        first = self.state()
        self.assertTrue(first['enabled'])
        self.assertTrue(first['required'])
        self.assertFalse(first['exempt'])
        self.assertFalse(first['paid'])
        self.assertTrue(first['in_grace'])
        self.assertEqual(first['grace_seconds'], 300)
        self.assertEqual(first['price_cents'], 100)
        self.assertEqual(first['currency'], 'eur')
        deadline = first['deadline']
        self.assertEqual(datetime.fromisoformat(deadline), self.instant+timedelta(seconds=300))
        self.instant += timedelta(seconds=299)
        self.activate()
        self.assertFalse(self.is_due())
        self.assertEqual(self.state()['grace_seconds'], 1)
        self.instant += timedelta(seconds=1)
        self.assertTrue(self.is_due())
        self.assertFalse(self.state()['in_grace'])
        self.assertEqual(self.state()['grace_seconds'], 0)
        self.assertEqual(self.state()['deadline'], deadline)
        self.instant += timedelta(days=1)
        self.assertTrue(self.is_due())
        self.assertEqual(self.state()['deadline'], deadline)

    def test_state_reads_are_pure_and_authenticated_endpoint_starts_grace_once(self):
        self.assertIsNone(self.marker()['grace_started_at'])
        self.state()
        self.assertIsNone(self.marker()['grace_started_at'])
        self.assertFalse(self.is_due())
        response = self.member.get('/api/account/registration-fee')
        self.assertEqual(response.status_code, 200, response.json)
        first = response.json
        self.assertEqual(first['grace_seconds'], 300)
        original = self.marker()
        self.instant += timedelta(seconds=60)
        second = self.member.get('/api/account/registration-fee').json
        self.assertEqual(second['grace_seconds'], 240)
        self.assertEqual(original, self.marker())

    def test_unactivated_and_archived_accounts_do_not_start_a_grace_clock(self):
        _, inactive = self.account('not-activated', activated=False)
        _, archived = self.account('archived-person')
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL)',
                         (archived, m.stamp(self.instant), self.admin_id, 'fixture'))
        for ident in [inactive, archived]:
            with self.subTest(member=ident):
                self.activate(ident)
                self.state(ident)
                self.assertIsNone(self.marker(ident)['grace_started_at'])
                self.assertIsNone(self.marker(ident)['due_at'])
                self.assertFalse(self.is_due(ident))

    def test_guests_and_admins_are_exempt_but_unknown_existing_accounts_need_the_fee(self):
        _, legacy = self.account('existing-unknown', enrolled=False)
        with self.app.app_context():
            guest = fee.state(None)
        self.assertFalse(guest['required'])
        self.assertTrue(guest['exempt'])
        self.assertTrue(self.state(self.admin_id)['exempt'])
        self.assertFalse(self.state(self.admin_id)['required'])
        self.assertFalse(self.is_due(self.admin_id))
        self.assertFalse(self.state(legacy)['exempt'])
        self.assertTrue(self.state(legacy)['required'])
        self.assertIsNone(self.marker(legacy))
        self.assertTrue(self.state(legacy)['required'])
        self.assertIsNone(self.marker(legacy))
        self.activate(legacy)
        self.assertEqual(self.marker(legacy)['origin'], 'legacy_unknown')
        self.assertEqual(self.state(legacy)['grace_seconds'], 300)

    def test_rosas_owner_exemption_stays_with_identity_while_free_grants_do_not_waive_fee(self):
        with self.app.app_context(), m.database() as conn:
            fee.mark_owner(conn, self.member_id, 'owner_rosas')
            fee.enroll(conn, self.member_id, origin='self_service')
        self.assertTrue(self.state()['exempt'])
        self.assertEqual(self.marker()['exempt_reason'], 'owner_rosas')
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET username=? WHERE id=?', ('renamed-owner', self.member_id))
        self.assertTrue(self.state()['exempt'])
        for table, name in [('friend_access', 'invited-grant'), ('service_grants', 'service-grant')]:
            _, ident = self.account(name)
            with self.app.app_context(), m.database() as conn:
                conn.execute('INSERT INTO '+table+'(member_id,granted_at,granted_by) VALUES(?,?,?)',
                             (ident, m.stamp(self.instant), self.admin_id))
            self.assertFalse(self.state(ident)['exempt'])
            self.assertTrue(self.state(ident)['required'])

    def test_invitation_and_legacy_origins_need_the_fee_without_staff_authority(self):
        for number, origin in enumerate(['owner_invitation', 'legacy_unknown']):
            _, ident = self.account('origin-'+str(number), origin=origin)
            self.activate(ident)
            self.assertFalse(self.state(ident)['exempt'])
            self.assertTrue(self.state(ident)['required'])
            self.assertEqual(self.state(ident)['grace_seconds'], 300)

    def test_only_active_supervision_and_moderation_authority_waives_the_fee(self):
        for number, kind in enumerate(['supervisor', 'pricing_moderator']):
            _, ident = self.account('staff-'+str(number))
            with self.app.app_context(), m.database() as conn:
                if kind == 'supervisor':
                    conn.execute('INSERT INTO ol_supervisors VALUES(?,?,?,?,NULL)',
                                 (ident, self.admin_id, m.stamp(self.instant), 1))
                else:
                    conn.execute('INSERT INTO pricing_moderators(member_id,assigned_by,assigned_at) VALUES(?,?,?)',
                                 (ident, self.admin_id, m.stamp(self.instant)))
            self.assertTrue(self.state(ident)['exempt'], kind)
            self.assertFalse(self.state(ident)['required'], kind)
            with self.app.app_context(), m.database() as conn:
                if kind == 'supervisor':
                    conn.execute('UPDATE ol_supervisors SET revoked_at=?,can_review=0 WHERE member_id=?',
                                 (m.stamp(self.instant), ident))
                else:
                    conn.execute('INSERT INTO moderator_permissions VALUES(?,?,?,?)',
                                 (ident, 'review_agreements', self.admin_id, m.stamp(self.instant)))
                    conn.execute('UPDATE pricing_moderators SET revoked_at=? WHERE member_id=?',
                                 (m.stamp(self.instant), ident))
            self.assertFalse(self.state(ident)['exempt'], kind)
            self.assertTrue(self.state(ident)['required'], kind)
        _, orphan = self.account('orphaned-permission')
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO moderator_permissions VALUES(?,?,?,?)',
                         (orphan, 'review_agreements', self.admin_id, m.stamp(self.instant)))
        self.assertFalse(self.state(orphan)['exempt'])
        self.assertTrue(self.state(orphan)['required'])

    def test_disabling_fee_never_blocks_due_accounts(self):
        self.activate()
        self.instant += timedelta(seconds=301)
        self.assertTrue(self.is_due())
        with patch.dict('os.environ', {'OL_REGISTRATION_FEE_ENABLED': '0'}):
            self.assertFalse(self.state()['enabled'])
            self.assertFalse(self.is_due())

    def test_fee_endpoints_require_auth_csrf_and_explicit_terms(self):
        self.assertEqual(self.guest.get('/api/account/registration-fee').status_code, 401)
        self.assertEqual(self.post(self.guest).status_code, 401)
        self.assertEqual(self.member.post('/api/account/registration-fee/checkout',
                                          json={'fee_terms': True}).status_code, 403)
        for position, terms in enumerate([None, False, 'true', 1]):
            with self.subTest(terms=terms):
                response = self.post(data={'fee_terms': terms}, address='192.0.2.'+str(position+1))
                self.assertEqual(response.status_code, 400, response.json)
        self.stripe.assert_not_called()
        self.assertEqual(self.orders(), [])

    def test_checkout_always_charges_one_euro_for_current_member_and_reuses_attempt(self):
        response = self.post(data={'fee_terms': True, 'amount_cents': 90000,
                                   'currency': 'usd', 'member_id': self.admin_id,
                                   'deadline': '2999-01-01T00:00:00+00:00'})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['grants_access'])
        order = self.order(response.json['id'])
        self.assertEqual(order['member_id'], self.member_id)
        self.assertEqual(order['amount_cents'], 100)
        self.assertEqual(order['currency'], 'eur')
        self.assertIsNone(order['paid_at'])
        method, path, data, options = self.stripe_calls[-1]
        self.assertEqual((method, path), ('POST', '/checkout/sessions'))
        self.assertEqual(data['mode'], 'payment')
        self.assertEqual(int(data['line_items[0][price_data][unit_amount]']), 100)
        self.assertEqual(data['line_items[0][price_data][currency]'], 'eur')
        for prefix in ['metadata', 'payment_intent_data[metadata]']:
            self.assertEqual(data[prefix+'[registration_fee_id]'], order['id'])
            self.assertEqual(data[prefix+'[member_id]'], self.member_id)
        self.assertEqual(data['success_url'], 'https://electronicama.com/account?registration_fee=processing#registration-payment')
        self.assertEqual(data['cancel_url'], 'https://electronicama.com/account?registration_fee=cancelled#registration-payment')
        self.assertFalse(options.get('account'))
        self.assertTrue(options.get('idempotency'))
        self.assertEqual(data['client_reference_id'], self.member_id)
        self.assertNotIn('recurring', json.dumps(data))
        second = self.post()
        self.assertEqual(second.status_code, 200, second.json)
        self.assertEqual(second.json['id'], order['id'])
        self.assertEqual(len(self.orders()), 1)
        self.assertEqual(options.get('idempotency'), self.stripe_calls[-1][3].get('idempotency'))
        self.assertFalse(self.state()['paid'])

    def test_unavailable_provider_returns_503_without_orders_or_external_calls(self):
        with patch.object(fee, 'payment_available', return_value=False):
            self.assertFalse(self.state()['payment_available'])
            self.assertEqual(self.post().status_code, 503)
        self.stripe.assert_not_called()
        self.assertEqual(self.orders(), [])

    def test_reconciliation_requires_auth_csrf_and_an_existing_checkout(self):
        self.assertEqual(self.reconcile(self.guest).status_code, 401)
        self.assertEqual(self.member.post('/api/account/registration-fee/reconcile',
                                          json={}).status_code, 403)
        self.assertEqual(self.reconcile().status_code, 409)
        self.stripe.assert_not_called()
        exempt = self.reconcile(self.admin)
        self.assertEqual(exempt.status_code, 200, exempt.json)
        self.assertTrue(exempt.json['exempt'])
        self.stripe.assert_not_called()
        with patch.object(fee, 'payment_available', return_value=False):
            self.assertEqual(self.reconcile().status_code, 503)
        self.stripe.assert_not_called()

    def test_reconciliation_leaves_unpaid_pending_and_valid_payment_confirms_without_annual_access(self):
        order = self.pending()
        before = self.annual_snapshot()
        unpaid = self.event(order)['data']['object']
        unpaid.update(payment_status='unpaid', payment_intent=None, status='open')
        with patch.object(payments, 'stripe', return_value=unpaid) as remote:
            response = self.reconcile()
            self.assertEqual(response.status_code, 200, response.json)
            self.assertFalse(response.json['paid'])
            self.assertEqual(remote.call_args.args[:2], ('GET', '/checkout/sessions/'+order['checkout_id']))
        self.assertIsNone(self.order(order['id'])['paid_at'])
        paid = self.event(order)['data']['object']
        paid['status'] = 'complete'
        with patch.object(payments, 'stripe', return_value=paid):
            response = self.reconcile()
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(response.json['paid'])
        with patch.object(payments, 'stripe') as remote:
            self.assertTrue(self.reconcile().json['paid'])
            remote.assert_not_called()
        self.assertEqual(before, self.annual_snapshot())

    def test_reconciliation_rejects_mismatched_or_unavailable_stripe_response_without_confirmation(self):
        order = self.pending()
        mismatch = self.event(order)['data']['object']
        mismatch['amount_total'] = 101
        with patch.object(payments, 'stripe', return_value=mismatch):
            self.assertEqual(self.reconcile().status_code, 502)
        self.assertIsNone(self.order(order['id'])['paid_at'])
        self.assertFalse(self.state()['paid'])
        with patch.object(payments, 'stripe', side_effect=payments.PaymentError('Sin respuesta del gestor.')):
            self.assertEqual(self.reconcile().status_code, 502)
        self.assertIsNone(self.order(order['id'])['paid_at'])

    def test_reconciliation_uses_latest_own_checkout_ignoring_foreign_ids_and_urls(self):
        older = self.pending()
        self.instant += timedelta(seconds=1)
        latest = self.pending()
        _, other_id = self.account('another-fee-payer')
        foreign = self.pending(other_id)
        before = self.annual_snapshot()
        paid = self.event(latest)['data']['object']
        paid['status'] = 'complete'
        with patch.object(payments, 'stripe', return_value=paid) as remote:
            response = self.reconcile(data={
                'id': foreign['id'], 'checkout_id': foreign['checkout_id'],
                'session_id': foreign['checkout_id'],
                'url': 'https://untrusted.invalid/'+foreign['checkout_id'],
            })
            self.assertEqual(response.status_code, 200, response.json)
            self.assertTrue(response.json['paid'])
            self.assertEqual(remote.call_args.args[:2], ('GET', '/checkout/sessions/'+latest['checkout_id']))
        self.assertIsNotNone(self.order(latest['id'])['paid_at'])
        self.assertIsNone(self.order(older['id'])['paid_at'])
        self.assertIsNone(self.order(foreign['id'])['paid_at'])
        self.assertFalse(self.state(other_id)['paid'])
        self.assertEqual(before, self.annual_snapshot())

    def test_checkout_rate_limit_ignores_arbitrary_username_and_email_fields(self):
        for number in range(6):
            response = self.post(data={'fee_terms': True, 'username': 'person-'+str(number),
                                       'email': str(number)+'@untrusted.invalid'})
            self.assertNotEqual(response.status_code, 429, response.json)
        self.assertEqual(self.post(data={'fee_terms': True, 'username': 'another-person',
                                         'email': 'another@untrusted.invalid'}).status_code, 429)
        other, _ = self.account('another-account-same-address')
        self.assertEqual(self.post(other, {'fee_terms': True}).status_code, 429)

    def test_verified_fee_is_idempotent_and_never_grants_annual_or_founder_access(self):
        self.activate()
        self.instant += timedelta(seconds=301)
        order = self.pending()
        before = self.annual_snapshot()
        event = self.event(order)
        self.assertTrue(self.handle(event))
        first = self.order(order['id'])
        self.assertEqual(first['state'], 'paid')
        self.assertIsNotNone(first['paid_at'])
        self.assertTrue(self.state()['paid'])
        self.assertFalse(self.is_due())
        self.assertTrue(self.handle(event))
        event['id'] = 'evt_registration_second_confirmation'
        event['type'] = 'checkout.session.async_payment_succeeded'
        self.assertTrue(self.handle(event))
        self.assertEqual(self.order(order['id']), first)
        self.assertEqual(before, self.annual_snapshot())

    def test_signed_payment_must_match_price_currency_member_checkout_and_mode(self):
        order = self.pending()
        cases = [('amount_total', 99), ('amount_total', True), ('amount_total', '100'),
                 ('currency', 'usd'), ('id', 'cs_live_another_checkout'),
                 ('mode', 'subscription'), ('payment_intent', None),
                 ('client_reference_id', self.admin_id)]
        for key, value in cases:
            with self.subTest(field=key, value=value):
                event = self.event(order)
                event['data']['object'][key] = value
                with self.assertRaises(ValueError):
                    self.handle(event)
        event = self.event(order)
        event['data']['object']['metadata']['member_id'] = self.admin_id
        with self.assertRaises(ValueError):
            self.handle(event)
        self.assertIsNone(self.order(order['id'])['paid_at'])
        self.assertFalse(self.state()['paid'])

    def test_nonplatform_and_test_events_cannot_confirm_fee(self):
        order = self.pending()
        events = []
        event = self.event(order)
        event['livemode'] = False
        events.append(event)
        event = self.event(order)
        event['account'] = 'acct_foreign_fixture'
        events.append(event)
        event = self.event(order)
        event['data']['object']['livemode'] = False
        events.append(event)
        for event in events:
            try:
                handled = self.handle(event)
            except ValueError:
                handled = False
            self.assertFalse(handled)
        self.assertIsNone(self.order(order['id'])['paid_at'])
        self.assertFalse(self.state()['paid'])

    def test_expiry_and_unpaid_completion_need_no_payment_intent(self):
        expired = self.pending()
        event = self.event(expired, 'checkout.session.expired')
        event['data']['object'].update(payment_intent=None, payment_status='unpaid')
        self.assertTrue(self.handle(event))
        self.assertEqual(self.order(expired['id'])['state'], 'expired')
        unpaid = self.pending()
        event = self.event(unpaid)
        event['data']['object'].update(payment_intent=None, payment_status='unpaid')
        self.assertTrue(self.handle(event))
        self.assertEqual(self.order(unpaid['id'])['state'], 'pending')
        self.assertIsNone(self.order(unpaid['id'])['paid_at'])
        self.assertFalse(self.state()['paid'])

    def test_partial_full_refund_or_dispute_revokes_only_fee_and_late_completion_cannot_restore(self):
        self.activate()
        self.instant += timedelta(seconds=301)
        for number, kind in enumerate(['partial', 'full', 'dispute']):
            with self.subTest(reversal=kind):
                _, ident = self.account('reversed-'+str(number))
                self.activate(ident)
                self.instant += timedelta(seconds=301)
                order = self.pending(ident)
                before = self.annual_snapshot()
                self.handle(self.event(order))
                obj = {'id': 'ch_registration_'+order['id'], 'livemode': True,
                       'payment_intent': 'pi_registration'+order['id'],
                       'amount': 100, 'currency': 'eur',
                       'metadata': {'registration_fee_id': order['id'], 'member_id': ident}}
                if kind == 'dispute':
                    event_kind = 'charge.dispute.created'
                else:
                    event_kind = 'charge.refunded'
                    obj.update(amount_refunded=50 if kind == 'partial' else 100,
                               refunded=kind == 'full')
                self.assertTrue(self.handle(self.event(order, event_kind, obj)))
                self.assertFalse(self.state(ident)['paid'])
                self.assertIsNone(self.marker(ident)['paid_at'])
                self.assertTrue(self.is_due(ident))
                self.handle(self.event(order))
                self.assertFalse(self.state(ident)['paid'])
                self.assertEqual(before, self.annual_snapshot())

    def test_signed_webhook_rejects_forgery_and_mismatch_then_confirms_once(self):
        order = self.pending()
        event = self.event(order)
        self.assertEqual(self.webhook(event, signed=False).status_code, 400)
        bad = self.event(order)
        bad['data']['object']['amount_total'] = 101
        self.assertEqual(self.webhook(bad).status_code, 400)
        self.assertIsNone(self.order(order['id'])['paid_at'])
        with self.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT id FROM stripe_events WHERE id=?', (bad['id'],)).fetchone())
        before = self.annual_snapshot()
        response = self.webhook(event)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(self.webhook(event).json['duplicate'])
        self.assertTrue(self.state()['paid'])
        self.assertEqual(before, self.annual_snapshot())

    def test_real_self_registration_enrolls_and_first_authenticated_state_starts_grace(self):
        client = self.app.test_client()
        data = registration_data(client, {'username': 'fee-real-registration',
                                          'password': 'local-registration-fixture-123'})
        token = client.get('/api/account/me').json['csrf']
        response = client.post('/api/account/register', json=data, headers={'X-CSRF-Token': token})
        self.assertEqual(response.status_code, 201, response.json)
        ident = client.get('/api/account/me').json['user']['id']
        self.assertEqual(self.marker(ident)['origin'], 'self_service')
        state = client.get('/api/account/registration-fee')
        self.assertEqual(state.status_code, 200, state.json)
        self.assertTrue(state.json['required'])
        self.assertTrue(state.json['in_grace'])
        self.assertEqual(state.json['grace_seconds'], 300)


if __name__ == '__main__':
    unittest.main()
