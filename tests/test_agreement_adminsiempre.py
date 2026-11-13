"""An existing admin can moderate agreements without becoming two approvers."""
from contextlib import contextmanager
from datetime import datetime, timedelta
import json
import secrets
import unittest
from unittest.mock import patch

import app as application
import membership as m
import streamers
import subscriptions as subs
from auth_support import authenticated_client


class AgreementAdminSiempreTests(unittest.TestCase):
    def setUp(self):
        settings=patch.dict('os.environ', {
            'VERCEL':'0','VERCEL_ENV':'development','OL_LOGIN_EMAIL_REQUIRED':'0',
            'OL_LOGIN_AUDIT_EMAILS':'0','OL_ACCOUNT_REPORT_EMAILS':'0',
            'OL_REGISTRATION_FEE_ENABLED':'0','MAGGY_STREAMERS_ENABLED':'0',
        })
        settings.start();self.addCleanup(settings.stop)
        notice=patch('notifications.notify',return_value=False)
        notice.start();self.addCleanup(notice.stop)
        self.app=application.app
        self.admin=authenticated_client(self.app,self.addCleanup)
        self.admin_id=self.admin.get('/api/account/me').json['user']['id']
        self.cutoff=datetime.fromisoformat(subs.OWNER_MODERATOR_CUTOFF)
        self.old=m.stamp(self.cutoff-timedelta(days=2))
        with self.app.app_context():streamers.init_database()
        self.creator_id,self.creator=self.member('agreement-creator',creator=True)
        self.gref_id,self.gref=self.member('gref')
        self.designate(self.gref_id)
        self.channel=self.channel_for(self.creator)

    def member(self,name,role='member',creator=False,activated=True,created_at=None):
        ident=secrets.token_hex(16)
        future=m.stamp(m.now_utc()+timedelta(days=365))
        with self.app.app_context(),m.database() as conn:
            conn.execute('''INSERT INTO members(id,username,password_hash,role,created_at,access_until)
                VALUES(?,?,?,?,?,?)''',(ident,name,'fixture-not-a-login-hash' if activated else None,
                role,created_at or self.old,future))
            if creator:conn.execute('INSERT INTO streamer_access VALUES(?,?)',(ident,future))
        client=self.app.test_client()
        if activated:
            with client.session_transaction() as session:session.update(member_id=ident,session_version=0)
        return ident,client

    def post(self,client,path,data):
        csrf=client.get('/api/account/me').json['csrf']
        return client.post(path,json=data,headers={'X-CSRF-Token':csrf})

    def designate(self,ident):
        response=self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':ident})
        self.assertEqual(response.status_code,200,response.json)
        response=self.post(self.admin,'/api/admin/moderator-permissions',
                           {'permissions':['review_agreements','approve_agreements']})
        self.assertEqual(response.status_code,200,response.json)

    def channel_for(self,client):
        response=self.post(client,'/api/streamers/me',{'title':'Canal de pruebas',
            'paypal_url':'https://paypal.me/AgreementFixture','owns_paypal':True})
        self.assertEqual(response.status_code,200,response.json)
        return response.json['channel']['id']

    def proposal(self,client=None):
        response=self.post(client or self.creator,'/api/channel-subscriptions/propose',
            {'price_cents':350,'period':'month','benefits':['badge']})
        self.assertEqual(response.status_code,200,response.json)
        return response

    def approve(self,client,ident,party):
        return self.post(client,'/api/channel-subscriptions/approve',
                         {'agreement_id':ident,'party':party})

    def migrate(self,vercel='1',environment='production'):
        with self.app.app_context(),patch.dict('os.environ',{'VERCEL':vercel,'VERCEL_ENV':environment}):
            return subs.apply_owner_moderator_migration()

    def rows(self,table,condition='1=1',parameters=()):
        with self.app.app_context(),m.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM '+table+' WHERE '+condition,parameters).fetchall()]

    def test_existing_admin_moderates_with_three_independent_approvers(self):
        ident,client=self.member('adminsiempre',role='admin')
        self.assertEqual(self.migrate()['member_id'],ident)
        agreement=self.proposal().json['agreement_id']
        queue=client.get('/api/channel-subscriptions/review').json
        self.assertEqual(queue['agreements'][0]['approval_party'],'moderator')
        self.assertEqual(queue['agreements'][0]['moderator_username'],'adminsiempre')
        self.assertEqual(self.approve(client,agreement,'admin').status_code,403)
        self.assertEqual(self.approve(self.creator,agreement,'moderator').status_code,403)
        self.assertEqual(self.approve(self.creator,agreement,'creator').status_code,200)
        own=self.approve(client,agreement,'moderator')
        self.assertEqual(own.status_code,200);self.assertFalse(own.json['agreement_activated'])
        other=self.approve(self.admin,agreement,'admin')
        self.assertEqual(other.status_code,200);self.assertTrue(other.json['agreement_activated'])
        approvals=self.rows('subscription_approvals','agreement_id=?',(agreement,))
        self.assertEqual(len({row['member_id'] for row in approvals}),3)
        self.assertEqual(self.rows('members','id=?',(ident,))[0]['role'],'admin')

    def test_old_gref_agreements_and_permissions_are_not_rewritten(self):
        agreement=self.proposal().json['agreement_id']
        for client,party in [(self.creator,'creator'),(self.admin,'admin'),(self.gref,'moderator')]:
            self.assertEqual(self.approve(client,agreement,party).status_code,200)
        before=self.rows('subscription_agreements')
        consents=self.rows('subscription_approvals')
        old_grant=self.rows('pricing_moderators','member_id=?',(self.gref_id,))
        old_permissions=self.rows('moderator_permissions','member_id=?',(self.gref_id,))
        self.member('adminsiempre',role='admin');self.migrate()
        self.assertEqual(self.rows('subscription_agreements'),before)
        self.assertEqual(self.rows('subscription_approvals'),consents)
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(self.gref_id,)),old_grant)
        self.assertEqual(self.rows('moderator_permissions','member_id=?',(self.gref_id,)),old_permissions)
        queue=self.admin.get('/api/channel-subscriptions/review').json
        self.assertEqual(queue['agreements'][0]['moderator_username'],'gref')
        with self.app.app_context(),m.database() as conn:
            row=conn.execute('SELECT * FROM subscription_agreements WHERE id=?',(agreement,)).fetchone()
            self.assertTrue(subs.approvals_valid(conn,row))

    def test_creator_adminsiempre_uses_another_existing_moderator(self):
        ident,client=self.member('adminsiempre',role='admin')
        self.migrate();self.channel_for(client)
        agreement=self.proposal(client).json['agreement_id']
        row=self.rows('subscription_agreements','id=?',(agreement,))[0]
        self.assertEqual(row['creator_id'],ident);self.assertEqual(row['moderator_id'],self.gref_id)
        card=next(card for card in client.get('/api/channel-subscriptions/review').json['agreements'] if card['id']==agreement)
        self.assertIsNone(card['approval_party'])
        self.assertEqual(self.approve(client,agreement,'moderator').status_code,403)

    def test_creator_without_an_independent_moderator_gets_a_draft(self):
        ident,client=self.member('adminsiempre',role='admin')
        self.migrate();self.channel_for(client)
        with self.app.app_context(),m.database() as conn:
            conn.execute('UPDATE pricing_moderators SET revoked_at=? WHERE member_id=?',(m.stamp(m.now_utc()),self.gref_id))
        response=self.proposal(client)
        self.assertTrue(response.json['draft'])
        self.assertNotIn('agreement_id',response.json)
        self.assertIn('distinta del creador',' '.join(response.json['pending']))

    def test_actor_permissions_are_separate_from_the_primary_permission_form(self):
        ident,client=self.member('adminsiempre',role='admin');self.migrate()
        agreement=self.proposal().json['agreement_id']
        self.designate(self.gref_id)
        self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':['review_agreements']})
        status=client.get('/api/channel-subscriptions/reviewer').json
        self.assertEqual(status['assigned']['username'],'gref')
        self.assertEqual(status['permissions'],['review_agreements'])
        self.assertEqual(set(status['actor_permissions']),{'review_agreements','approve_agreements'})
        self.assertEqual(self.approve(client,agreement,'moderator').status_code,200)

    def test_granular_revocation_applies_to_the_next_admin_moderator_action(self):
        ident,client=self.member('adminsiempre',role='admin');self.migrate()
        agreement=self.proposal().json['agreement_id']
        self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':['review_agreements']})
        self.assertEqual(self.approve(client,agreement,'moderator').status_code,403)
        self.assertEqual(client.get('/api/channel-subscriptions/review').json['agreements'][0]['approval_party'],'moderator')
        self.post(self.admin,'/api/admin/moderator-permissions',{'permissions':[]})
        self.assertIsNone(client.get('/api/channel-subscriptions/review').json['agreements'][0]['approval_party'])
        self.migrate()
        self.assertEqual(self.rows('moderator_permissions','member_id=?',(ident,)),[])

    def test_id_designation_and_owner_button_identity_survive_a_username_change(self):
        ident,client=self.member('adminsiempre',role='admin');self.migrate()
        with self.app.app_context(),m.database() as conn:
            conn.execute("UPDATE members SET username='changed-admin-name' WHERE id=?",(ident,))
        replacement,_=self.member('adminsiempre')
        reviewer=self.admin.get('/api/channel-subscriptions/reviewer').json
        self.assertEqual(reviewer['adminsiempre_member_id'],ident)
        response=self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':reviewer['adminsiempre_member_id']})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json['username'],'changed-admin-name')
        agreement=self.proposal().json['agreement_id']
        self.assertEqual(self.rows('subscription_agreements','id=?',(agreement,))[0]['moderator_id'],ident)
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(replacement,)),[])

    def test_designation_accepts_pending_accounts_without_granting_permissions(self):
        ident,_=self.member('pending-reviewer',activated=False)
        response=self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':ident})
        self.assertEqual(response.status_code,200);self.assertFalse(response.json['activated'])
        self.assertEqual(self.rows('moderator_permissions','member_id=?',(ident,)),[])
        self.assertEqual(self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':'not-an-id'}).status_code,400)

    def test_designation_and_selection_exclude_archived_and_blocked_accounts(self):
        ident,client=self.member('adminsiempre',role='admin');self.migrate()
        with self.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO account_blocks VALUES(?,?,?,?)',(ident,m.stamp(m.now_utc()),'fixture','test'))
        self.assertEqual(self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':ident}).status_code,409)
        self.assertIsNone(self.admin.get('/api/channel-subscriptions/reviewer').json['adminsiempre_member_id'])
        self.assertEqual(self.proposal().json.get('draft',False),False)
        agreement=self.rows('subscription_agreements')[0]
        self.assertEqual(agreement['moderator_id'],self.gref_id)
        self.assertEqual(client.get('/api/channel-subscriptions/review').status_code,403)

    def test_owner_identity_uses_a_previous_grant_and_never_changes_the_role(self):
        ident,_=self.member('renamed-owner-account')
        with self.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO video_upload_grants VALUES(?,?,?,NULL)',
                         (ident,self.old,'owner-adminsiempre-video-upload-2026-11-12'))
        result=self.migrate()
        self.assertEqual(result['member_id'],ident);self.assertEqual(result['status'],'granted')
        self.assertEqual(self.rows('members','id=?',(ident,))[0]['role'],'member')

    def test_missing_identity_is_durable_and_does_not_follow_a_later_name(self):
        result=self.migrate();self.assertEqual(result['status'],'skipped_missing_existing_account')
        ident,_=self.member('adminsiempre')
        self.assertEqual(self.migrate(),result)
        self.assertIsNone(self.admin.get('/api/channel-subscriptions/reviewer').json['adminsiempre_member_id'])
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(ident,)),[])

    def test_preview_migration_does_not_assign_the_account(self):
        ident,_=self.member('adminsiempre')
        self.assertIsNone(self.migrate(environment='preview'))
        self.assertIsNone(self.migrate(vercel='0'))
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(ident,)),[])
        self.assertEqual(self.rows('owner_access_migrations','id=?',(subs.OWNER_MODERATOR_MIGRATION_ID,)),[])

    def test_invalid_prior_identity_and_late_account_are_not_granted(self):
        ident,_=self.member('adminsiempre',created_at=m.stamp(self.cutoff+timedelta(seconds=1)))
        self.assertEqual(self.migrate()['status'],'skipped_new_or_unknown_account')
        with self.app.app_context(),m.database() as conn:
            conn.execute('DELETE FROM owner_access_migrations WHERE id=?',(subs.OWNER_MODERATOR_MIGRATION_ID,))
            conn.execute('INSERT INTO owner_access_migrations VALUES(?,?,?)',
                ('owner-admin-adminsiempre-2026-11-12',self.old,json.dumps({'status':'granted','member_id':'invalid'})))
        self.assertEqual(self.migrate()['status'],'skipped_invalid_prior_identity')
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(ident,)),[])

    def test_privilege_changes_while_waiting_for_the_write_lock_are_rechecked(self):
        ident,_=self.member('new-reviewer')
        original_database=subs.database
        @contextmanager
        def changed_administrator():
            with original_database() as conn:
                conn.execute("UPDATE members SET role='member' WHERE id=?",(self.admin_id,))
                conn.commit()
                yield conn
        with patch.object(subs,'database',changed_administrator):
            response=self.post(self.admin,'/api/admin/subscription-moderator',{'member_id':ident})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.rows('pricing_moderators','member_id=?',(ident,)),[])


if __name__=='__main__':unittest.main()
