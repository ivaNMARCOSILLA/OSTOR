"""Stable account blocks and the owner's single, existing-account instruction."""
from datetime import datetime, timedelta
import json
import os
import secrets

from account_archives import _tables, close_member, is_archived
from membership import database, now_utc, stamp


OWNER_BLOCK_MIGRATION_ID = 'owner-block-loladrones-2026-11-12'
OWNER_BLOCK_CUTOFF = '2026-11-12T19:04:04+00:00'
OWNER_BLOCK_USERNAME = 'loladrones'
BLOCK_REASON = 'owner_requested_access_block'


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS account_blocks (
          member_id TEXT PRIMARY KEY REFERENCES members(id),blocked_at TEXT NOT NULL,
          reason TEXT NOT NULL,source TEXT NOT NULL
        );CREATE TABLE IF NOT EXISTS account_block_livekit_jobs (
          member_id TEXT PRIMARY KEY REFERENCES members(id),blocked_at TEXT NOT NULL,
          retry_until TEXT NOT NULL,next_attempt_at TEXT NOT NULL,lease_until TEXT,
          lease_token TEXT,last_attempt_at TEXT,last_success_at TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT,
          rooms_json TEXT NOT NULL DEFAULT '[]',completed_at TEXT,
          room_cursor TEXT NOT NULL DEFAULT '',sweep_started_at TEXT
        );CREATE INDEX IF NOT EXISTS account_block_pending ON account_block_livekit_jobs(completed_at,next_attempt_at);''')


def is_blocked(conn, member_id):
    """Check the stable signed-session ID even after normal auth becomes guest."""
    if not isinstance(member_id, str) or not member_id:
        return False
    return conn.execute('SELECT 1 FROM account_blocks WHERE member_id=?', (member_id,)).fetchone() is not None


def _known_rooms(conn, member_id, tables):
    if 'streamer_channels' not in tables:
        return [], None
    channel = conn.execute('SELECT id,room_name FROM streamer_channels WHERE member_id=?', (member_id,)).fetchone()
    rooms = []
    if channel:
        rooms.append({'room_name': channel['room_name'], 'owner': True, 'member_id': member_id})
    if 'live_guest_invites' in tables:
        rooms.extend({'room_name': row['room_name'], 'owner': False, 'member_id': member_id}
                     for row in conn.execute('''SELECT DISTINCT c.room_name FROM live_guest_invites i
                       JOIN streamer_channels c ON c.id=i.channel_id WHERE i.member_id=?''', (member_id,)).fetchall())
    return rooms, channel


def _revoke_permissions(conn, member_id, instant, tables):
    conn.execute("UPDATE members SET role='member',access_until=CASE WHEN access_until>? THEN ? ELSE access_until END WHERE id=?", (instant, instant, member_id))
    for table in ('pricing_moderators', 'service_grants', 'friend_access', 'live_entitlements', 'live_founders'):
        if table in tables:
            conn.execute('UPDATE '+table+' SET revoked_at=COALESCE(revoked_at,?) WHERE member_id=?', (instant, member_id))
    if 'ol_supervisors' in tables:
        conn.execute('UPDATE ol_supervisors SET can_review=0,revoked_at=COALESCE(revoked_at,?) WHERE member_id=?', (instant, member_id))
    if 'moderator_permissions' in tables:
        conn.execute('DELETE FROM moderator_permissions WHERE member_id=?', (member_id,))
    if 'streamer_access' in tables:
        conn.execute('UPDATE streamer_access SET until_at=CASE WHEN until_at>? THEN ? ELSE until_at END WHERE member_id=?', (instant, instant, member_id))


def _finish_archive(conn, member_id, instant, tables, was_archived, channel):
    # close_member deliberately short-circuits already archived accounts; these
    # remaining operations also secure a formerly archived imported account.
    if was_archived:
        conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?', (member_id,))
        conn.execute('DELETE FROM email_tokens WHERE member_id=?', (member_id,))
        conn.execute('DELETE FROM invitations WHERE member_id=? AND used_at IS NULL', (member_id,))
        conn.execute('DELETE FROM online_presence WHERE member_id=?', (member_id,))
        if 'stripe_connect_states' in tables:
            conn.execute('DELETE FROM stripe_connect_states WHERE member_id=?', (member_id,))
    if 'security_login_challenges' in tables:
        conn.execute('DELETE FROM security_login_challenges WHERE member_id=? AND used_at IS NULL', (member_id,))
    if channel:
        conn.execute('UPDATE streamer_channels SET room_name=?,live_until=NULL,updated_at=? WHERE id=?',
                     ('electronicama-'+secrets.token_hex(16), instant, channel['id']))
        if 'live_channel_thumbnails' in tables:
            conn.execute('DELETE FROM live_channel_thumbnails WHERE channel_id=?', (channel['id'],))
        if 'live_guest_invites' in tables:
            conn.execute('DELETE FROM live_guest_invites WHERE channel_id=?', (channel['id'],))
    if 'live_guest_invites' in tables:
        conn.execute('DELETE FROM live_guest_invites WHERE member_id=?', (member_id,))
    conn.execute('INSERT INTO member_archive_events VALUES(?,?,?,?,?)',
                 (secrets.token_hex(16), member_id, None, 'owner_block', instant))


def apply_owner_block_migration():
    """Block only the named account that existed when the owner requested it.

    Persist skipped outcomes too: a later registration or rename must never
    become the target. Network disconnections are durable jobs, never attempted
    inside the account transaction or claimed as complete by this migration.
    """
    if os.getenv('VERCEL') != '1' or os.getenv('VERCEL_ENV') != 'production':
        return None
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT result FROM owner_access_migrations WHERE id=?', (OWNER_BLOCK_MIGRATION_ID,)).fetchone()
        if previous:
            return json.loads(previous['result'])
        target = conn.execute('''SELECT m.id,m.username,m.role,m.created_at,
            CASE WHEN EXISTS(SELECT 1 FROM member_name_history h WHERE h.member_id=m.id
                AND h.changed_at>?) THEN 1 ELSE 0 END AS recently_renamed
            FROM members m WHERE m.username=?''', (OWNER_BLOCK_CUTOFF, OWNER_BLOCK_USERNAME)).fetchone()
        result = {'status': 'skipped_missing_existing_account', 'requested_username': OWNER_BLOCK_USERNAME}
        instant = now_utc()
        at = stamp(instant)
        if target:
            result.update(member_id=target['id'], username=target['username'], previous_role=target['role'], role=target['role'])
            try:
                created = datetime.fromisoformat(target['created_at'])
                existing = created.tzinfo is not None and created <= datetime.fromisoformat(OWNER_BLOCK_CUTOFF)
            except (TypeError, ValueError):
                existing = False
            if not existing:
                result['status'] = 'skipped_new_or_unknown_account'
            elif target['recently_renamed']:
                result['status'] = 'skipped_renamed_account'
            else:
                member_id = target['id']
                tables = _tables(conn)
                rooms, channel = _known_rooms(conn, member_id, tables)
                was_blocked = is_blocked(conn, member_id)
                was_archived = is_archived(conn, member_id)
                _revoke_permissions(conn, member_id, at, tables)
                close_member(conn, member_id, reason=BLOCK_REASON)
                _finish_archive(conn, member_id, at, tables, was_archived, channel)
                conn.execute('''INSERT INTO account_blocks(member_id,blocked_at,reason,source)
                    VALUES(?,?,?,?) ON CONFLICT(member_id) DO NOTHING''',
                             (member_id, at, BLOCK_REASON, OWNER_BLOCK_MIGRATION_ID))
                conn.execute('''INSERT INTO account_block_livekit_jobs
                    (member_id,blocked_at,retry_until,next_attempt_at,rooms_json)
                    VALUES(?,?,?,?,?) ON CONFLICT(member_id) DO NOTHING''',
                             (member_id, at, stamp(instant+timedelta(seconds=360)), at,
                              json.dumps(rooms, separators=(',', ':'))))
                result.update(status='already_blocked' if was_blocked else 'blocked', role='member',
                              session_revoked=True, archived=True, live_disconnect_pending=True)
        conn.execute('INSERT INTO owner_access_migrations(id,applied_at,result) VALUES(?,?,?)',
                     (OWNER_BLOCK_MIGRATION_ID, at, json.dumps(result, separators=(',', ':'))))
    return result
