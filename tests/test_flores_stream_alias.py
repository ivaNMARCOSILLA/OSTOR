"""Flores' display-only stream distinction stays scoped to the exact account."""
import secrets
import unittest
from datetime import timedelta
from unittest.mock import patch

import app
import membership as m
import streamers as st
from auth_support import authenticated_client


class FloresStreamAliasTests(unittest.TestCase):
    endpoint='/api/streamers/admin/flores-alias'
    expected={'title':'Triunfador'}

    def setUp(self):
        self.admin=authenticated_client(app.app,self.addCleanup)
        with app.app.app_context():st.init_database()

    def account(self,username,nickname='',email=None):
        ident=secrets.token_hex(16)
        with app.app.app_context(),m.database() as conn:
            conn.execute("INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,'member',?)",(ident,username,'isolated-not-a-login',m.stamp(m.now_utc())))
            conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',(ident,email or username+'@example.invalid',nickname,m.stamp(m.now_utc())))
        client=app.app.test_client()
        with client.session_transaction() as session:
            session['member_id']=ident;session['session_version']=0
        return client,ident

    def channel(self,owner,title):
        ident=secrets.token_hex(16)
        with app.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)',(ident,owner,title,'isolated-'+ident,m.stamp(m.now_utc()+timedelta(hours=1)),m.stamp(m.now_utc())))
        return ident

    def message(self,channel,author,text):
        with app.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO community_messages(id,channel_id,member_id,kind,body,created_at) VALUES(?,?,?,?,?,?)',(secrets.token_hex(16),channel,author,'comment',text,m.stamp(m.now_utc())))

    def test_alias_uses_exact_account_and_returns_independent_values(self):
        self.assertEqual(st.stream_alias('rosas'),self.expected)
        for username in ['Flores','ROSAS','rosas2',' rosas','test-admin',None]:
            self.assertIsNone(st.stream_alias(username))
        copy=st.stream_alias('rosas');copy['title']='Changed'
        self.assertEqual(st.stream_alias('rosas'),self.expected)

    def test_admin_section_is_available_without_fabricating_an_account_or_channel(self):
        response=self.admin.get(self.endpoint)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.json,{'stream_alias':self.expected,'account':None,'channel':None})
        self.account('rosas2','Flores')
        self.assertIsNone(self.admin.get(self.endpoint).json['account'])

    def test_section_is_admin_only_and_does_not_elevate_flores(self):
        flores,ident=self.account('rosas','Flores')
        self.assertEqual(app.app.test_client().get(self.endpoint).status_code,403)
        self.assertEqual(flores.get(self.endpoint).status_code,403)
        self.assertEqual(flores.get('/api/admin/members').status_code,403)
        user=flores.get('/api/account/me').json['user']
        self.assertEqual(user['role'],'member');self.assertFalse(user['active'])
        self.assertFalse(user['streamer_active'])

    def test_section_shows_real_flores_and_channel_without_profile_or_payment_changes(self):
        flores,ident=self.account('rosas','Flores')
        channel=self.channel(ident,'El directo de Flores')
        with app.app.app_context(),m.database() as conn:
            before_member=dict(conn.execute('SELECT * FROM members WHERE id=?',(ident,)).fetchone())
            before_profile=dict(conn.execute('SELECT * FROM member_profiles WHERE member_id=?',(ident,)).fetchone())
            before_payments=conn.execute('SELECT COUNT(*) AS n FROM payments').fetchone()['n']
        result=self.admin.get(self.endpoint).json
        self.assertEqual(result,{'stream_alias':self.expected,'account':{'id':ident,'username':'rosas','display_name':'Flores','archived':False},'channel':{'id':channel,'title':'El directo de Flores','live':True}})
        self.assertNotIn('@example.invalid',str(result))
        with app.app.app_context(),m.database() as conn:
            self.assertEqual(dict(conn.execute('SELECT * FROM members WHERE id=?',(ident,)).fetchone()),before_member)
            self.assertEqual(dict(conn.execute('SELECT * FROM member_profiles WHERE member_id=?',(ident,)).fetchone()),before_profile)
            self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM payments').fetchone()['n'],before_payments)
        self.assertEqual(flores.get('/api/account/me').json['user']['nickname'],'Flores')

    def test_channel_cards_identify_only_flores_channel_and_keep_titles(self):
        _,flores=self.account('rosas','Flores')
        _,other=self.account('other-creator','Flores')
        first=self.channel(flores,'Directo de Flores');second=self.channel(other,'Otro directo')
        response=app.app.test_client().get('/api/live/catalogue')
        self.assertEqual(response.status_code,200)
        channels={item['id']:item for item in response.json['channels']}
        self.assertEqual(channels[first]['stream_alias'],self.expected)
        self.assertEqual(channels[first]['title'],'Directo de Flores')
        self.assertIsNone(channels[second]['stream_alias'])

    def test_comments_show_the_distinction_only_for_flores_in_own_channel(self):
        flores,ident=self.account('rosas','Flores')
        _,other=self.account('other-creator','Flores')
        first=self.channel(ident,'Flores en directo');second=self.channel(other,'Segundo directo')
        self.message(first,ident,'Mensaje de Flores en su directo')
        self.message(first,other,'Una persona invitada')
        self.message(second,ident,'Flores visita otro directo')
        first_feed=flores.get('/api/streamers/'+first+'/comments')
        self.assertEqual(first_feed.status_code,200)
        comments={item['body']:item for item in first_feed.json['comments']}
        self.assertEqual(comments['Mensaje de Flores en su directo']['stream_alias'],self.expected)
        self.assertEqual(comments['Mensaje de Flores en su directo']['display_name'],'Flores')
        self.assertIsNone(comments['Una persona invitada']['stream_alias'])
        second_feed=flores.get('/api/streamers/'+second+'/comments')
        self.assertEqual(second_feed.status_code,200)
        self.assertIsNone(second_feed.json['comments'][0]['stream_alias'])

    def test_archived_flores_is_identified_without_showing_a_live_channel(self):
        _,ident=self.account('rosas','Flores')
        channel=self.channel(ident,'Directo archivado')
        admin_id=self.admin.get('/api/account/me').json['user']['id']
        with app.app.app_context(),m.database() as conn:
            conn.execute('INSERT INTO member_archives(member_id,archived_at,archived_by,reason) VALUES(?,?,?,?)',(ident,m.stamp(m.now_utc()),admin_id,'isolated-test'))
        result=self.admin.get(self.endpoint).json
        self.assertTrue(result['account']['archived'])
        self.assertEqual(result['channel'],{'id':channel,'title':'Directo archivado','live':False})

    def test_rename_keeps_flores_distinction_and_reused_username_cannot_take_it(self):
        owner,ident=self.account('rosas','Flores')
        first=self.channel(ident,'El canal original')
        token=self.admin.get('/api/account/me').json['csrf']
        result=self.admin.post('/api/admin/members/rename',json={'member_id':ident,'username':'flores.original'},headers={'X-CSRF-Token':token})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(owner.get('/api/account/me').json['user']['username'],'flores.original')
        impostor,other=self.account('rosas','Flores',email='second-rosas@example.invalid')
        second=self.channel(other,'El canal nuevo')
        with app.app.app_context():m.init_database()
        admin=self.admin.get(self.endpoint).json
        self.assertEqual(admin['account']['id'],ident)
        self.assertEqual(admin['account']['username'],'flores.original')
        self.assertEqual(admin['channel']['id'],first)
        channels={item['id']:item for item in owner.get('/api/live/catalogue').json['channels']}
        self.assertEqual(channels[first]['stream_alias'],self.expected)
        self.assertIsNone(channels[second]['stream_alias'])
        self.message(first,ident,'La persona original conserva su apodo')
        self.message(first,other,'Visita con el nombre anterior')
        self.message(second,ident,'La persona original visita otro canal')
        self.message(second,other,'La nueva cuenta publica en su propio canal')
        first_feed={item['body']:item for item in owner.get('/api/streamers/'+first+'/comments').json['comments']}
        self.assertEqual(first_feed['La persona original conserva su apodo']['stream_alias'],self.expected)
        self.assertIsNone(first_feed['Visita con el nombre anterior']['stream_alias'])
        second_feed=impostor.get('/api/streamers/'+second+'/comments').json['comments']
        self.assertEqual(len(second_feed),2)
        self.assertTrue(all(item['stream_alias'] is None for item in second_feed))

    def test_identity_is_read_once_per_request_including_missing_accounts(self):
        _,ident=self.account('rosas','Flores')
        with app.app.test_request_context():
            with patch.object(st,'database',wraps=m.database) as opened:
                for _ in range(3):self.assertEqual(st.stream_alias_for_member(ident),self.expected)
                self.assertEqual(opened.call_count,1)
        with app.app.app_context(),m.database() as conn:
            conn.execute("DELETE FROM members WHERE id=?",(ident,))
        with app.app.test_request_context():
            with patch.object(st,'database',wraps=m.database) as opened:
                for _ in range(3):self.assertIsNone(st.stream_alias_for_member(ident))
                self.assertEqual(opened.call_count,1)


if __name__=='__main__':unittest.main()
