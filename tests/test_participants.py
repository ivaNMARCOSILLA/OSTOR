"""Administrative participant files use existing facts, never invented activity."""
import json
import secrets
import unittest
from datetime import timedelta

import app as application
import membership as m
import streamers
from account_archives import close_member
from auth_support import authenticated_client


class ParticipantTrackingTests(unittest.TestCase):
    def setUp(self):
        self.app = application.app
        self.admin = authenticated_client(self.app, self.addCleanup)
        with self.app.app_context():
            streamers.init_database()
        self.admin_id = self.admin.get('/api/account/me').json['user']['id']
        self.member, self.member_id = self.account('tracked-person')
        self.other, self.other_id = self.account('another-person')
        self.guest = self.app.test_client()

    def account(self, username, activated=True, nickname=None, created_at=None):
        ident = secrets.token_hex(16)
        created_at = created_at or m.stamp(m.now_utc() - timedelta(days=3))
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO members(id,username,password_hash,role,created_at) VALUES(?,?,?,?,?)',
                         (ident, username, 'password-private-sentinel' if activated else None, 'member', created_at))
            conn.execute('INSERT INTO member_profiles(member_id,email,nickname,updated_at) VALUES(?,?,?,?)',
                         (ident, username+'@private.invalid', nickname or 'Nombre '+username, created_at))
        client = self.app.test_client()
        with client.session_transaction() as session:
            session['member_id'] = ident
            session['session_version'] = 0
        return client, ident

    def detail(self, ident=None):
        response = self.admin.get('/api/admin/participants/'+(ident or self.member_id))
        self.assertEqual(response.status_code, 200, response.json)
        self.assertIn('no-store', response.headers.get('Cache-Control', ''))
        return response.json

    def video(self, owner, title, state='published', created_at=None):
        ident = secrets.token_hex(16)
        instant = created_at or m.stamp(m.now_utc())
        with self.app.app_context(), m.database() as conn:
            conn.execute('''INSERT INTO community_videos
                (id,owner_id,title,description,category,filename,mime_type,size_bytes,
                 object_key,upload_id,part_size,part_count,state,technical_checked,
                 verified_etag,created_at,updated_at,published_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (ident, owner, title, 'Una creación propia', 'dance', 'mi-video.mp4',
                 'video/mp4', 123, 'videos/private-object-sentinel/'+ident,
                 'private-upload-sentinel-'+ident, 8388608, 1, state, 1,
                 'private-etag-sentinel', instant, instant,
                 instant if state == 'published' else None))
        return ident

    def assert_private_values_absent(self, value):
        raw = json.dumps(value, ensure_ascii=False)
        for secret in ['password-private-sentinel', '@private.invalid',
                       'private-object-sentinel', 'private-upload-sentinel',
                       'private-etag-sentinel', 'private-network-sentinel',
                       'private-room-sentinel', 'private-payment-reference']:
            self.assertNotIn(secret, raw)
        for field in ['password_hash', 'session_version', 'object_key', 'upload_id',
                      'verified_etag', 'profile_email', 'network_id', 'room_name']:
            self.assertNotIn('"'+field+'"', raw)

    def test_only_administrators_can_list_or_open_participant_files(self):
        for client in [self.guest, self.member]:
            for path in ['/api/admin/participants', '/api/admin/participants/'+self.member_id]:
                self.assertEqual(client.get(path).status_code, 403)
        listing = self.admin.get('/api/admin/participants')
        self.assertEqual(listing.status_code, 200)
        self.assertIn('no-store', listing.headers.get('Cache-Control', ''))
        self.assert_private_values_absent(listing.json)
        self.assert_private_values_absent(self.detail())

    def test_server_pagination_search_and_page_bounds(self):
        ids = []
        for number in range(29):
            _, ident = self.account('cohort-'+str(number).zfill(3), nickname='Grupo '+str(number))
            ids.append(ident)
        first = self.admin.get('/api/admin/participants').json
        self.assertEqual(first['page_size'], 25)
        self.assertEqual(len(first['participants']), 25)
        self.assertGreaterEqual(first['total'], 31)
        final = self.admin.get('/api/admin/participants?page=999999').json
        self.assertEqual(final['page'], final['pages'])
        self.assertTrue(final['participants'])
        result = self.admin.get('/api/admin/participants?q=COHORT-028').json
        self.assertEqual(result['total'], 1)
        self.assertEqual(result['participants'][0]['id'], ids[-1])
        nickname = self.admin.get('/api/admin/participants?q=Grupo%2027').json
        self.assertEqual(nickname['total'], 1)
        self.assertEqual(nickname['participants'][0]['id'], ids[-2])
        quoted = self.admin.get('/api/admin/participants', query_string={'q': "' OR 1=1 --"}).json
        self.assertEqual(quoted['participants'], [])
        for query in [{'page': 'not-a-number'}, {'archived': 'maybe'}, {'q': 'x'*5000}]:
            self.assertEqual(self.admin.get('/api/admin/participants', query_string=query).status_code, 400)

    def test_registration_and_invitation_are_distinct_and_unknown_activity_is_null(self):
        created = '2020-01-02T03:04:05+00:00'
        _, ident = self.account('waiting-person', activated=False, created_at=created)
        invited = self.detail(ident)
        self.assertEqual(invited['participant']['created_at'], created)
        self.assertIs(invited['participant']['account_activated'], False)
        self.assertIsNone(invited['participant']['last_activity_at'])
        self.assertIsNone(invited['activity']['last_activity_at'])
        self.assertIsNone(invited['activity']['verified_seconds'])
        self.assertIsNone(invited['activity']['last_verified_at'])
        self.assertIs(self.detail()['participant']['account_activated'], True)

    def test_detail_uses_own_real_videos_channel_and_verified_payment_only(self):
        self.video(self.member_id, 'Baile público')
        self.video(self.member_id, 'En cuarentena', 'quarantined')
        self.video(self.member_id, 'Retirado', 'deleted')
        self.video(self.other_id, 'Vídeo de otra persona')
        now = m.now_utc()
        start, end = m.stamp(now-timedelta(days=1)), m.stamp(now+timedelta(days=364))
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO streamer_channels(id,member_id,title,room_name,live_until,updated_at) VALUES(?,?,?,?,?,?)',
                         (secrets.token_hex(16), self.member_id, 'Mi canal', 'private-room-sentinel', end, start))
            conn.execute('INSERT INTO payments VALUES(?,?,?,?,?,?,?,?,?)',
                         (secrets.token_hex(16), self.member_id, 'annual', 2500,
                          start, end, start, self.admin_id, 'private-payment-reference'))
            conn.execute('UPDATE members SET access_until=? WHERE id=?', (end, self.member_id))
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)', (self.member_id, start))
        detail = self.detail()
        self.assertEqual(detail['videos']['counts']['published'], 1)
        self.assertEqual(detail['videos']['counts']['quarantined'], 1)
        self.assertEqual(detail['videos']['counts']['deleted'], 1)
        self.assertEqual({row['title'] for row in detail['videos']['latest']},
                         {'Baile público', 'En cuarentena', 'Retirado'})
        self.assertEqual([row['title'] for row in detail['channels']], ['Mi canal'])
        self.assertIs(detail['channels'][0]['live'], True)
        self.assertEqual(len(detail['payments']), 1)
        self.assertEqual(detail['payments'][0]['amount_cents'], 2500)
        self.assertEqual(detail['payments'][0]['verified_at'], start)
        self.assertIs(detail['participant']['access']['live_annual'], True)
        self.assertIs(detail['participant']['access_active'], True)
        self.assert_private_values_absent(detail)

    def test_last_activity_comes_from_existing_per_member_observations(self):
        now = m.now_utc()
        presence = m.stamp(now-timedelta(minutes=5))
        verified = m.stamp(now-timedelta(minutes=3))
        consented = m.stamp(now-timedelta(minutes=1))
        with self.app.app_context(), m.database() as conn:
            conn.execute('INSERT INTO online_presence VALUES(?,?,?)', (secrets.token_hex(16), self.member_id, presence))
            conn.execute('INSERT INTO founder_activity(member_id,total_seconds,session_seconds,last_verified_at,qualification_until) VALUES(?,?,?,?,?)',
                         (self.member_id, 1234, 45, verified, m.stamp(now+timedelta(days=20))))
            device = secrets.token_hex(16)
            conn.execute('INSERT INTO visitor_devices VALUES(?,?,?)', (device, presence, consented))
            conn.execute('''INSERT INTO visitor_sessions
                (id,device_id,member_id,account_kind,started_at,last_seen,pageviews,last_page,
                 network_id,network_day,device,os,browser) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (secrets.token_hex(16), device, self.member_id, 'member', presence, consented,
                 2, '/videos', 'private-network-sentinel', now.date().isoformat(), 'mobile', 'test-os', 'test-browser'))
            conn.execute('INSERT INTO online_presence VALUES(?,?,?)', (secrets.token_hex(16), self.other_id, m.stamp(now)))
        detail = self.detail()
        self.assertEqual(detail['activity']['last_activity_at'], consented)
        self.assertEqual(detail['participant']['last_activity_at'], consented)
        self.assertEqual(detail['activity']['verified_seconds'], 1234)
        self.assertEqual(detail['activity']['last_verified_at'], verified)
        self.assert_private_values_absent(detail)

    def test_renaming_keeps_one_stable_file_and_archiving_does_not_claim_live_access(self):
        renamed = self.admin.post('/api/admin/members/rename', json={'member_id': self.member_id, 'username': 'renamed-person'})
        self.assertEqual(renamed.status_code, 200, renamed.json)
        detail = self.detail()
        self.assertEqual(detail['participant']['id'], self.member_id)
        self.assertEqual(detail['participant']['username'], 'renamed-person')
        self.assertIn('tracked-person', json.dumps(detail['timeline']))
        self.assertIn('renamed-person', json.dumps(detail['timeline']))
        with self.app.app_context(), m.database() as conn:
            conn.execute('BEGIN IMMEDIATE')
            close_member(conn, self.member_id, self.admin_id)
        hidden = self.admin.get('/api/admin/participants?q=renamed-person').json
        self.assertEqual(hidden['participants'], [])
        archived = self.admin.get('/api/admin/participants?q=renamed-person&archived=1').json
        self.assertEqual(len(archived['participants']), 1)
        detail = self.detail()
        self.assertIs(detail['participant']['archived'], True)
        self.assertIs(detail['participant']['access_active'], False)
        self.assertIs(detail['participant']['streamer_active'], False)
        self.assertTrue(detail['timeline'])

    def test_permanent_founder_number_survives_expired_annual_access(self):
        now = m.now_utc()
        assigned, expired = m.stamp(now-timedelta(days=366)), m.stamp(now-timedelta(days=1))
        with self.app.app_context(), m.database() as conn:
            conn.execute('UPDATE members SET access_until=? WHERE id=?', (expired, self.member_id))
            conn.execute('INSERT INTO live_entitlements(member_id,paid_at) VALUES(?,?)', (self.member_id, assigned))
            conn.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)', (self.member_id, 42, assigned))
            conn.execute('INSERT INTO founder_ownership(member_id,number,assigned_at) VALUES(?,?,?)', (self.member_id, 42, assigned))
        detail = self.detail()
        self.assertEqual(detail['founder_ownership']['number'], 42)
        self.assertIs(detail['founder_ownership']['permanent'], True)
        self.assertIs(detail['participant']['access']['live_annual'], False)
        self.assertIs(detail['participant']['access_active'], False)
        self.assertEqual(detail['participant']['founder_number'], 42)

    def test_latest_content_is_bounded_and_missing_members_are_not_fabricated(self):
        now = m.now_utc()
        for number in range(12):
            self.video(self.member_id, 'Publicación '+str(number), created_at=m.stamp(now+timedelta(seconds=number)))
        self.video(self.other_id, 'Solo de otra cuenta', created_at=m.stamp(now+timedelta(seconds=30)))
        detail = self.detail()
        self.assertEqual(detail['videos']['counts']['published'], 12)
        self.assertEqual(len(detail['videos']['latest']), 10)
        self.assertNotIn('Solo de otra cuenta', json.dumps(detail))
        self.assertLessEqual(len(detail['timeline']), 50)
        self.assertEqual(self.admin.get('/api/admin/participants/'+'f'*32).status_code, 404)
        self.assertIn(self.admin.get('/api/admin/participants/not-an-id').status_code, [400, 404])


if __name__ == '__main__':
    unittest.main()
