"""A stable account grant limited to the community video upload workflow."""
from datetime import datetime
import json
import os
import re

from account_archives import is_archived
from account_blocks import is_blocked
from membership import database, now_utc, stamp


OWNER_UPLOAD_MIGRATION_ID = 'owner-adminsiempre-video-upload-2026-11-12'
OWNER_UPLOAD_CUTOFF = '2026-11-12T19:20:00+00:00'
OWNER_ADMIN_MIGRATION_ID = 'owner-admin-adminsiempre-2026-11-12'
_IDENT = r'[a-f0-9]{32}'


def init_database():
    with database() as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS video_upload_grants (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
          granted_at TEXT NOT NULL,source TEXT NOT NULL,revoked_at TEXT
        );''')


def _active(conn, member_id):
    return (conn.execute('SELECT 1 FROM members WHERE id=?', (member_id,)).fetchone() is not None
            and not is_archived(conn, member_id) and not is_blocked(conn, member_id))


def _upload_route(path, method):
    if method == 'GET':
        return path in {'/api/videos/config', '/api/videos/me'}
    if method != 'POST':
        return False
    return (path == '/api/videos/uploads'
            or re.fullmatch('/api/videos/uploads/' + _IDENT + '/(?:parts|complete)', path) is not None
            or re.fullmatch('/api/videos/' + _IDENT + '/delete', path) is not None)


def permits(user, path, method):
    """Bypass only the signup fee for upload steps; normal ownership still applies."""
    if not user or not _upload_route(path, method):
        return False
    member_id = user['id']
    with database() as conn:
        return (_active(conn, member_id) and conn.execute(
            'SELECT 1 FROM video_upload_grants WHERE member_id=? AND revoked_at IS NULL',
            (member_id,)).fetchone() is not None)


def _existing(created_at):
    try:
        created = datetime.fromisoformat(created_at)
        return created.tzinfo is not None and created <= datetime.fromisoformat(OWNER_UPLOAD_CUTOFF)
    except (TypeError, ValueError):
        return False


def apply_owner_upload_migration():
    """Resolve the owner's existing account once, without changing any role."""
    if os.getenv('VERCEL') != '1' or os.getenv('VERCEL_ENV') != 'production':
        return None
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT result FROM owner_access_migrations WHERE id=?',
                                (OWNER_UPLOAD_MIGRATION_ID,)).fetchone()
        if previous:
            return json.loads(previous['result'])
        prior = conn.execute('SELECT result FROM owner_access_migrations WHERE id=?',
                             (OWNER_ADMIN_MIGRATION_ID,)).fetchone()
        stable_id = None
        invalid_prior = False
        if prior:
            try:
                outcome = json.loads(prior['result'])
                if not isinstance(outcome, dict) or not isinstance(outcome.get('status'), str):
                    invalid_prior = True
                elif outcome['status'] in {'granted', 'already_admin'}:
                    candidate = outcome.get('member_id')
                    if isinstance(candidate, str) and re.fullmatch(_IDENT, candidate):
                        stable_id = candidate
                    else:
                        invalid_prior = True
            except (AttributeError, TypeError, ValueError):
                invalid_prior = True
        if stable_id:
            target = conn.execute('SELECT id,username,password_hash,created_at FROM members WHERE id=?',
                                  (stable_id,)).fetchone()
        else:
            target = conn.execute('SELECT id,username,password_hash,created_at FROM members WHERE username=?',
                                  ('adminsiempre',)).fetchone()
        result = {'status': 'skipped_missing_existing_account'}
        if invalid_prior:
            result['status'] = 'skipped_invalid_prior_identity'
        elif target:
            member_id = target['id']
            result.update(member_id=member_id, username=target['username'])
            renamed_later = not stable_id and conn.execute('''SELECT 1 FROM member_name_history
                WHERE member_id=? AND changed_at>? LIMIT 1''', (member_id, OWNER_UPLOAD_CUTOFF)).fetchone()
            if not _existing(target['created_at']):
                result['status'] = 'skipped_new_or_unknown_account'
            elif renamed_later:
                result['status'] = 'skipped_renamed_account'
            elif not target['password_hash']:
                result['status'] = 'skipped_unactivated_account'
            elif not _active(conn, member_id):
                result['status'] = 'skipped_inactive_account'
            else:
                instant = stamp(now_utc())
                conn.execute('''INSERT INTO video_upload_grants(member_id,granted_at,source,revoked_at)
                    VALUES(?,?,?,NULL) ON CONFLICT(member_id) DO NOTHING''',
                             (member_id, instant, OWNER_UPLOAD_MIGRATION_ID))
                grant = conn.execute('SELECT revoked_at FROM video_upload_grants WHERE member_id=?',
                                     (member_id,)).fetchone()
                result['status'] = 'granted' if grant['revoked_at'] is None else 'skipped_revoked_grant'
        conn.execute('INSERT INTO owner_access_migrations(id,applied_at,result) VALUES(?,?,?)',
                     (OWNER_UPLOAD_MIGRATION_ID, stamp(now_utc()), json.dumps(result, separators=(',', ':'))))
    return result
