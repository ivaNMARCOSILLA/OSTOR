"""Durable, bounded removal of blocked accounts from existing LiveKit sessions.

Revoking a website session does not close a WebRTC transport. Each request tick
performs a small part of a room sweep without retaining a database transaction
during network calls. Sweeps continue beyond the application's 300-second join
token lifetime, then finish with a complete fresh sweep. Room ownership and
recording history are never deleted from the database.
"""
import json
import os
import re
import secrets
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse

import requests

from membership import database, now_utc, stamp


MAX_CALLS = 8
TICK_SECONDS = 4
RETRY_SECONDS = 15
LEASE_SECONDS = 30


class ServiceUnavailable(Exception):
    """A remote operation was not confirmed; no service response is disclosed."""


class TickExhausted(Exception):
    pass


def service_ready():
    # Disabling new broadcasts must not prevent removing an old connection.
    from streamers import video_configuration_checks
    checks = video_configuration_checks()
    return all(checks[key] for key in ('LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET'))


def belongs_to_member(identity, member_id):
    """Match only identities minted by this application's publisher/viewer code."""
    return isinstance(identity, str) and bool(re.fullmatch(
        r'maggy-' + re.escape(member_id) + r'-(?:publisher|[0-9a-f]{10})', identity,
    ))


class RoomService:
    def __init__(self):
        self.deadline = time.monotonic() + TICK_SECONDS
        self.calls = 0

    def call(self, action, data, grants):
        remaining = self.deadline - time.monotonic()
        if self.calls >= MAX_CALLS or remaining < .2:
            raise TickExhausted
        self.calls += 1
        from streamers import sign_token
        instant = int(time.time())
        token = sign_token({'iss': os.environ['LIVEKIT_API_KEY'].strip(),
                            'iat': instant, 'nbf': instant - 5, 'exp': instant + 45,
                            'video': grants})
        url = ('https://' + urlparse(os.environ['LIVEKIT_URL'].strip()).netloc
               + '/twirp/livekit.RoomService/' + action)
        timeout = min(1.0, remaining / 2)
        try:
            with requests.post(url, json=data, headers={'Authorization': 'Bearer ' + token},
                               timeout=(timeout, timeout), allow_redirects=False) as response:
                if response.status_code == 404 and action != 'ListRooms':
                    return {}
                if response.status_code != 200:
                    raise ServiceUnavailable
                result = response.json()
                if not isinstance(result, dict):
                    raise ServiceUnavailable
                return result
        except (requests.RequestException, ValueError, TypeError) as error:
            raise ServiceUnavailable from error


