"""Platform contributions are voluntary payments, never access or badge purchases."""
import hashlib
import hmac
import json
import secrets
import time
import unittest
from unittest.mock import patch

import app as application
import contributions
import membership as m
import payments
import streamers
from auth_support import authenticated_client


class ContributionTests(unittest.TestCase):
    def setUp(self):
        self.app = application.app
        environment = patch.dict('os.environ', {
            'OL_LOGIN_EMAIL_REQUIRED': '0', 'OL_LOGIN_AUDIT_EMAILS': '0',
            'STRIPE_WEBHOOK_SECRET': 'whsec_contribution_local_fixture',
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.admin = authenticated_client(self.app, self.addCleanup)
        with self.app.app_context():
            streamers.init_database()
            payments.init_database()
            contributions.init_database()
        self.member_id = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (self.member_id, 'contribution-viewer', 'private-password-sentinel',
                          'member', m.stamp(m.now_utc())))
            conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',
                         (self.member_id, 'private-email-sentinel@example.invalid',
                          'Persona', m.stamp(m.now_utc())))
        self.member = self.app.test_client()
        with self.member.session_transaction() as session:
            session.update(member_id=self.member_id, session_version=0)
        self.guest = self.app.test_client()
        self.serial = 0
        self.stripe_calls = []
        for mocked in [patch.object(payments, 'provider', return_value='stripe'),
                       patch.object(payments, 'ready', return_value=True),
                       patch.object(payments, 'stripe', side_effect=self.fake_stripe),
                       patch('notifications.deliver_to'), patch('notifications.notify')]:
            mock = mocked.start()
            self.addCleanup(mocked.stop)
            if mocked.attribute == 'stripe':
                self.stripe = mock

    def fake_stripe(self, method, path, data=None, **kwargs):
        self.stripe_calls.append((method, path, data, kwargs))
        self.serial += 1
        return {'id': 'cs_live_contribution_fixture_'+str(self.serial),
                'url': 'https://checkout.stripe.com/c/pay/contribution-fixture-'+str(self.serial),
                'livemode': True, 'mode': 'payment', 'status': 'open'}

    def post(self, client=None, data=None, address=None):
        client = client or self.guest
        token = client.get('/api/account/me').json['csrf']
        options = {'json': data if data is not None else {
            'amount_cents': 1000, 'contributions_terms': True},
            'headers': {'X-CSRF-Token': token}}
        if address:
            options['environ_overrides'] = {'REMOTE_ADDR': address}
        return client.post('/api/contributions/checkout', **options)

    def rows(self):
        with self.app.app_context(), m.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM contribution_payments ORDER BY created_at,id').fetchall()]

    def row(self, ident):
        return next(row for row in self.rows() if row['id'] == ident)

    def seed(self, amount=1000, member_id=None):
        ident = secrets.token_hex(16)
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO contribution_payments
                (id,member_id,amount_cents,currency,created_at,checkout_id,state)
                VALUES(?,?,?,?,?,?,?)''',
                         (ident, member_id, amount, 'eur', m.stamp(m.now_utc()),
                          'cs_live_fixture_'+ident, 'pending'))
        return self.row(ident)

    def event(self, row, kind='checkout.session.completed', obj=None):
        if obj is None:
            obj = {'id': row['checkout_id'], 'livemode': True,
                   'mode': 'payment', 'payment_status': 'paid',
                   'amount_total': row['amount_cents'], 'currency': 'eur',
                   'metadata': {'contribution_id': row['id']},
                   'payment_intent': 'pi_fixture'+row['id']}
        return {'id': 'evt_fixture_'+secrets.token_hex(8), 'livemode': True,
                'type': kind, 'data': {'object': obj}}

    def handle(self, event):
        with self.app.app_context(), m.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            return contributions.handle_event(conn, event)

    def webhook(self, event, valid_signature=True):
        raw = json.dumps(event).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(b'whsec_contribution_local_fixture',
                             timestamp.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        return self.guest.post('/api/payments/webhook/platform', data=raw, headers={
            'Content-Type': 'application/json',
            'Stripe-Signature': 't='+timestamp+',v1='+(signature if valid_signature else 'wrong'),
        })

    def refund(self, row, amount, metadata=True):
        obj = {'id': 'ch_fixture_'+row['id'], 'livemode': True,
               'payment_intent': 'pi_fixture'+row['id'], 'currency': 'eur',
               'amount': row['amount_cents'], 'amount_refunded': amount,
               'refunded': amount == row['amount_cents']}
        if metadata:
            obj['metadata'] = {'contribution_id': row['id']}
        return self.event(row, 'charge.refunded', obj)

    def access_snapshot(self):
        with self.app.app_context(), m.database() as conn:
            return {table: sorted([dict(row) for row in conn.execute('SELECT * FROM '+table).fetchall()],
                                  key=lambda row: json.dumps(row, sort_keys=True))
                    for table in ['members', 'payments', 'live_entitlements',
                                  'live_founders', 'streamer_access', 'friend_access',
                                  'service_grants', 'founder_activity', 'creator_subscriptions']}

    def test_public_configuration_and_unavailable_provider_create_no_payment(self):
        response = self.guest.get('/api/contributions/config')
        self.assertEqual(response.status_code, 200)
        config = response.json
        self.assertTrue(config['available'])
        self.assertEqual(config['currency'], 'eur')
        self.assertEqual(config['presets'], [300, 500, 1000])
        self.assertEqual(config['min_amount_cents'], 100)
        self.assertEqual(config['max_amount_cents'], 50000)
        self.assertTrue(config['one_time'])
        self.assertFalse(config['grants_access'])
        for patches in [patch.object(payments, 'ready', return_value=False),
                        patch.object(payments, 'provider', return_value='legacy_paypal')]:
            with patches:
                self.assertFalse(self.guest.get('/api/contributions/config').json['available'])
                self.assertEqual(self.post().status_code, 503)
        self.stripe.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_guest_requires_csrf_and_explicit_consent(self):
        response = self.guest.post('/api/contributions/checkout',
                                   json={'amount_cents': 1000, 'contributions_terms': True})
        self.assertEqual(response.status_code, 403)
        for position, terms in enumerate([None, False, 'true', 1]):
            with self.subTest(terms=terms):
                self.assertEqual(self.post(data={'amount_cents': 1000, 'contributions_terms': terms},
                                           address='192.0.2.'+str(position+1)).status_code, 400)
        self.stripe.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_amount_must_be_integer_euros_within_bounds(self):
        for position, amount in enumerate([None, True, False, '1000', 100.0, -1, 0, 99, 50001]):
            with self.subTest(amount=amount):
                response = self.post(data={'amount_cents': amount, 'contributions_terms': True},
                                     address='192.0.2.'+str(position+30))
                self.assertEqual(response.status_code, 400, response.json)
        self.stripe.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_guest_checkout_uses_platform_one_time_mode_and_no_access(self):
        before = self.access_snapshot()
        response = self.post(data={'amount_cents': 300, 'contributions_terms': True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertFalse(response.json['grants_access'])
        row = self.row(response.json['id'])
        self.assertIsNone(row['member_id'])
        self.assertEqual(row['amount_cents'], 300)
        self.assertEqual(row['state'], 'pending')
        self.assertIsNone(row['paid_at'])
        method, path, params, options = self.stripe_calls[-1]
        self.assertEqual((method, path), ('POST', '/checkout/sessions'))
        self.assertEqual(params['mode'], 'payment')
        self.assertEqual(params['line_items[0][price_data][currency]'], 'eur')
        self.assertEqual(int(params['line_items[0][price_data][unit_amount]']), 300)
        self.assertEqual(params['metadata[contribution_id]'], row['id'])
        self.assertEqual(params['payment_intent_data[metadata][contribution_id]'], row['id'])
        self.assertEqual(params['success_url'], 'https://electronicama.com/?contribution=processing#contributions')
        self.assertEqual(params['cancel_url'], 'https://electronicama.com/?contribution=cancelled#contributions')
        self.assertTrue(options.get('idempotency'))
        self.assertFalse(options.get('account'))
        for forbidden in ['subscription_data', 'transfer_data', 'application_fee_amount', 'recurring']:
            self.assertNotIn(forbidden, json.dumps(params))
        self.assertEqual(before, self.access_snapshot())

    def test_registered_contributor_and_browser_return_never_grant_access(self):
        before = self.access_snapshot()
        response = self.post(self.member, {'amount_cents': 50000, 'contributions_terms': True})
        self.assertEqual(response.status_code, 200, response.json)
        row = self.row(response.json['id'])
        self.assertEqual(row['member_id'], self.member_id)
        self.member.get('/?contribution=received&session_id='+row['checkout_id']).close()
        self.assertEqual(self.row(row['id'])['state'], 'pending')
        self.assertIsNone(self.row(row['id'])['paid_at'])
        self.assertTrue(self.handle(self.event(row)))
        self.assertEqual(self.row(row['id'])['state'], 'paid')
        self.assertEqual(before, self.access_snapshot())

    def test_ambiguous_failure_retries_same_attempt_with_same_idempotency_key(self):
        with patch.object(payments, 'stripe', side_effect=payments.PaymentError('Sin respuesta del gestor.')) as first:
            failure = self.post()
        self.assertEqual(failure.status_code, 502)
        original_key = first.call_args.kwargs.get('idempotency')
        self.assertTrue(original_key)
        response = self.post()
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.stripe_calls[-1][3].get('idempotency'), original_key)
        self.assertEqual(len(self.rows()), 1)
        self.assertIsNone(self.rows()[0]['paid_at'])

    def test_rate_limit_cannot_be_reset_with_untrusted_identity_fields(self):
        for number in range(6):
            response = self.post(data={'amount_cents': 100+number, 'contributions_terms': True,
                                       'username': 'supplied-'+str(number),
                                       'email': str(number)+'@untrusted.invalid'})
            self.assertNotEqual(response.status_code, 429, response.json)
        response = self.post(data={'amount_cents': 106, 'contributions_terms': True,
                                   'username': 'a-new-name', 'email': 'another@untrusted.invalid'})
        self.assertEqual(response.status_code, 429, response.json)

    def test_verified_confirmation_is_idempotent_and_has_no_access_side_effects(self):
        row = self.seed(member_id=self.member_id)
        before = self.access_snapshot()
        event = self.event(row)
        self.assertTrue(self.handle(event))
        first = self.row(row['id'])
        self.assertEqual(first['state'], 'paid')
        self.assertIsNotNone(first['paid_at'])
        self.assertEqual(first['payment_intent'], event['data']['object']['payment_intent'])
        self.assertTrue(self.handle(event))
        event['id'] = 'evt_second_confirmation_fixture'
        event['type'] = 'checkout.session.async_payment_succeeded'
        self.assertTrue(self.handle(event))
        self.assertEqual(first, self.row(row['id']))
        self.assertEqual(before, self.access_snapshot())

    def test_expired_unpaid_checkout_needs_no_payment_intent_and_never_reverses_paid(self):
        row = self.seed()
        expired = self.event(row, 'checkout.session.expired')
        expired['data']['object'].update(payment_intent=None, payment_status='unpaid')
        self.assertTrue(self.handle(expired))
        self.assertEqual(self.row(row['id'])['state'], 'expired')
        self.assertIsNone(self.row(row['id'])['paid_at'])
        paid = self.seed()
        self.handle(self.event(paid))
        expired = self.event(paid, 'checkout.session.expired')
        expired['data']['object'].update(payment_intent=None, payment_status='unpaid')
        self.assertTrue(self.handle(expired))
        self.assertEqual(self.row(paid['id'])['state'], 'paid')

    def test_unpaid_completed_session_remains_pending_until_async_confirmation(self):
        row = self.seed()
        unpaid = self.event(row)
        unpaid['data']['object'].update(payment_intent=None, payment_status='unpaid')
        self.assertTrue(self.handle(unpaid))
        self.assertEqual(self.row(row['id'])['state'], 'pending')
        self.assertIsNone(self.row(row['id'])['paid_at'])
        self.assertIsNone(self.row(row['id'])['payment_intent'])
        self.assertTrue(self.handle(self.event(row, 'checkout.session.async_payment_succeeded')))
        self.assertEqual(self.row(row['id'])['state'], 'paid')

    def test_confirmation_rejects_amount_currency_checkout_and_metadata_mismatch(self):
        row = self.seed()
        original = self.row(row['id'])
        cases = [('amount_total', row['amount_cents']+1), ('amount_total', True),
                 ('amount_total', str(row['amount_cents'])), ('currency', 'usd'),
                 ('id', 'cs_live_other_fixture'), ('mode', 'subscription'),
                 ('payment_intent', None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                event = self.event(row)
                event['data']['object'][field] = value
                with self.assertRaises(ValueError):
                    self.handle(event)
                self.assertEqual(original, self.row(row['id']))
        foreign = self.seed()
        event = self.event(row)
        event['data']['object']['metadata']['contribution_id'] = foreign['id']
        with self.assertRaises(ValueError):
            self.handle(event)
        self.assertEqual(original, self.row(row['id']))

    def test_test_mode_connected_account_and_unrelated_events_cannot_credit(self):
        row = self.seed()
        original = self.row(row['id'])
        events = []
        event = self.event(row)
        event['livemode'] = False
        events.append(event)
        event = self.event(row)
        event['account'] = 'acct_other_fixture'
        events.append(event)
        event = self.event(row)
        event['data']['object']['livemode'] = False
        events.append(event)
        for event in events:
            with self.subTest(event=event):
                try:
                    handled = self.handle(event)
                except ValueError:
                    handled = False
                self.assertFalse(handled)
                self.assertEqual(original, self.row(row['id']))
        unrelated = self.event(row)
        unrelated['data']['object']['id'] = 'cs_live_unrelated_fixture'
        unrelated['data']['object']['metadata'] = {'contribution_id': secrets.token_hex(16)}
        self.assertFalse(self.handle(unrelated))
        self.assertEqual(original, self.row(row['id']))

    def test_partial_and_full_refunds_are_cumulative_not_double_counted(self):
        row = self.seed(amount=1000)
        self.handle(self.event(row))
        self.assertTrue(self.handle(self.refund(row, 250, metadata=False)))
        self.assertEqual(self.row(row['id'])['refunded_cents'], 250)
        self.assertEqual(self.row(row['id'])['state'], 'refunded')
        self.handle(self.refund(row, 250))
        summary = self.admin.get('/api/admin/contributions').json['summary']
        self.assertEqual(summary['gross_cents'], 1000)
        self.assertEqual(summary['refunded_cents'], 250)
        self.assertEqual(summary['net_cents'], 750)
        self.assertEqual(summary['confirmed_count'], 1)
        self.handle(self.refund(row, 1000))
        self.handle(self.refund(row, 250))
        self.assertEqual(self.row(row['id'])['refunded_cents'], 1000)
        summary = self.admin.get('/api/admin/contributions').json['summary']
        self.assertEqual(summary['gross_cents'], 1000)
        self.assertEqual(summary['refunded_cents'], 1000)
        self.assertEqual(summary['net_cents'], 0)

    def test_refund_before_checkout_confirmation_never_restores_paid_state(self):
        for amount in [250, 1000]:
            with self.subTest(refund=amount):
                row = self.seed(amount=1000)
                self.assertTrue(self.handle(self.refund(row, amount)))
                self.assertEqual(self.row(row['id'])['state'], 'refunded')
                self.assertIsNone(self.row(row['id'])['paid_at'])
                self.assertTrue(self.handle(self.event(row)))
                confirmed = self.row(row['id'])
                self.assertEqual(confirmed['state'], 'refunded')
                self.assertEqual(confirmed['refunded_cents'], amount)
                self.assertIsNotNone(confirmed['paid_at'])

    def test_malformed_refunds_cannot_reduce_or_inflate_totals(self):
        row = self.seed()
        self.handle(self.event(row))
        for amount in [-1, 1001, True, '1000']:
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    self.handle(self.refund(row, amount))
        event = self.refund(row, 1000)
        event['data']['object']['currency'] = 'usd'
        with self.assertRaises(ValueError):
            self.handle(event)
        self.assertEqual(self.row(row['id'])['refunded_cents'], 0)

    def test_disputed_payment_is_held_separately_and_completion_cannot_restore_it(self):
        row = self.seed()
        self.handle(self.event(row))
        dispute = self.event(row, 'charge.dispute.created', {
            'id': 'dp_fixture_'+row['id'], 'livemode': True,
            'payment_intent': 'pi_fixture'+row['id'],
            'amount': row['amount_cents'], 'currency': 'eur',
        })
        self.assertTrue(self.handle(dispute))
        self.assertEqual(self.row(row['id'])['state'], 'disputed')
        self.handle(self.event(row))
        self.assertEqual(self.row(row['id'])['state'], 'disputed')
        summary = self.admin.get('/api/admin/contributions').json['summary']
        self.assertEqual(summary['gross_cents'], 1000)
        self.assertEqual(summary['refunded_cents'], 0)
        self.assertEqual(summary['disputed_cents'], 1000)
        self.assertEqual(summary['net_cents'], 0)

    def test_admin_listing_is_private_bounded_and_contains_no_payment_secrets(self):
        for client in [self.member, self.guest]:
            self.assertEqual(client.get('/api/admin/contributions').status_code, 403)
        for number in range(27):
            self.seed(amount=100+number, member_id=self.member_id if number == 0 else None)
        response = self.admin.get('/api/admin/contributions')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        self.assertEqual(len(response.json['contributions']), 25)
        raw = response.get_data(as_text=True)
        for forbidden in ['private-password-sentinel', 'private-email-sentinel',
                          'password_hash', 'client_secret', 'payment_method_details', 'card_number']:
            self.assertNotIn(forbidden, raw)
        self.assertEqual(response.json['summary']['confirmed_count'], 0)

    def test_signed_platform_webhook_confirms_once_and_invalid_signature_does_not(self):
        row = self.seed(member_id=self.member_id)
        event = self.event(row)
        self.assertEqual(self.webhook(event, valid_signature=False).status_code, 400)
        self.assertIsNone(self.row(row['id'])['paid_at'])
        before = self.access_snapshot()
        response = self.webhook(event)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.row(row['id'])['state'], 'paid')
        self.assertTrue(self.webhook(event).json['duplicate'])
        self.assertEqual(before, self.access_snapshot())

    def test_confirmed_contribution_protects_member_and_payment_history_from_unpaid_cleanup(self):
        from account_archives import AccountDeletionBlocked, delete_unpaid_member
        row = self.seed(member_id=self.member_id)
        self.assertEqual(self.webhook(self.event(row)).status_code, 200)
        with self.app.app_context(), m.database() as conn:
            with self.assertRaises(AccountDeletionBlocked):
                delete_unpaid_member(conn, self.member_id)
            self.assertIsNotNone(conn.execute('SELECT id FROM members WHERE id=?', (self.member_id,)).fetchone())
        self.assertEqual(self.row(row['id'])['member_id'], self.member_id)
        self.assertEqual(self.row(row['id'])['state'], 'paid')

    def test_signed_webhook_amount_mismatch_is_not_confirmed_or_recorded_as_processed(self):
        row = self.seed()
        event = self.event(row)
        event['data']['object']['amount_total'] += 1
        self.assertEqual(self.webhook(event).status_code, 400)
        self.assertIsNone(self.row(row['id'])['paid_at'])
        self.assertEqual(self.row(row['id'])['state'], 'pending')
        with self.app.app_context(), m.database() as conn:
            self.assertIsNone(conn.execute('SELECT id FROM stripe_events WHERE id=?',
                                          (event['id'],)).fetchone())


if __name__ == '__main__':
    unittest.main()
