"""Copy an existing local Maggy database into an EMPTY PostgreSQL installation."""
import argparse
import getpass
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import quote

ROOT=Path(__file__).resolve().parents[1]
TABLES={
    'members':['id','username','password_hash','role','created_at','access_until','welcome_used','session_version'],
    'member_archives':['member_id','archived_at','archived_by','reason','restored_at'],
    'account_blocks':['member_id','blocked_at','reason','source'],
    'video_upload_grants':['member_id','granted_at','source','revoked_at'],
    'account_block_livekit_jobs':['member_id','blocked_at','retry_until','next_attempt_at','lease_until','lease_token','last_attempt_at','last_success_at','attempts','last_error','rooms_json','completed_at','room_cursor','sweep_started_at'],
    'member_archive_events':['id','member_id','actor_id','action','created_at'],
    'member_name_history':['id','member_id','actor_id','former_username','new_username','changed_at'],
    'member_identity_links':['identity','member_id'],
    'sticker_voice_audio':['cache_key','audio_base64','created_at'],
    'member_legal_names':['member_id','legal_name','updated_at'],
    'stripe_order_names':['order_id','legal_name'],
    'member_profiles':['member_id','email','nickname','email_verified','updated_at'],
    'email_tokens':['token_hash','member_id','purpose','email','session_version','created_at','expires_at'],
    'member_two_factor':['member_id','nonce','enabled_at','key_id','last_counter','pending_nonce','pending_until'],
    'two_factor_recovery':['member_id','code_hash','used_at'],
    'fan_aliases':['member_id','alias'],
    'ol_operations':['id','scope','message','updated_by','updated_at'],
    'ol_supervisors':['member_id','assigned_by','assigned_at','can_review','revoked_at'],
    'stripe_accounts':['member_id','account_id','linked_at'],
    'stripe_connect_states':['token_hash','member_id','expires_at'],
    'moderator_permissions':['member_id','permission','granted_by','granted_at'],
    'pricing_moderators':['member_id','assigned_by','assigned_at','revoked_at'],
    'live_launch':['id','started_at'],
    'live_entitlements':['member_id','trial_started_at','trial_until','paid_at','revoked_at'],
    'founder_activity':['member_id','total_seconds','session_seconds','last_verified_at','qualification_until','first_completed_at'],
    'creator_daily_activity':['member_id','day','seconds'],
    'promotion_metrics':['day','event','amount'],
    'live_founders':['member_id','number','claimed_at','revoked_at'],
    'founder_ownership':['member_id','number','assigned_at','revoked_at'],
    'founder_slot_history':['id','member_id','number','claimed_at','trial_until','released_at','reason','signature_json'],
    'founder_signatures':['member_id','mode','letter','caption','audio_json','updated_at'],
    'sticker_designs':['id','name','points','image_data','updated_at'],
    'member_rewards':['member_id','active_seconds','last_seen'],
    'friend_access':['member_id','granted_at','granted_by','revoked_at'],
    'streamer_access':['member_id','until_at'],
    'streamer_channels':['id','member_id','title','bio','paypal_url','room_name','live_until','updated_at'],
    'live_channel_settings':['channel_id','category','featured'],
    'subscription_agreements':['id','channel_id','version','creator_id','moderator_id','price_cents','period','benefits_json','paypal_url','created_at'],
    'subscription_approvals':['agreement_id','party','member_id','approved_at'],
    'channel_subscription_settings':['channel_id','agreement_id','subscriber_chat','exclusive_live'],
    'stripe_orders':['id','member_id','kind','channel_id','agreement_id','account_id','amount_cents','currency','created_at','checkout_id','payment_intent','paid_at','reversed_at','state'],
    'stripe_reversals':['payment_intent','account_id','reversed_at'],
    'stripe_events':['id','event_type','received_at'],
    'creator_subscriptions':['id','channel_id','member_id','agreement_id','amount_cents','benefits_json','starts_at','ends_at','verified_at','verified_by','reference','revoked_at'],
    'registration_access':['member_id','origin','exempt_reason','grace_started_at','due_at','paid_at'],
    'registration_fee_orders':['id','member_id','amount_cents','currency','created_at','checkout_id','payment_intent','paid_at','state','refunded_cents'],
    'account_report_queue':['event_key','title','body','created_at','status','attempts','last_attempt','sent_at','lease_token'],
    'account_report_members':['member_id','event','event_key'],
    'account_report_batches':['id','created_at','total_accounts','batches'],
    'contribution_payments':['id','member_id','amount_cents','currency','created_at','checkout_id','payment_intent','paid_at','state','refunded_cents'],
    'security_login_challenges':['id','member_id','email','session_version','binding_hash','code_hash','created_at','expires_at','last_sent_at','attempts','sends','delivery_state','delivery_token','used_at','profile_email_present'],
    'security_login_events':['id','member_id','identifier','event','result','created_at','network_id','browser','mail_status','mail_attempted_at','mail_sent_at','mail_batch_id'],
    'community_videos':['id','owner_id','title','description','category','filename','mime_type','size_bytes','object_key','upload_id','part_size','part_count','state','technical_checked','verified_etag','storage_completed_at','operation_token','operation_expires_at','review_reason','created_at','updated_at','published_at','revision','storage_deleted_at'],
    'community_video_reviews':['id','video_id','actor_id','previous_state','new_state','reason','created_at'],
    'community_video_reports':['id','video_id','reporter_id','reason','created_at'],
    'live_recordings':['id','channel_id','owner_id','room_name','egress_id','object_key','state','started_at','ended_at','expires_at','updated_at'],
    'adult_channel_rules':['channel_id','adult_content','version','locked'],
    'adult_age_declarations':['member_id','context','minimum_age','expires_at'],
    'interface_revisions':['topic','version'],
    'live_channel_views':['channel_id','member_id','day'],
    'community_retention_clock':['id','last_run'],
    'live_channel_thumbnails':['channel_id','session_start','image_base64','updated_at'],
    'live_broadcast_sessions':['channel_id','started_at'],
    'live_guest_invites':['channel_id','member_id','session_start'],
    'visitor_public_totals':['id','since','sessions'],
    'visitor_public_history':['id','since','initialized_at','unassigned'],
    'visitor_public_days':['day','sessions'],
    'visitor_devices':['id','first_seen','last_seen'],
    'visitor_sessions':['id','device_id','member_id','account_kind','started_at','last_seen','pageviews','last_page','network_id','network_day','device','os','browser'],
    'community_messages':['id','channel_id','member_id','kind','body','category','blocked','created_at'],
    'community_likes':['message_id','member_id'],
    'community_report_details':['message_id','snapshot_json'],
    'community_audiences':['message_id','audience'],
    'payments':['id','member_id','plan','amount_cents','starts_at','ends_at','verified_at','verified_by','reference'],
    'invitations':['token_hash','member_id','expires_at','used_at'],
    'admin_notifications':['id','kind','title','detail','event_key','created_at','status','attempts','last_attempt','sent_at'],
    'admin_notification_members':['notification_id','member_id'],
    'login_attempts':['bucket','attempted_at'],
}


