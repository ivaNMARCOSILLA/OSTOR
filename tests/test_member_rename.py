"""Administrative name changes keep the same account, credentials and badge."""
from concurrent.futures import ThreadPoolExecutor
import secrets
import unittest
from unittest.mock import patch

import app
import membership as m
import streamers
from auth_support import authenticated_client
from registration_support import registration_data


class MemberRenameTests(unittest.TestCase):
    PASSWORD='rename-account-password-123'

    def setUp(self):
        self.admin=authenticated_client(app.app,self.addCleanup)
        with app.app.app_context():streamers.init_database()
        self.admin_id=self.admin.get('/api/account/me').json['user']['id']
        notices=patch.object(m,'notify');self.notices=notices.start();self.addCleanup(notices.stop)
        mail=patch('email_security.send_security_mail',return_value=False);mail.start();self.addCleanup(mail.stop)

    def post(self,client,path,body):
        if path=='/api/account/register':body=registration_data(client,body)
        token=client.get('/api/account/me').json['csrf']
        return client.post(path,json=body,headers={'X-CSRF-Token':token})

    def member(self,name,**profile):
        client=app.app.test_client()
        result=self.post(client,'/api/account/register',dict(username=name,password=self.PASSWORD,**profile))
        self.assertEqual(result.status_code,201,result.json)
        return client,client.get('/api/account/me').json['user']['id']

    def rename(self,ident,name,client=None):
        return self.post(client or self.admin,'/api/admin/members/rename',{'member_id':ident,'username':name})

    def row(self,ident):
        with app.app.app_context(),m.database() as conn:
            row=conn.execute('SELECT * FROM members WHERE id=?',(ident,)).fetchone()
            return dict(row) if row else None

    def history(self,ident):
        with app.app.app_context(),m.database() as conn:
            return [dict(row) for row in conn.execute('SELECT * FROM member_name_history WHERE member_id=?',(ident,)).fetchall()]

    def test_rename_keeps_identity_profile_payments_badge_and_existing_session(self):
        owner,ident=self.member('rename-holder',email='rename@example.test',nickname='Nombre visible')
        instant=m.now_utc();now=m.stamp(instant);until=m.stamp(m.end_of_plan(instant,'annual'))
        channel=secrets.token_hex(16)
        with app.app.app_context(),m.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('UPDATE members SET access_until=? WHERE id=?',(until,ident))
            conn.execute('UPDATE member_profiles SET email_verified=1 WHERE member_id=?',(ident,))
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)',(ident,now))
            from founder_slots import reserve
            number=reserve(conn,ident)
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',('rename-receipt',ident,'annual',2500,now,until,now,self.admin_id,'rename-paid-001'))
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,updated_at) VALUES(?,?,?,?,?)',(channel,ident,'Mi canal','rename-room',now))
            profile=dict(conn.execute('SELECT * FROM member_profiles WHERE member_id=?',(ident,)).fetchone())
            payment=dict(conn.execute('SELECT * FROM payments WHERE member_id=?',(ident,)).fetchone())
            ownership=dict(conn.execute('SELECT * FROM founder_ownership WHERE member_id=?',(ident,)).fetchone())
        before=self.row(ident);self.notices.reset_mock()
        result=self.rename(ident,'  NEW.HOLDER  ')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json,{'ok':True,'member_id':ident,'username':'new.holder','previous_username':'rename-holder','changed':True})
        self.assertEqual(self.row(ident),dict(before,username='new.holder'))
        session_owner=owner.get('/api/account/me').json['user']
        self.assertEqual(session_owner['id'],ident)
        self.assertEqual(session_owner['username'],'new.holder')
        self.assertEqual(session_owner['founder_number'],number)
        self.assertEqual(session_owner['role'],'member')
        self.assertTrue(session_owner['live_annual'])
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM member_profiles WHERE member_id=?',(ident,)).fetchone()),profile)
            self.assertEqual(dict(conn.execute('SELECT * FROM payments WHERE member_id=?',(ident,)).fetchone()),payment)
            self.assertEqual(dict(conn.execute('SELECT * FROM founder_ownership WHERE member_id=?',(ident,)).fetchone()),ownership)
            self.assertEqual(conn.execute('SELECT member_id FROM streamer_channels WHERE id=?',(channel,)).fetchone()['member_id'],ident)
        record=self.history(ident)
        self.assertEqual(len(record),1)
        self.assertEqual({key:record[0][key] for key in ['member_id','actor_id','former_username','new_username','changed_at']},
                         {'member_id':ident,'actor_id':self.admin_id,'former_username':'rename-holder','new_username':'new.holder','changed_at':record[0]['changed_at']})
        self.assertTrue(record[0]['changed_at'])
        self.notices.assert_not_called()
        for identity,status in [('rename-holder',401),('NEW.HOLDER',200),('rename@example.test',200)]:
            fresh=app.app.test_client()
            self.assertEqual(self.post(fresh,'/api/account/login',{'username':identity,'password':self.PASSWORD}).status_code,status)
            if status==200:self.assertEqual(fresh.get('/api/account/me').json['user']['id'],ident)

    def test_renaming_to_admin_word_does_not_grant_authority(self):
        client,ident=self.member('ordinary-name')
        self.assertEqual(self.rename(ident,'admin').status_code,200)
        self.assertEqual(client.get('/api/account/me').json['user']['role'],'member')
        self.assertEqual(client.get('/api/admin/members').status_code,403)
        self.assertEqual(self.rename(self.admin_id,'stolen-admin',client).status_code,403)

    def test_requires_administration_and_csrf(self):
        client,ident=self.member('rename-protected')
        for denied in [client,app.app.test_client()]:
            self.assertEqual(self.rename(ident,'cannot-rename',denied).status_code,403)
        raw=app.app.test_client()
        self.assertEqual(self.post(raw,'/api/account/login',{'username':'test-admin','password':'test-password-only-123'}).status_code,200)
        body={'member_id':ident,'username':'cannot-rename'}
        self.assertEqual(raw.post('/api/admin/members/rename',json=body).status_code,403)
        self.assertEqual(raw.post('/api/admin/members/rename',json=body,headers={'X-CSRF-Token':'invalid'}).status_code,403)
        self.assertEqual(self.row(ident)['username'],'rename-protected')
        self.assertEqual(self.history(ident),[])

    def test_duplicate_name_including_archived_account_returns_conflict(self):
        _,first=self.member('original-name')
        _,second=self.member('occupied-name')
        self.assertEqual(self.rename(first,'  OCCUPIED-NAME  ').status_code,409)
        self.assertEqual(self.post(self.admin,'/api/admin/members/archive',{'member_id':second,'archived':True}).status_code,200)
        self.assertEqual(self.rename(first,'occupied-name').status_code,409)
        self.assertEqual(self.row(first)['username'],'original-name')
        self.assertEqual(self.history(first),[])

    def test_invalid_input_is_rejected_before_changes(self):
        _,ident=self.member('valid-name')
        for body in [{},[],{'member_id':True,'username':'new-name'},{'member_id':ident,'username':12345},
                     {'member_id':ident,'username':''},{'member_id':ident,'username':'two words'},
                     {'member_id':ident,'username':'@name'},{'member_id':ident,'username':'x'*61}]:
            response=self.post(self.admin,'/api/admin/members/rename',body)
            self.assertEqual(response.status_code,400,(body,response.json))
        self.assertEqual(self.row(ident)['username'],'valid-name')
        self.assertEqual(self.history(ident),[])
        self.assertEqual(self.rename('f'*32,'missing-account').status_code,404)

    def test_archived_account_is_not_renamed(self):
        _,ident=self.member('archived-name')
        self.assertEqual(self.post(self.admin,'/api/admin/members/archive',{'member_id':ident,'archived':True}).status_code,200)
        result=self.rename(ident,'new-archived-name')
        self.assertEqual(result.status_code,409)
        self.assertEqual(self.row(ident)['username'],'archived-name')
        self.assertEqual(self.history(ident),[])

    def test_same_normalized_name_is_idempotent(self):
        _,ident=self.member('unchanged-name')
        before=self.row(ident)
        result=self.rename(ident,' UNCHANGED-NAME ')
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.json['changed'])
        self.assertEqual(result.json['previous_username'],'unchanged-name')
        self.assertEqual(self.row(ident),before)
        self.assertEqual(self.history(ident),[])

    def test_administrator_can_rename_self_without_losing_session(self):
        before=self.row(self.admin_id)
        result=self.rename(self.admin_id,'new-owner-name')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.row(self.admin_id),dict(before,username='new-owner-name'))
        current=self.admin.get('/api/account/me').json['user']
        self.assertEqual(current['id'],self.admin_id)
        self.assertEqual(current['role'],'admin')
        self.assertEqual(self.admin.get('/api/admin/members').status_code,200)
        self.assertEqual(self.history(self.admin_id)[0]['actor_id'],self.admin_id)

    def test_account_erasure_removes_its_private_name_history(self):
        _,ident=self.member('erase-original')
        self.assertEqual(self.rename(ident,'erase-renamed').status_code,200)
        self.assertEqual(len(self.history(ident)),1)
        response=self.post(self.admin,'/api/admin/members/delete',{'member_id':ident})
        self.assertEqual(response.status_code,200,response.json)
        self.assertIsNone(self.row(ident))
        self.assertEqual(self.history(ident),[])

    def test_competing_renames_assign_a_name_once(self):
        _,first=self.member('competing-first')
        _,second=self.member('competing-second')
        clients=[app.app.test_client(),app.app.test_client()]
        for client in clients:
            self.assertEqual(self.post(client,'/api/account/login',{'username':'test-admin','password':'test-password-only-123'}).status_code,200)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda item:self.rename(item[1],'only-one-name',item[0]),zip(clients,[first,second])))
        self.assertEqual(sorted(response.status_code for response in results),[200,409])
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM members WHERE username=?',('only-one-name',)).fetchone()['n'],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM member_name_history').fetchone()['n'],1)

    def test_flores_binding_stays_with_original_account_after_name_reuse(self):
        _,original=self.member('rosas')
        self.assertEqual(self.rename(original,'flores-personal').status_code,200)
        _,replacement=self.member('rosas')
        with app.app.app_context():
            m.init_database()
            with m.database() as conn:
                self.assertEqual(conn.execute("SELECT member_id FROM member_identity_links WHERE identity='flores'").fetchone()['member_id'],original)
        self.assertEqual(self.rename(replacement,'another-account').status_code,200)
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(conn.execute("SELECT member_id FROM member_identity_links WHERE identity='flores'").fetchone()['member_id'],original)
            self.assertNotEqual(original,replacement)

    def test_startup_seeds_flores_link_once_and_account_erasure_removes_it(self):
        _,ident=self.member('rosas')
        with app.app.app_context():
            m.init_database();m.init_database()
            with m.database() as conn:
                self.assertEqual([dict(row) for row in conn.execute('SELECT * FROM member_identity_links').fetchall()],
                                 [{'identity':'flores','member_id':ident}])
        self.assertEqual(self.rename(ident,'private-flores').status_code,200)
        self.assertEqual(self.post(self.admin,'/api/admin/members/delete',{'member_id':ident}).status_code,200)
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM member_identity_links').fetchone()['n'],0)


if __name__=='__main__':unittest.main()