def _claim():
    instant = now_utc()
    token = secrets.token_hex(16)
    with database() as conn:
        # Normal account checks do not need the shared write lock when there is
        # no due work. Recheck under the lock before actually claiming a job.
        if not conn.execute('''SELECT 1 FROM account_block_livekit_jobs j
            JOIN account_blocks b ON b.member_id=j.member_id
            WHERE j.completed_at IS NULL AND j.next_attempt_at<=?
            AND (j.lease_until IS NULL OR j.lease_until<=?) LIMIT 1''',
                            (stamp(instant), stamp(instant))).fetchone():
            return None
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''SELECT j.* FROM account_block_livekit_jobs j
            JOIN account_blocks b ON b.member_id=j.member_id
            WHERE j.completed_at IS NULL AND j.next_attempt_at<=?
            AND (j.lease_until IS NULL OR j.lease_until<=?)
            ORDER BY j.next_attempt_at,j.member_id LIMIT 1''', (stamp(instant), stamp(instant))).fetchone()
        if not row:
            return None
        conn.execute('''UPDATE account_block_livekit_jobs SET lease_token=?,lease_until=?,
            last_attempt_at=?,attempts=attempts+1 WHERE member_id=?''',
                     (token, stamp(instant + timedelta(seconds=LEASE_SECONDS)),
                      stamp(instant), row['member_id']))
    return dict(row) | {'lease_token': token}


def _sweep(job, service):
    """Advance only past fully processed rooms, so budget exhaustion is resumable."""
    cursor = job['room_cursor'] or ''
    started = job['sweep_started_at'] if cursor else stamp(now_utc())
    error = job['last_error'] if cursor else None
    state = {'rooms_json': job['rooms_json'], 'room_cursor': cursor,
             'sweep_started_at': started, 'last_error': error, 'completed_at': None}
    try:
        rooms_to_close = json.loads(job['rooms_json'])
        if not isinstance(rooms_to_close, list) or any(not isinstance(room, dict) for room in rooms_to_close):
            raise ServiceUnavailable
        pending = [room for room in rooms_to_close if room.get('owner')]
        state['rooms_json'] = json.dumps(pending)
        for room in pending[:]:
            name = room.get('room_name')
            if not isinstance(name, str) or not name:
                raise ServiceUnavailable
            try:
                service.call('DeleteRoom', {'room': name}, {'roomCreate': True})
                pending.remove(room)
                state['rooms_json'] = json.dumps(pending)
            except ServiceUnavailable:
                state['last_error'] = 'livekit_unconfirmed'
        listing = service.call('ListRooms', {}, {'roomList': True})
        rooms = listing.get('rooms', [])
        if not isinstance(rooms, list) or any(not isinstance(room, dict) or not isinstance(room.get('name'), str) for room in rooms):
            raise ServiceUnavailable
        for name in sorted({room['name'] for room in rooms if room['name'] > cursor}):
            grants = {'roomAdmin': True, 'room': name}
            try:
                listing = service.call('ListParticipants', {'room': name}, grants)
                participants = listing.get('participants', [])
                if not isinstance(participants, list) or any(not isinstance(item, dict) for item in participants):
                    raise ServiceUnavailable
                for participant in participants:
                    identity = participant.get('identity')
                    if belongs_to_member(identity, job['member_id']):
                        service.call('RemoveParticipant', {'room': name, 'identity': identity}, grants)
            except ServiceUnavailable:
                # A failing room cannot starve removal from the remaining rooms.
                # The entire sweep remains unconfirmed and will run again.
                state['last_error'] = 'livekit_unconfirmed'
            state['room_cursor'] = name
        instant = now_utc()
        if not state['last_error'] and datetime.fromisoformat(started) >= datetime.fromisoformat(job['retry_until']):
            state['completed_at'] = stamp(instant)
        else:
            state['room_cursor'] = ''
            state['sweep_started_at'] = None
        state['full_sweep'] = not state['last_error']
    except TickExhausted:
        state['full_sweep'] = False
    except (ServiceUnavailable, ValueError, TypeError, KeyError):
        state['last_error'] = 'livekit_unconfirmed'
        state['full_sweep'] = False
    return state


def run_pending():
    """Process at most one leased job; never claim success on missing credentials."""
    job = _claim()
    if not job:
        return {'attempted': 0, 'completed': 0}
    if service_ready():
        state = _sweep(job, RoomService())
    else:
        state = dict(job, full_sweep=False, last_error='livekit_not_configured')
    instant = now_utc()
    successful_sweep = stamp(instant) if state.get('full_sweep') else job['last_success_at']
    with database() as conn:
        updated = conn.execute('''UPDATE account_block_livekit_jobs SET
            lease_token=NULL,lease_until=NULL,next_attempt_at=?,last_success_at=?,last_error=?,
            rooms_json=?,room_cursor=?,sweep_started_at=?,completed_at=?
            WHERE member_id=? AND lease_token=?''',
            (stamp(instant + timedelta(seconds=RETRY_SECONDS)), successful_sweep,
             state['last_error'], state['rooms_json'], state['room_cursor'],
             state['sweep_started_at'], state['completed_at'], job['member_id'], job['lease_token'])).rowcount
    return {'attempted': 1, 'completed': int(bool(updated and state['completed_at']))}
