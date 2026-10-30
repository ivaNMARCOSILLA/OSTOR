"""Account closure and unpaid-account deletion with protected financial evidence."""
import json
import os
import secrets
import time
from urllib.parse import urlparse

import requests
from flask import Blueprint, current_app, jsonify

from membership import database, get_user, payload, require_admin, stamp, now_utc
from storage import INTEGRITY_ERRORS, PostgresConnection

bp = Blueprint('account_archives', __name__)
OWNER_CLEANUP_ID = 'owner-delete-existing-test-accounts-2026-10-30'


class AccountDeletionBlocked(ValueError):
    """The account must remain available for financial/history review."""


def init_database():
    with database() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS member_archives (
          member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
          archived_at TEXT NOT NULL,archived_by TEXT REFERENCES members(id),
          reason TEXT NOT NULL,restored_at TEXT
        );
        CREATE TABLE IF NOT EXISTS member_archive_events (
          id TEXT PRIMARY KEY,member_id TEXT NOT NULL REFERENCES members(id),
          actor_id TEXT REFERENCES members(id),action TEXT NOT NULL,created_at TEXT NOT NULL
        );
        ''')


def is_archived(conn, member_id):
    return conn.execute('SELECT 1 FROM member_archives WHERE member_id=? AND restored_at IS NULL',
                        (member_id,)).fetchone() is not None


def _tables(conn):
    if isinstance(conn, PostgresConnection):
        return {r['table_name'] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='maggy'").fetchall()}
    return {r['name'] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def close_member(conn, member_id, actor_id=None, reason='admin_account_closure'):
    """Caller holds BEGIN IMMEDIATE. Returns only formerly live rooms to close."""
    member = conn.execute('SELECT id,role FROM members WHERE id=?', (member_id,)).fetchone()
    if not member or member['role'] == 'admin' or member_id == actor_id:
        raise ValueError('No se puede dar de baja una cuenta administradora ni la sesión propia.')
    if is_archived(conn, member_id):
        return []
    instant = stamp(now_utc())
    conn.execute('INSERT INTO member_archives VALUES(?,?,?,?,NULL) ON CONFLICT(member_id) DO UPDATE SET archived_at=excluded.archived_at,archived_by=excluded.archived_by,reason=excluded.reason,restored_at=NULL',
                 (member_id, instant, actor_id, reason))
    conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?', (member_id,))
    conn.execute('INSERT INTO member_archive_events VALUES(?,?,?,?,?)',
                 (secrets.token_hex(16), member_id, actor_id, 'archive', instant))
    conn.execute('DELETE FROM email_tokens WHERE member_id=?', (member_id,))
    conn.execute('DELETE FROM invitations WHERE member_id=? AND used_at IS NULL', (member_id,))
    conn.execute('DELETE FROM online_presence WHERE member_id=?', (member_id,))
    tables = _tables(conn)
    rooms = []
    if 'stripe_connect_states' in tables:
        conn.execute('DELETE FROM stripe_connect_states WHERE member_id=?', (member_id,))
    if 'streamer_channels' in tables:
        channel = conn.execute('SELECT id,room_name,live_until FROM streamer_channels WHERE member_id=?', (member_id,)).fetchone()
        if channel:
            if channel['live_until'] is not None:
                rooms.append({'room_name': channel['room_name'], 'owner': True, 'member_id': member_id})
            conn.execute('UPDATE streamer_channels SET live_until=NULL,updated_at=? WHERE id=?', (instant, channel['id']))
            if 'live_channel_thumbnails' in tables:
                conn.execute('DELETE FROM live_channel_thumbnails WHERE channel_id=?', (channel['id'],))
            if 'live_guest_invites' in tables:
                conn.execute('DELETE FROM live_guest_invites WHERE channel_id=?', (channel['id'],))
        if 'live_guest_invites' in tables:
            for guest in conn.execute('SELECT c.room_name FROM live_guest_invites i JOIN streamer_channels c ON c.id=i.channel_id WHERE i.member_id=? AND c.live_until IS NOT NULL', (member_id,)).fetchall():
                rooms.append({'room_name': guest['room_name'], 'owner': False, 'member_id': member_id})
            conn.execute('DELETE FROM live_guest_invites WHERE member_id=?', (member_id,))
    # The archive is the authoritative authentication block. Financial periods,
    # grants, passwords, founder history and recordings are retained for review.
    return rooms


def delete_unpaid_member(conn, member_id, actor_id=None):
    """Caller holds BEGIN IMMEDIATE. Delete only an account without protected history.

    All checks precede changes. The savepoint also protects against an additional
    foreign key introduced by a later schema version; other members are untouched.
    """
    member = conn.execute('SELECT id,role FROM members WHERE id=?', (member_id,)).fetchone()
    if not member or member['role'] == 'admin' or member_id == actor_id:
        raise ValueError('No se puede borrar una cuenta administradora ni la sesión propia.')
    tables = _tables(conn)

    def has(table, condition, parameters):
        return table in tables and conn.execute(
            'SELECT 1 FROM '+table+' WHERE '+condition+' LIMIT 1', parameters,
        ).fetchone() is not None

    channels = conn.execute('SELECT id,room_name,live_until FROM streamer_channels WHERE member_id=?',
                            (member_id,)).fetchall() if 'streamer_channels' in tables else []
    channel_ids = [row['id'] for row in channels]
    channel_marks = ','.join('?' for _ in channel_ids)
    scope = 'member_id=?' + (' OR channel_id IN ('+channel_marks+')' if channel_ids else '')
    scope_args = (member_id, *channel_ids)
    financial = has('payments', 'member_id=? OR verified_by=?', (member_id, member_id))
    financial = financial or has('stripe_orders', '('+scope+") AND (paid_at IS NOT NULL OR reversed_at IS NOT NULL OR state IN ('paid','test_paid','reversed'))", scope_args)
    financial = financial or has('creator_subscriptions', '('+scope+') OR verified_by=?', (*scope_args, member_id))
    financial = financial or has('live_entitlements', 'member_id=? AND paid_at IS NOT NULL', (member_id,))
    financial = financial or has('annual_access_emails', 'member_id=?', (member_id,))
    if 'stripe_accounts' in tables and 'stripe_reversals' in tables:
        financial = financial or has('stripe_reversals', 'account_id IN (SELECT account_id FROM stripe_accounts WHERE member_id=?)', (member_id,))
    if financial:
        raise AccountDeletionBlocked('La cuenta tiene pagos o referencias financieras. Se conserva para revisión; puedes darla de baja sin borrar su historial.')
    recording_scope = 'owner_id=?' + (' OR channel_id IN ('+channel_marks+')' if channel_ids else '')
    if has('live_recordings', recording_scope, scope_args):
        raise AccountDeletionBlocked('La cuenta tiene grabaciones conservadas para revisión. No se borrará su historial.')
    if has('community_messages', '('+scope+") AND (kind='report' OR blocked=1)", scope_args):
        raise AccountDeletionBlocked('La cuenta o su canal tienen denuncias o incidencias de moderación que deben conservarse.')
    if 'community_report_details' in tables:
        def mentions(value):
            if isinstance(value, dict):
                return any(mentions(child) for child in value.values())
            if isinstance(value, list):
                return any(mentions(child) for child in value)
            return isinstance(value, str) and value == member_id
        for report in conn.execute('SELECT snapshot_json FROM community_report_details WHERE snapshot_json LIKE ?', ('%'+member_id+'%',)).fetchall():
            try:
                relevant = mentions(json.loads(report['snapshot_json']))
            except (TypeError, ValueError):
                relevant = True
            if relevant:
                raise AccountDeletionBlocked('La cuenta aparece en una denuncia conservada. Debe mantenerse para revisión.')

    agreement_ids = [row['id'] for row in conn.execute(
        'SELECT id FROM subscription_agreements WHERE channel_id IN ('+channel_marks+')', channel_ids,
    ).fetchall()] if channel_ids and 'subscription_agreements' in tables else []
    agreement_marks = ','.join('?' for _ in agreement_ids)
    actor_links = [
        ('service_grants', 'granted_by', 'member_id'),
        ('community_roles', 'approved_by', 'member_id'),
        ('pricing_moderators', 'assigned_by', 'member_id'),
        ('moderator_permissions', 'granted_by', 'member_id'),
        ('ol_supervisors', 'assigned_by', 'member_id'),
        ('friend_access', 'granted_by', 'member_id'),
        ('member_archives', 'archived_by', 'member_id'),
        ('member_archive_events', 'actor_id', 'member_id'),
    ]
    for table, column, owner in actor_links:
        if has(table, column+'=? AND '+owner+'<>?', (member_id, member_id)):
            raise AccountDeletionBlocked('La cuenta figura como responsable de permisos o cambios de otras cuentas. No se modificarán esos registros.')
    if has('ol_operations', 'updated_by=?', (member_id,)):
        raise AccountDeletionBlocked('La cuenta figura como responsable de ajustes administrativos que deben conservarse.')
    for column in ('creator_id', 'moderator_id'):
        other_channel = ' AND channel_id NOT IN ('+channel_marks+')' if channel_ids else ''
        if has('subscription_agreements', column+'=?'+other_channel, (member_id, *channel_ids)):
            raise AccountDeletionBlocked('La cuenta participa en acuerdos de otros canales que deben conservarse.')
    other_agreement = ' AND agreement_id NOT IN ('+agreement_marks+')' if agreement_ids else ''
    if has('subscription_approvals', 'member_id=?'+other_agreement, (member_id, *agreement_ids)):
        raise AccountDeletionBlocked('La cuenta ha aprobado acuerdos de otros canales. Esas referencias se conservan.')

    rooms = [{'room_name': row['room_name'], 'owner': True, 'member_id': member_id}
             for row in channels if row['live_until'] is not None]
    if 'live_guest_invites' in tables and 'streamer_channels' in tables:
        rooms.extend({'room_name': row['room_name'], 'owner': False, 'member_id': member_id}
                     for row in conn.execute('SELECT DISTINCT c.room_name FROM live_guest_invites i JOIN streamer_channels c ON c.id=i.channel_id WHERE i.member_id=? AND c.live_until IS NOT NULL', (member_id,)).fetchall())

    def delete(table, condition, parameters):
        if table in tables:
            conn.execute('DELETE FROM '+table+' WHERE '+condition, parameters)

    conn.execute('SAVEPOINT delete_unpaid_account')
    try:
        if 'stripe_orders' in tables:
            for table in ('stripe_order_context', 'stripe_order_names', 'annual_access_emails'):
                delete(table, 'order_id IN (SELECT id FROM stripe_orders WHERE '+scope+')', scope_args)
            delete('stripe_orders', scope, scope_args)
        delete('annual_access_emails', 'member_id=?', (member_id,))
        if 'community_messages' in tables:
            for table in ('community_audiences', 'community_report_details', 'community_likes'):
                delete(table, 'message_id IN (SELECT id FROM community_messages WHERE '+scope+')', scope_args)
            delete('community_messages', scope, scope_args)
        delete('community_likes', 'member_id=?', (member_id,))
        if agreement_ids:
            delete('subscription_approvals', 'agreement_id IN ('+agreement_marks+')', agreement_ids)
        if channel_ids:
            for table in ('channel_subscription_settings', 'subscription_agreements',
                          'channel_subscription_prices', 'channel_subscription_drafts',
                          'live_stage_layouts', 'live_channel_thumbnails', 'live_broadcast_sessions',
                          'live_guest_invites', 'live_channel_settings', 'live_channel_views',
                          'adult_channel_rules'):
                delete(table, 'channel_id IN ('+channel_marks+')', channel_ids)
        for table in ('live_guest_invites', 'live_channel_views', 'adult_age_declarations',
                      'stripe_connect_states', 'stripe_accounts', 'email_tokens', 'invitations',
                      'member_two_factor', 'two_factor_recovery', 'member_legal_names',
                      'member_profiles', 'member_rewards', 'fan_aliases', 'annual_preferences',
                      'service_grants', 'community_roles', 'moderator_permissions',
                      'pricing_moderators', 'ol_supervisors', 'friend_access', 'streamer_access',
                      'live_entitlements', 'founder_activity', 'creator_daily_activity',
                      'founder_slot_history', 'founder_signatures', 'live_founders',
                      'visitor_sessions', 'online_presence', 'member_archive_events', 'member_archives'):
            delete(table, 'member_id=?', (member_id,))
        delete('streamer_channels', 'member_id=?', (member_id,))
        conn.execute('DELETE FROM members WHERE id=?', (member_id,))
    except INTEGRITY_ERRORS:
        conn.execute('ROLLBACK TO SAVEPOINT delete_unpaid_account')
        conn.execute('RELEASE SAVEPOINT delete_unpaid_account')
        raise AccountDeletionBlocked('La cuenta tiene otros registros vinculados que deben conservarse. No se ha borrado ningún dato.') from None
    conn.execute('RELEASE SAVEPOINT delete_unpaid_account')
    return rooms


def disconnect_rooms(rooms):
    if not rooms:
        return True
    from streamers import live_ready, sign_token
    if not live_ready():
        return False
    successful = True
    for room in rooms:
        instant = int(time.time())
        grants = {'roomCreate': True} if room['owner'] else {'roomAdmin': True, 'room': room['room_name']}
        token = sign_token({'iss': os.environ['LIVEKIT_API_KEY'].strip(), 'iat': instant,
                            'nbf': instant-5, 'exp': instant+45,
                            'video': grants})
        action = 'DeleteRoom' if room['owner'] else 'RemoveParticipant'
        data = {'room': room['room_name']}
        if not room['owner']:
            data['identity'] = 'maggy-'+room['member_id']+'-publisher'
        try:
            with requests.post('https://'+urlparse(os.environ['LIVEKIT_URL']).netloc+'/twirp/livekit.RoomService/'+action,
                               json=data, headers={'Authorization': 'Bearer '+token},
                               timeout=(2, 3), allow_redirects=False) as response:
                successful = response.status_code in {200, 404} and successful
        except requests.RequestException:
            successful = False
    if not successful:
        current_app.logger.warning('Account closed; an existing media connection could not be disconnected.')
    return successful


@bp.post('/api/admin/members/archive')
@require_admin
def archive_account():
    data = payload()
    if not isinstance(data.get('archived'), bool) or not isinstance(data.get('member_id'), str):
        return jsonify(error='Indica la cuenta y si deseas darla de baja o restaurarla.'), 400
    actor = get_user()
    rooms = []
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        fresh = conn.execute('SELECT role,session_version FROM members WHERE id=?', (actor['id'],)).fetchone()
        if not fresh or fresh['role'] != 'admin' or fresh['session_version'] != actor['session_version'] or is_archived(conn, actor['id']):
            return jsonify(error='La sesión de administración ha cambiado. Vuelve a entrar.'), 403
        target = conn.execute('SELECT id,username,role FROM members WHERE id=?', (data['member_id'],)).fetchone()
        if not target:
            return jsonify(error='La cuenta no existe.'), 404
        if target['role'] == 'admin' or target['id'] == actor['id']:
            return jsonify(error='Las cuentas administradoras se conservan para mantener el acceso al panel.'), 403
        if data['archived']:
            rooms = close_member(conn, target['id'], actor['id'])
        elif is_archived(conn, target['id']):
            instant = stamp(now_utc())
            conn.execute('UPDATE member_archives SET restored_at=? WHERE member_id=?', (instant, target['id']))
            conn.execute('UPDATE members SET session_version=session_version+1 WHERE id=?', (target['id'],))
            conn.execute('INSERT INTO member_archive_events VALUES(?,?,?,?,?)',
                         (secrets.token_hex(16), target['id'], actor['id'], 'restore', instant))
    return jsonify(ok=True, archived=data['archived'], username=target['username'],
                   live_disconnected=disconnect_rooms(rooms))


@bp.post('/api/admin/members/delete')
@require_admin
def delete_account():
    data = payload()
    if not isinstance(data.get('member_id'), str) or not data['member_id']:
        return jsonify(error='Selecciona la cuenta que deseas borrar.'), 400
    actor = get_user()
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        fresh = conn.execute('SELECT role,session_version FROM members WHERE id=?', (actor['id'],)).fetchone()
        if not fresh or fresh['role'] != 'admin' or fresh['session_version'] != actor['session_version'] or is_archived(conn, actor['id']):
            return jsonify(error='La sesión de administración ha cambiado. Vuelve a entrar.'), 403
        target = conn.execute('SELECT id,username,role FROM members WHERE id=?', (data['member_id'],)).fetchone()
        if not target:
            return jsonify(error='La cuenta no existe.'), 404
        if target['role'] == 'admin' or target['id'] == actor['id']:
            return jsonify(error='Las cuentas administradoras se conservan para mantener el acceso al panel.'), 403
        try:
            rooms = delete_unpaid_member(conn, target['id'], actor['id'])
        except AccountDeletionBlocked as error:
            return jsonify(error=str(error), code='account_deletion_blocked'), 409
    return jsonify(ok=True, deleted=True, username=target['username'],
                   live_disconnected=disconnect_rooms(rooms))


def apply_owner_cleanup_migration():
    """Owner requested permanent deletion of these three existing unpaid accounts."""
    if os.getenv('VERCEL_ENV') != 'production':
        return
    rooms = []
    with database() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM owner_access_migrations WHERE id=?', (OWNER_CLEANUP_ID,)).fetchone():
            return
        results = {}
        for name in ('amigo', 'prueba', 'prueba2'):
            target = conn.execute('SELECT id,role FROM members WHERE username=?', (name,)).fetchone()
            if not target:
                results[name] = 'not_present'
            elif target['role'] == 'admin':
                results[name] = 'protected_administrator'
            else:
                try:
                    rooms.extend(delete_unpaid_member(conn, target['id']))
                    results[name] = 'deleted'
                except AccountDeletionBlocked:
                    results[name] = 'blocked_financial_or_history'
        if 'deleted' in results.values() and 'interface_revisions' in _tables(conn):
            for topic in ('account', 'public'):
                conn.execute('INSERT INTO interface_revisions(topic,version) VALUES(?,?) ON CONFLICT(topic) DO UPDATE SET version=excluded.version',
                             (topic, secrets.token_hex(16)))
        conn.execute('INSERT INTO owner_access_migrations VALUES(?,?,?)',
                     (OWNER_CLEANUP_ID, stamp(now_utc()), json.dumps(results, sort_keys=True)))
    disconnect_rooms(rooms)


def install(app):
    app.register_blueprint(bp)
    with app.app_context():
        apply_owner_cleanup_migration()
