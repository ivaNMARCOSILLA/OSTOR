import base64
import hashlib
import hmac
import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch, Mock
import app
import membership as m
import streamers as st
from auth_support import authenticated_client
from legacy_support import legacy_payment

class StreamerTests(unittest.TestCase):
    def setUp(self):
        verified=patch('live_access.verified_broadcast',return_value=True);verified.start();self.addCleanup(verified.stop)
        self.admin=authenticated_client(app.app,self.addCleanup)
        with app.app.app_context():st.init_database()
        self.env=patch.dict(os.environ,{'LIVEKIT_URL':'','LIVEKIT_API_KEY':'','LIVEKIT_API_SECRET':'','MAGGY_STREAMERS_ENABLED':'0','MAGGY_STREAMER_SALES_ENABLED':'0'})
        self.env.start();self.addCleanup(self.env.stop)

    def post(self,client,path,data):
        if path=='/api/account/register':
         from registration_support import registration_data
         data=registration_data(client,data)
        csrf=client.get('/api/account/me').json['csrf']
        return client.post(path,json=data,headers={'X-CSRF-Token':csrf})

    def member(self,name):
        client=app.app.test_client()
        self.assertEqual(self.post(client,'/api/account/register',{'username':name,'password':'member-password-123'}).status_code,201)
        ident=client.get('/api/account/me').json['user']['id']
        return client,ident

    def enable(self):
        os.environ.update(LIVEKIT_URL='wss://video.example.org',LIVEKIT_API_KEY='test-key',LIVEKIT_API_SECRET='x'*40,MAGGY_STREAMERS_ENABLED='1',MAGGY_STREAMER_SALES_ENABLED='1')

    def pay(self,ident,plan,ref):
        if plan=='lifetime':return self.admin.post('/api/admin/confirm-payment',json={'member_id':ident,'plan':plan,'reference':ref})
        return legacy_payment(app.app,self.admin,ident,plan,ref)

    def creator(self):
        self.enable();client,ident=self.member('creator')
        self.assertEqual(self.pay(ident,'streamer','STREAMER-CREATOR-001').status_code,200)
        result=self.post(client,'/api/streamers/me',{'title':'My camera','bio':'Live','paypal_url':'https://paypal.me/CreatorLink','owns_paypal':True})
        self.assertEqual(result.status_code,200)
        return client,ident,result.json['channel']['id']

    def test_camera_permissions_are_allowed_only_on_the_streaming_page(self):
        with self.admin.get('/streamers') as page:
            self.assertEqual(page.status_code,200)
            self.assertIn('camera=(self)',page.headers['Permissions-Policy'])
            self.assertIn('microphone=(self)',page.headers['Permissions-Policy'])
            self.assertIn('display-capture=(self)',page.headers['Permissions-Policy'])
        with self.admin.get('/') as page:
            self.assertIn('camera=()',page.headers['Permissions-Policy'])
            self.assertIn('microphone=()',page.headers['Permissions-Policy'])

    def test_no_streamer_sale_until_video_is_explicitly_enabled(self):
        client,ident=self.member('viewer')
        self.assertFalse(client.get('/api/account/me').json['streamer_available'])
        self.assertEqual(self.pay(ident,'lifetime','STREAMER-NOT-ACTIVE').status_code,409)
        self.assertEqual(self.pay(ident,'lifetime','VIEWER-NOT-READY').status_code,409)
        self.enable()
        self.assertEqual(self.pay(ident,'monthly','VIEWER-OK-001').status_code,200)
        self.assertFalse(client.get('/api/account/me').json['user']['streamer_active'])
        self.assertEqual(self.post(client,'/api/streamers/me',{'title':'No rights'}).status_code,403)

    def test_video_testing_does_not_enable_streamer_sales(self):
        self.enable();os.environ['MAGGY_STREAMER_SALES_ENABLED']='0'
        self.assertTrue(st.live_ready());self.assertFalse(st.streamer_sales_ready())
        client,ident=self.member('preview-viewer')
        self.assertFalse(client.get('/api/account/me').json['streamer_available'])
        self.assertEqual(self.pay(ident,'lifetime','PREVIEW-NO-SALE').status_code,409)

    @patch.object(st.requests,'post')
    def test_admin_can_probe_service_without_disclosing_credentials_or_creating_rooms(self,post):
        self.enable();post.return_value=Mock(status_code=200,json=Mock(return_value={'rooms':[]}))
        result=self.admin.post('/api/streamers/admin/check-video',json={})
        self.assertEqual(result.status_code,200);self.assertTrue(result.json['connected'])
        self.assertTrue(post.call_args.args[0].endswith('/twirp/livekit.RoomService/ListRooms'))
        self.assertEqual(post.call_args.kwargs['json'],{})
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertNotIn('x'*40,result.get_data(as_text=True))
        post.return_value=Mock(status_code=401)
        result=self.admin.post('/api/streamers/admin/check-video',json={})
        self.assertEqual(result.status_code,502);self.assertFalse(result.json['connected'])

    @patch.object(st.requests,'post')
    def test_service_probe_requires_admin(self,post):
        self.enable();client,ident=self.member('probe-viewer');self.pay(ident,'monthly','PROBE-VIEWER-001')
        self.assertEqual(self.post(client,'/api/streamers/admin/check-video',{}).status_code,403)
        post.assert_not_called()

    def test_invalid_video_configuration_does_not_break_normal_accounts(self):
        with patch.dict(os.environ,{'MAGGY_STREAMERS_ENABLED':'1','LIVEKIT_URL':'wss://[invalid'}):
            response=self.admin.get('/api/account/me')
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json['streamer_available'])

    def test_existing_legacy_creator_purchase_keeps_its_rights_and_history(self):
        self.enable();client,ident=self.member('upgrade')
        self.pay(ident,'monthly','UPGRADE-VIEWER-001')
        self.assertEqual(self.pay(ident,'streamer','UPGRADE-STREAMER-001').status_code,200)
        data=client.get('/api/account/me').json
        self.assertTrue(data['user']['streamer_active'])
        payment=next(x for x in data['payments'] if x['plan']=='streamer')
        self.assertEqual(payment['amount_cents'],800)
        self.assertLess(abs((m.datetime.fromisoformat(payment['starts_at'])-m.now_utc()).total_seconds()),3)
        self.assertEqual(self.pay(ident,'streamer','UPGRADE-STREAMER-001').status_code,409)

    def test_viewer_cannot_publish_and_owner_token_has_limited_camera_grant(self):
        creator,ident,channel=self.creator()
        self.assertEqual(self.post(creator,'/api/streamers/me/live',{'live':True}).status_code,200)
        viewer,viewerid=self.member('viewer');self.pay(viewerid,'monthly','VIEWER-TOKEN-001')
        self.assertEqual(self.post(viewer,f'/api/streamers/{channel}/token',{'publish':True}).status_code,403)
        viewer_token=self.post(viewer,f'/api/streamers/{channel}/token',{'publish':False}).json['token']
        owner_token=self.post(creator,f'/api/streamers/{channel}/token',{'publish':True}).json['token']
        for token,publish in [(viewer_token,False),(owner_token,True)]:
            parts=token.split('.');claims=json.loads(base64.urlsafe_b64decode(parts[1]+'='*(-len(parts[1])%4)))
            self.assertEqual(claims['video']['canPublish'],publish)
            self.assertFalse(claims['video']['canPublishData'])
            if publish:self.assertEqual(set(claims['video']['canPublishSources']),{'camera','microphone','screen_share','screen_share_audio'})
            else:self.assertNotIn('canPublishSources',claims['video'])
            signature=base64.urlsafe_b64encode(hmac.new(('x'*40).encode(),'.'.join(parts[:2]).encode(),hashlib.sha256).digest()).rstrip(b'=').decode()
            self.assertEqual(parts[2],signature)
            self.assertLessEqual(claims['exp']-claims['iat'],300)

    def test_gifts_are_direct_external_links_without_commission_or_fake_confirmation(self):
        creator,ident,channel=self.creator()
        viewer,viewerid=self.member('supporter');self.pay(viewerid,'monthly','GIFT-VIEWER-001')
        result=self.post(viewer,f'/api/streamers/{channel}/gift-link',{'amount_cents':500})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['url'],'https://paypal.me/CreatorLink/5.00EUR')
        self.assertEqual(result.json['maggy_commission_cents'],0)
        self.assertFalse(result.json['payment_confirmed'])
        for amount in [True,1.5,0,100001]:self.assertEqual(self.post(viewer,f'/api/streamers/{channel}/gift-link',{'amount_cents':amount}).status_code,400)
        with app.app.app_context(),m.database() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) AS n FROM payments').fetchone()['n'],2)

    def test_paypal_links_require_ownership_declaration_and_cannot_redirect_elsewhere(self):
        creator,ident,channel=self.creator()
        for url in ['https://paypal.me.evil.test/Creator','https://evil.test/paypal.me/Creator','https://paypal.me/Creator/500EUR','http://paypal.me/Creator','https://user@paypal.me/Creator']:
            self.assertEqual(self.post(creator,'/api/streamers/me',{'title':'My channel','paypal_url':url,'owns_paypal':True}).status_code,400)
        self.assertEqual(self.post(creator,'/api/streamers/me',{'title':'My channel','paypal_url':'https://paypal.me/CreatorLink','owns_paypal':False}).status_code,400)

    def test_revocation_removes_streamer_rights_even_if_normal_access_is_later_renewed(self):
        creator,ident,channel=self.creator()
        self.admin.post('/api/admin/revoke',json={'member_id':ident})
        self.assertEqual(creator.get('/api/streamers').status_code,401)
        self.pay(ident,'monthly','RENEW-NORMAL-AFTER-REVOKE')
        self.post(creator,'/api/account/login',{'username':'creator','password':'member-password-123'})
        self.assertTrue(creator.get('/api/account/me').json['user']['active'])
        self.assertFalse(creator.get('/api/account/me').json['user']['streamer_active'])

    def test_streamer_expiry_does_not_remove_remaining_normal_access(self):
        creator,ident,channel=self.creator()
        with app.app.app_context(),m.database() as conn:
            conn.execute('UPDATE streamer_access SET until_at=? WHERE member_id=?',(m.stamp(m.now_utc()-timedelta(seconds=1)),ident))
        user=creator.get('/api/account/me').json['user']
        self.assertTrue(user['active']);self.assertFalse(user['streamer_active'])
        self.assertEqual(self.post(creator,f'/api/streamers/{channel}/token',{'publish':True}).status_code,403)

    def test_moderated_comments_transcripts_and_reports_are_private_and_role_bound(self):
        creator,ident,channel=self.creator()
        self.post(creator,'/api/streamers/me/live',{'live':True})
        viewer,viewer_id=self.member('comment-viewer')
        self.pay(viewer_id,'monthly','CHAT-VIEWER-001')
        endpoint='/api/streamers/'+channel+'/comments'
        self.assertTrue(self.post(viewer,endpoint,{'text':'Buen directo, gracias'}).json['accepted'])
        blocked=self.post(viewer,endpoint,{'text':'eres un gilipollas'}).json
        self.assertTrue(blocked['blocked']);self.assertIn('suspensión',blocked['warning'])
        self.assertEqual(len(viewer.get(endpoint).json['comments']),1)
        self.assertEqual(self.post(viewer,endpoint,{'kind':'transcript','text':'voz inventada'}).status_code,403)
        self.post(creator,endpoint,{'kind':'transcript','text':'Una frase privada de la voz'})
        self.assertEqual(len(viewer.get(endpoint).json['comments']),1)
        self.assertTrue(self.post(viewer,endpoint,{'kind':'report','text':'Posible actividad ilegal'}).json['reported'])
        self.assertEqual(viewer.get('/api/admin/moderation').status_code,403)
        log=self.admin.get('/api/admin/moderation').json
        self.assertEqual(log['total'],2)
        all_log=self.admin.get('/api/admin/moderation?flagged=0').json
        self.assertEqual(all_log['total'],4)
        self.assertTrue(any(r['kind']=='transcript' for r in all_log['records']))

    def test_toxic_profile_is_blocked_but_respectful_criticism_is_allowed(self):
        creator,ident,channel=self.creator()
        result=self.post(creator,'/api/streamers/me',{'title':'Los médicos de mi barrio','bio':'La sanidad pública debe mejorar sus tiempos de espera.'})
        self.assertEqual(result.status_code,200)
        result=self.post(creator,'/api/streamers/me',{'title':'Mi canal','bio':'Te voy a matar'})
        self.assertEqual(result.status_code,400)
        self.assertIn('buen trato',result.json['error'])