def migrate(source,app):
    from membership import database
    path=Path(source).resolve()
    if not path.is_file():raise ValueError('No existe la base SQLite de origen.')
    if not app.config.get('MEMBERSHIP_DATABASE_URL'):raise ValueError('El destino debe ser PostgreSQL mediante DATABASE_URL.')
    original=sqlite3.connect('file:'+quote(str(path),safe='/\\:')+'?mode=ro',uri=True)
    original.row_factory=sqlite3.Row
    try:
        original.execute('BEGIN')
        rows={}
        for table,columns in TABLES.items():
            actual=[row['name'] for row in original.execute('PRAGMA table_info('+table+')')]
            if not actual and table in {'video_upload_grants','account_blocks','account_block_livekit_jobs','registration_access','registration_fee_orders','account_report_queue','account_report_members','account_report_batches','contribution_payments','security_login_challenges','security_login_events','community_videos','community_video_reviews','community_video_reports','admin_notification_members','member_archives','member_archive_events','member_name_history','member_identity_links','founder_ownership','visitor_public_totals','visitor_public_history','visitor_public_days','visitor_devices','visitor_sessions','live_channel_thumbnails','live_broadcast_sessions','live_guest_invites','community_likes','community_report_details','live_recordings','adult_channel_rules','adult_age_declarations','interface_revisions','live_channel_views','community_retention_clock','sticker_voice_audio','member_legal_names','stripe_order_names','member_profiles','email_tokens','fan_aliases','stripe_orders','stripe_accounts','stripe_connect_states','stripe_events','stripe_reversals','ol_operations','ol_supervisors','moderator_permissions','member_two_factor','two_factor_recovery','pricing_moderators','subscription_agreements','subscription_approvals','channel_subscription_settings','creator_subscriptions','community_audiences','founder_slot_history','live_launch','live_entitlements','founder_activity','creator_daily_activity','promotion_metrics','founder_signatures','live_founders','sticker_designs','member_rewards','friend_access','streamer_access','streamer_channels','community_messages','admin_notifications','live_channel_settings'}:
                rows[table]=[];continue
            if set(actual)!=set(columns):raise ValueError('La estructura SQLite no es compatible: '+table)
            rows[table]=[dict(row) for row in original.execute('SELECT '+','.join(columns)+' FROM '+table)]
        with app.app_context():
            from two_factor import key_id
            if any(row['enabled_at'] and row['key_id']!=key_id() for row in rows['member_two_factor']):raise ValueError('Para conservar 2FA debes configurar en el destino el mismo MAGGY_SESSION_SECRET del origen antes de migrar.')
            from streamers import init_database as init_streamer_database
            init_streamer_database()
        with app.app_context(),database() as connection:
            connection.execute('BEGIN IMMEDIATE')
            for table in TABLES:
                if connection.execute('SELECT COUNT(*) AS count FROM '+table).fetchone()['count']:
                    raise ValueError('El destino ya contiene datos. La migración no sobrescribe ni mezcla cuentas.')
            for table,columns in TABLES.items():
                query='INSERT INTO '+table+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')'
                for row in rows[table]:connection.execute(query,tuple(row[column] for column in columns))
        return {table:len(records) for table,records in rows.items()}
    finally:
        original.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True,help='Ruta local a .instance/members.sqlite3')
    args=parser.parse_args()
    if not os.environ.get('DATABASE_URL'):
        os.environ['DATABASE_URL']=getpass.getpass('Conexión PostgreSQL de destino (no se muestra): ')
    sys.path.insert(0,str(ROOT))
    try:
        from app import app
        result=migrate(args.source,app)
    except ValueError as error:
        raise SystemExit(str(error))
    except Exception as error:
        raise SystemExit('La migración no se completó ('+type(error).__name__+'). Revisa conexión y esquema; no se modificó la base de origen.')
    print('Migración completada:',', '.join(f'{name}: {count}' for name,count in result.items()))


if __name__=='__main__':main()
