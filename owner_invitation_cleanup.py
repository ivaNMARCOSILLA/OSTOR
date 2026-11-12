"""One-time removal of existing friend-invitation accounts, preserving evidence."""
from datetime import datetime
import json
import os
import secrets

from account_archives import AccountDeletionBlocked, _tables, close_member, delete_unpaid_member
from membership import database, now_utc, stamp


OWNER_INVITATION_CLEANUP_ID = 'owner-delete-existing-friend-invitations-2026-11-12'
OWNER_INVITATION_CUTOFF = '2026-11-12T19:56:52+00:00'
VIDEO_OWNER_SOURCE = 'owner-adminsiempre-video-upload-2026-11-12'


def _existing(value):
    try:
        instant = datetime.fromisoformat(value)
        return instant.tzinfo is not None and instant <= datetime.fromisoformat(OWNER_INVITATION_CUTOFF)
    except (TypeError, ValueError):
        return False


def _protection(conn, member, tables):
    ident = member['id']
    if member['role'] == 'admin':
        return 'kept_administrator'
    if 'account_blocks' in tables and conn.execute('SELECT 1 FROM account_blocks WHERE member_id=?', (ident,)).fetchone():
        return 'kept_blocked'
    if (member['username'] == 'rosas' or member['exempt_reason'] == 'owner_rosas'
            or conn.execute("SELECT 1 FROM member_identity_links WHERE member_id=? AND identity IN ('rosas','flores')", (ident,)).fetchone()):
        return 'kept_owner'
    if 'pricing_moderators' in tables and conn.execute('SELECT 1 FROM pricing_moderators WHERE member_id=? AND revoked_at IS NULL', (ident,)).fetchone():
        return 'kept_staff'
    if 'ol_supervisors' in tables and conn.execute('SELECT 1 FROM ol_supervisors WHERE member_id=? AND can_review=1 AND revoked_at IS NULL', (ident,)).fetchone():
        return 'kept_staff'
    if 'video_upload_grants' in tables and conn.execute('SELECT 1 FROM video_upload_grants WHERE member_id=? AND source=?', (ident, VIDEO_OWNER_SOURCE)).fetchone():
        return 'kept_video_owner_command'
    return None


def apply_owner_invitation_cleanup():
    """Return (durable result, formerly live rooms); perform no network calls.

    Friend access can also be granted to a genuine self-service registration, so
    it alone never qualifies an account for removal. Missing legacy evidence is
    retained. Only this initial production snapshot is eligible, even if a later
    account reuses a removed username.
    """
    if os.getenv('VERCEL') != '1' or os.getenv('VERCEL_ENV') != 'production':
        return None, []
    rooms = []
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT result FROM owner_access_migrations WHERE id=?', (OWNER_INVITATION_CLEANUP_ID,)).fetchone()
        if previous:
            return json.loads(previous['result']), []
        tables = _tables(conn)
        candidates = conn.execute('''SELECT m.id,m.username,m.role,m.created_at,
            r.origin,r.exempt_reason,f.granted_at,
            CASE WHEN EXISTS(SELECT 1 FROM invitations i WHERE i.member_id=m.id)
                THEN 1 ELSE 0 END AS invitation_record
            FROM members m LEFT JOIN registration_access r ON r.member_id=m.id
            LEFT JOIN friend_access f ON f.member_id=m.id
            WHERE r.origin='owner_invitation' OR
                ((r.origin IS NULL OR r.origin='legacy_unknown') AND f.member_id IS NOT NULL)
            ORDER BY m.created_at,m.id''').fetchall()
        outcomes = []
        changed = False
        for member in candidates:
            status = _protection(conn, member, tables)
            if not status and not _existing(member['created_at']):
                status = 'kept_new_or_unknown_account'
            if not status and member['granted_at'] is not None and not _existing(member['granted_at']):
                status = 'kept_new_or_unknown_grant'
            if not status and member['origin'] != 'owner_invitation':
                if not member['invitation_record'] or not _existing(member['granted_at']):
                    status = 'kept_ambiguous_legacy'
            if not status:
                try:
                    rooms.extend(delete_unpaid_member(conn, member['id']))
                    status = 'deleted'
                except AccountDeletionBlocked:
                    rooms.extend(close_member(conn, member['id'], reason='owner_invitation_cleanup'))
                    conn.execute('DELETE FROM invitations WHERE member_id=?', (member['id'],))
                    status = 'archived_protected_history'
                changed = True
            outcomes.append({'member_id': member['id'], 'username': member['username'], 'status': status})
        if changed and 'interface_revisions' in tables:
            for topic in ('account', 'public'):
                conn.execute('INSERT INTO interface_revisions(topic,version) VALUES(?,?) ON CONFLICT(topic) DO UPDATE SET version=excluded.version',
                             (topic, secrets.token_hex(16)))
        counts = {}
        for outcome in outcomes:
            counts[outcome['status']] = counts.get(outcome['status'], 0) + 1
        result = {'status': 'applied', 'cutoff': OWNER_INVITATION_CUTOFF, 'counts': counts, 'accounts': outcomes}
        conn.execute('INSERT INTO owner_access_migrations(id,applied_at,result) VALUES(?,?,?)',
                     (OWNER_INVITATION_CLEANUP_ID, stamp(now_utc()), json.dumps(result, separators=(',', ':'))))
    return result, rooms
