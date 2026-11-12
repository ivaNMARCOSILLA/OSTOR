"""Revocation removes every matching transport, retries failures and limits work."""
import json
import os
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from flask import Flask

import account_block_livekit as worker
import membership as members


class FakeRooms:
    def __init__(self, participants=None, fail=None, budget=None):
        self.participants = participants or {}
        self.fail = fail
        self.budget = budget
        self.calls = []

    def call(self, action, data, grants):
        if self.budget is not None and len(self.calls) >= self.budget:
            raise worker.TickExhausted
        self.calls.append((action, dict(data), grants))
        if self.fail == (action, data.get('room')):
            raise worker.ServiceUnavailable
        if action == 'ListRooms':
            return {'rooms': [{'name': name} for name in self.participants]}
        if action == 'ListParticipants':
            return {'participants': [{'identity': identity} for identity in self.participants[data['room']]]}
        return {}


class BlockLivekitSweepTests(unittest.TestCase):
    def setUp(self):
        self.now = members.now_utc()
        self.mid = 'a' * 32
        self.job = {'member_id': self.mid, 'rooms_json': '[]', 'room_cursor': '',
                    'sweep_started_at': None, 'last_error': None,
                    'retry_until': members.stamp(self.now + timedelta(seconds=360))}

    def identity(self, suffix='publisher'):
        return 'maggy-' + self.mid + '-' + suffix

    def test_only_exact_minted_member_identities_match(self):
        for identity in [self.identity(), self.identity('012345abcd')]:
            self.assertTrue(worker.belongs_to_member(identity, self.mid))
        for identity in [None, self.identity(''), self.identity('012345abc'),
                         self.identity('012345abcde'), self.identity('PUBLISHER'),
                         'x' + self.identity(), self.identity() + '-other',
                         'maggy-' + self.mid + 'b-publisher']:
            self.assertFalse(worker.belongs_to_member(identity, self.mid), identity)

    def test_all_rooms_and_all_target_transports_removed_without_affecting_others(self):
        service = FakeRooms({'one': [self.identity(), self.identity('012345abcd'), 'other'],
                             'two': [self.identity('abcdef0123')], 'three': ['other-2']})
        state = worker._sweep(self.job, service)
        removed = [data for action, data, _ in service.calls if action == 'RemoveParticipant']
        self.assertEqual(removed, [
            {'room': 'one', 'identity': self.identity()},
            {'room': 'one', 'identity': self.identity('012345abcd')},
            {'room': 'two', 'identity': self.identity('abcdef0123')},
        ])
        self.assertIsNone(state['completed_at'])
        self.assertTrue(state['full_sweep'])

    def test_owned_room_deleted_but_guest_room_never_deleted(self):
        self.job['rooms_json'] = json.dumps([
            {'room_name': 'own-room', 'owner': True, 'member_id': self.mid},
            {'room_name': 'other-room', 'owner': False, 'member_id': self.mid},
        ])
        service = FakeRooms({'other-room': [self.identity()]})
        state = worker._sweep(self.job, service)
        self.assertEqual([data['room'] for action, data, _ in service.calls if action == 'DeleteRoom'], ['own-room'])
        self.assertEqual(json.loads(state['rooms_json']), [])

    def test_budget_exhaustion_inside_room_resumes_room_instead_of_skipping_transport(self):
        service = FakeRooms({'one': [], 'two': [self.identity(), self.identity('012345abcd')]}, budget=4)
        state = worker._sweep(self.job, service)
        self.assertEqual(state['room_cursor'], 'one')
        self.assertFalse(state['full_sweep'])
        resumed = worker._sweep(self.job | state, FakeRooms({'one': [], 'two': [self.identity('012345abcd')]}))
        self.assertTrue(resumed['full_sweep'])

    def test_error_does_not_starve_other_rooms_and_never_completes(self):
        self.job['retry_until'] = members.stamp(self.now - timedelta(seconds=1))
        service = FakeRooms({'one': [], 'two': [self.identity()]}, fail=('ListParticipants', 'one'))
        state = worker._sweep(self.job, service)
        self.assertTrue(any(action == 'RemoveParticipant' for action, _, _ in service.calls))
        self.assertEqual(state['last_error'], 'livekit_unconfirmed')
        self.assertIsNone(state['completed_at'])

    def test_completion_requires_fresh_sweep_started_after_last_join_token_expiry(self):
        self.job['retry_until'] = members.stamp(self.now - timedelta(seconds=1))
        self.job.update(room_cursor='one', sweep_started_at=members.stamp(self.now - timedelta(seconds=30)))
        prior = worker._sweep(self.job, FakeRooms({'one': []}))
        self.assertIsNone(prior['completed_at'])
        state = worker._sweep(self.job | prior, FakeRooms())
        self.assertIsNotNone(state['completed_at'])

    def test_service_rejects_remote_errors_and_redirects_with_bounded_timeouts(self):
        environment = {'LIVEKIT_URL': 'wss://live.example.test', 'LIVEKIT_API_KEY': 'test',
                       'LIVEKIT_API_SECRET': 'x' * 32}
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 302
        with patch.dict(os.environ, environment), patch.object(worker.requests, 'post', return_value=response) as post:
            service = worker.RoomService()
            with self.assertRaises(worker.ServiceUnavailable):
                service.call('ListRooms', {}, {'roomList': True})
            kwargs = post.call_args.kwargs
            self.assertFalse(kwargs['allow_redirects'])
            self.assertLessEqual(sum(kwargs['timeout']), 2)
            self.assertTrue(kwargs['headers']['Authorization'].startswith('Bearer '))

    def test_service_hard_caps_number_of_remote_calls(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 200
        response.json.return_value = {}
        with patch.dict(os.environ, {'LIVEKIT_URL': 'wss://live.example.test', 'LIVEKIT_API_KEY': 'test', 'LIVEKIT_API_SECRET': 'x' * 32}), patch.object(worker.requests, 'post', return_value=response) as post:
            service = worker.RoomService()
            for _ in range(worker.MAX_CALLS):
                service.call('ListRooms', {}, {'roomList': True})
            with self.assertRaises(worker.TickExhausted):
                service.call('ListRooms', {}, {'roomList': True})
            self.assertEqual(post.call_count, worker.MAX_CALLS)

    def test_disabling_new_streams_does_not_disable_existing_session_revocation(self):
        with patch.dict(os.environ, {'LIVEKIT_URL': 'wss://live.example.test', 'LIVEKIT_API_KEY': 'test',
                                    'LIVEKIT_API_SECRET': 'x' * 32, 'MAGGY_STREAMERS_ENABLED': '0'}):
            self.assertTrue(worker.service_ready())


class BlockLivekitDurabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-block-worker-only',
                               MEMBERSHIP_DATABASE=str(Path(temporary.name) / 'blocks.sqlite3'),
                               MEMBERSHIP_DATABASE_URL=None)
        self.mid = 'a' * 32
        with self.app.app_context():
            members.init_database()
            import account_blocks
            account_blocks.init_database()
            with members.database() as conn:
                now = members.stamp(members.now_utc())
                conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)', (self.mid, 'blocked-transport', now))
                conn.execute('INSERT INTO account_blocks(member_id,blocked_at,reason,source) VALUES(?,?,?,?)', (self.mid, now, 'owner', 'test'))
                conn.execute('''INSERT INTO account_block_livekit_jobs(member_id,blocked_at,retry_until,next_attempt_at)
                    VALUES(?,?,?,?)''', (self.mid, now, members.stamp(members.now_utc() - timedelta(seconds=1)), now))

    def row(self):
        with self.app.app_context(), members.database() as conn:
            return dict(conn.execute('SELECT * FROM account_block_livekit_jobs WHERE member_id=?', (self.mid,)).fetchone())

    def test_missing_configuration_keeps_pending_without_claiming_disconnect(self):
        with self.app.app_context(), patch.object(worker, 'service_ready', return_value=False):
            result = worker.run_pending()
        row = self.row()
        self.assertEqual(result, {'attempted': 1, 'completed': 0})
        self.assertEqual(row['last_error'], 'livekit_not_configured')
        self.assertIsNone(row['completed_at'])
        self.assertIsNone(row['lease_token'])
        self.assertEqual(row['attempts'], 1)

    def test_remote_calls_happen_after_claim_commit_and_completed_jobs_are_not_repeated(self):
        def rooms():
            # A second database connection can acquire the write lock while the
            # service is constructed, proving no claim transaction surrounds I/O.
            with members.database() as conn:
                conn.execute('BEGIN IMMEDIATE')
                self.assertIsNotNone(conn.execute('SELECT lease_token FROM account_block_livekit_jobs').fetchone()['lease_token'])
            return FakeRooms()
        with self.app.app_context(), patch.object(worker, 'service_ready', return_value=True), patch.object(worker, 'RoomService', side_effect=rooms):
            self.assertEqual(worker.run_pending(), {'attempted': 1, 'completed': 1})
            self.assertEqual(worker.run_pending(), {'attempted': 0, 'completed': 0})
        self.assertIsNotNone(self.row()['last_success_at'])

    def test_lease_prevents_concurrent_worker_and_expired_lease_is_recoverable(self):
        with self.app.app_context(), members.database() as conn:
            conn.execute('UPDATE account_block_livekit_jobs SET lease_token=?,lease_until=?',
                         ('existing-lease', members.stamp(members.now_utc() + timedelta(seconds=30))))
        with self.app.app_context():
            self.assertIsNone(worker._claim())
            with members.database() as conn:
                conn.execute('UPDATE account_block_livekit_jobs SET lease_until=?',
                             (members.stamp(members.now_utc() - timedelta(seconds=1)),))
            self.assertNotEqual(worker._claim()['lease_token'], 'existing-lease')

    def test_stale_worker_cannot_clear_newer_lease(self):
        def replace_lease(job, service):
            with members.database() as conn:
                conn.execute("UPDATE account_block_livekit_jobs SET lease_token='new-lease'")
            return dict(job, full_sweep=True, completed_at=members.stamp(members.now_utc()))
        with self.app.app_context(), patch.object(worker, 'service_ready', return_value=True), patch.object(worker, '_sweep', side_effect=replace_lease):
            self.assertEqual(worker.run_pending(), {'attempted': 1, 'completed': 0})
        self.assertEqual(self.row()['lease_token'], 'new-lease')
        self.assertIsNone(self.row()['completed_at'])
