"""Clear old owner notices except Flores; ordinary future mail remains available."""
import json
import os
import secrets
import unittest
from unittest.mock import patch

import app
import membership as m
import notifications as n
from auth_support import authenticated_client


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.admin=authenticated_client(app.app,self.addCleanup)
        self.env=patch.dict(os.environ,{'OL_EMAIL_FROM':'','RESEND_API_KEY':'','SMTP_HOST':'','SMTP_USER':'','SMTP_PASSWORD':'','VERCEL_ENV':''})
        self.env.start();self.addCleanup(self.env.stop)
        with app.app.app_context():n.init_database()

    def member(self,username,nickname=''):
        ident=secrets.token_hex(16)
        with app.app.app_context(),m.database() as conn:
            instant=m.stamp(m.now_utc())
            conn.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,username,instant))
            if nickname:conn.execute('INSERT INTO member_profiles(member_id,nickname,updated_at) VALUES(?,?,?)',(ident,nickname,instant))
        return ident

    def notice(self,member_ids=(),event_key=None,status=None,title='Aviso'):
        with app.app.app_context():
            n.notify('test',title,'Resumen sin secretos',event_key=event_key,member_ids=member_ids)
            with m.database() as conn:
                row=conn.execute('SELECT id FROM admin_notifications ORDER BY created_at DESC,id DESC LIMIT 1').fetchone() if not event_key else conn.execute('SELECT id FROM admin_notifications WHERE event_key=?',(event_key,)).fetchone()
                if status:conn.execute('UPDATE admin_notifications SET status=? WHERE id=?',(status,row['id']))
                return row['id']

    def old_notice(self,event_key=None,status='pending',detail='Sin datos sensibles'):
        ident=secrets.token_hex(16)
        with app.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO admin_notifications(id,kind,title,detail,event_key,created_at,status) VALUES(?,?,?,?,?,?,?)',
                         (ident,'test','Aviso histórico',detail,event_key,m.stamp(m.now_utc()),status))
        return ident

    def listing(self):
        response=self.admin.get('/api/admin/notifications')
        self.assertEqual(response.status_code,200)
        return response.json

    def clear(self):return self.admin.post('/api/admin/notifications/clear',json={})

    def configured(self):
        return patch.dict(os.environ,{'OL_EMAIL_FROM':'Ol <test@example.org>','RESEND_API_KEY':'test-key'})

    def test_unconfigured_email_is_queued_without_claiming_delivery(self):
        with app.app.app_context():n.notify('test','Aviso de prueba','Resumen sin secretos',event_key='notice-test')
        result=self.listing()
        self.assertFalse(result['email_ready']);self.assertEqual(result['pending'],1)
        self.assertEqual(result['recipient'],'normalesoutro@gmail.com')
        self.assertEqual(result['notifications'][0]['status'],'pending')
        self.assertEqual(result['history_keep'],{'username':'rosas','label':'Flores'})
        self.assertEqual(app.app.test_client().get('/api/admin/notifications').status_code,403)

    def test_deduplication_and_delivery_failure_preserve_pending_notice(self):
        with self.configured(),patch.object(n,'deliver',side_effect=RuntimeError('private provider detail')) as delivered:
            with app.app.app_context():
                n.notify('test','Aviso','Resumen',event_key='notice-dedupe')
                n.notify('test','Aviso','Resumen',event_key='notice-dedupe')
        self.assertEqual(delivered.call_count,1)
        result=self.listing()
        self.assertEqual(result['total'],1);self.assertEqual(result['notifications'][0]['status'],'failed')
        self.assertNotIn('private provider detail',str(result))

    def test_clear_physically_deletes_other_history_in_every_mail_state(self):
        flores=self.member('rosas','Flores');other=self.member('ordinary-account','Otra persona')
        kept=self.notice([flores],event_key='kept-flores',status='sent')
        for index,state in enumerate(['sent','pending','failed','sending']):
            self.notice([other],event_key='removed-'+str(index),status=state)
        self.old_notice('unknown:old')
        response=self.clear()
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json,{'ok':True,'deleted':5,'retained':1,'kept_username':'rosas','kept_label':'Flores'})
        result=self.listing();self.assertEqual(result['total'],1);self.assertEqual(result['notifications'][0]['id'],kept)
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM admin_notification_members').fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM members').fetchone()['n'],3)
        self.assertEqual(self.clear().json['deleted'],0)

    def test_nickname_and_free_text_cannot_preserve_an_unrelated_notice(self):
        flores=self.member('rosas','Flores');other=self.member('impostor','Flores')
        self.notice([flores],event_key='real-flores')
        self.notice([other],event_key='other-with-name',title='Flores')
        self.old_notice('unknown:Flores',detail=json.dumps({'nickname':'Flores','body':'rosas'}))
        response=self.clear()
        self.assertEqual((response.json['deleted'],response.json['retained']),(2,1))
        self.assertEqual(self.listing()['total'],1)

    def test_missing_flores_never_causes_a_global_delete(self):
        original=self.old_notice('unknown:old')
        response=self.clear()
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.listing()['notifications'][0]['id'],original)

    def test_clear_requires_admin_and_csrf(self):
        self.member('rosas','Flores')
        guest=app.app.test_client();token=guest.get('/api/account/me').json['csrf']
        self.assertEqual(guest.post('/api/admin/notifications/clear',json={},headers={'X-CSRF-Token':token}).status_code,403)
        raw_admin=app.app.test_client();token=raw_admin.get('/api/account/me').json['csrf']
        raw_admin.post('/api/account/login',json={'username':'test-admin','password':'test-password-only-123'},headers={'X-CSRF-Token':token})
        response=raw_admin.post('/api/admin/notifications/clear',json={})
        self.assertEqual(response.status_code,403);self.assertEqual(response.json['code'],'csrf_expired')

    def test_trusted_legacy_registration_invite_and_founder_keys_are_retained(self):
        flores=self.member('rosas','Flores');other=self.member('another-account')
        kept={self.old_notice(prefix+':'+flores) for prefix in ['registration','invite','founder']}
        self.old_notice('registration:'+other)
        response=self.clear()
        self.assertEqual((response.json['deleted'],response.json['retained']),(1,3))
        self.assertEqual({row['id'] for row in self.listing()['notifications']},kept)

    def test_trusted_old_stripe_and_report_relations_keep_flores(self):
        import streamers,payments
        flores=self.member('rosas','Flores');other=self.member('ordinary-buyer')
        channel=secrets.token_hex(16);order=secrets.token_hex(16);report=secrets.token_hex(16)
        with app.app.app_context():
            streamers.init_database();payments.init_database()
            with m.database() as conn:
                instant=m.stamp(m.now_utc())
                conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,updated_at) VALUES(?,?,?,?,?)',(channel,flores,'Canal','room-fixture',instant))
                conn.execute('INSERT INTO stripe_orders(id,member_id,kind,channel_id,account_id,amount_cents,currency,created_at,state) VALUES(?,?,?,?,?,?,?,?,?)',(order,other,'creator',channel,'acct_fixture',350,'eur',instant,'paid'))
                conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,blocked,created_at) VALUES(?,?,?,?,?,0,?)',(report,channel,other,'report','Motivo',instant))
                conn.execute('INSERT INTO community_report_details VALUES(?,?)',(report,json.dumps({'reporter':{'id':other},'reported':{'id':flores}})))
        kept={self.old_notice('stripe-order:'+order),self.old_notice('community-report:'+report)}
        self.old_notice('unknown:removed')
        response=self.clear()
        self.assertEqual((response.json['deleted'],response.json['retained']),(1,2))
        self.assertEqual({row['id'] for row in self.listing()['notifications']},kept)

    def test_one_time_production_cleanup_leaves_future_notices_and_delivery_normal(self):
        flores=self.member('rosas','Flores');other=self.member('ordinary-account')
        self.notice([flores],event_key='flores-historical')
        self.notice([other],event_key='old-other')
        with app.app.app_context(),patch.dict(os.environ,{'VERCEL_ENV':'production'}):
            n.apply_owner_history_cleanup()
        with self.configured(),patch.object(n,'deliver') as delivered:
            with app.app.app_context():self.assertTrue(n.notify('test','Nuevo aviso normal','Resumen',event_key='future-other',member_ids=[other]))
        delivered.assert_called_once()
        with app.app.app_context(),patch.dict(os.environ,{'VERCEL_ENV':'production'}):
            n.apply_owner_history_cleanup()
        result=self.listing();self.assertEqual(result['total'],2)
        self.assertEqual({row['status'] for row in result['notifications']},{'sent','pending'})
        self.assertNotIn('mail_filter',result)

    def test_non_production_or_missing_target_migration_is_safe_and_once(self):
        original=self.old_notice('unknown:old')
        with app.app.app_context():n.apply_owner_history_cleanup()
        self.assertEqual(self.listing()['total'],1)
        with app.app.app_context(),patch.dict(os.environ,{'VERCEL_ENV':'production'}):n.apply_owner_history_cleanup()
        self.member('rosas','Flores')
        with app.app.app_context(),patch.dict(os.environ,{'VERCEL_ENV':'production'}):n.apply_owner_history_cleanup()
        self.assertEqual(self.listing()['notifications'][0]['id'],original)
        with app.app.app_context(),m.database() as conn:
            result=conn.execute('SELECT result FROM owner_access_migrations WHERE id=?',('owner-clear-notifications-except-rosas-2026-10-30',)).fetchone()
        self.assertEqual(result['result'],'skipped_missing_flores')
