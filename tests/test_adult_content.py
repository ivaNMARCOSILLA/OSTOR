import unittest
from datetime import date,timedelta
from unittest.mock import patch
import app,membership as m,streamers as st,age_policy
from auth_support import authenticated_client

class AdultContentTests(unittest.TestCase):
 def setUp(self):
  self.admin=authenticated_client(app.app,self.addCleanup)
  with app.app.app_context():st.init_database()
  self.admin.post('/api/streamers/me',json={'title':'Directo adulto','adult_content':True,'adult_rules_accepted':True})
  self.channel=self.admin.get('/api/streamers').json['mine']['id']
  with app.app.app_context(),m.database() as conn:conn.execute('UPDATE streamer_channels SET live_until=? WHERE id=?',(m.stamp(m.now_utc()+timedelta(hours=1)),self.channel))
  self.viewer=app.app.test_client();csrf=self.viewer.get('/api/account/me').json['csrf']
  from registration_support import registration_data
  self.viewer.post('/api/account/register',json=registration_data(self.viewer,{'username':'age-viewer','password':'age-viewer-password-123'}),headers={'X-CSRF-Token':csrf})
  self.csrf=self.viewer.get('/api/account/me').json['csrf'];self.base='/api/streamers/'+self.channel
 def confirm(self,years,context):
  born=date.today().replace(year=date.today().year-years).isoformat()
  return self.viewer.post(self.base+'/age-confirm',json={'birth_date':born,'context':context,'accept_rules':True},headers={'X-CSRF-Token':self.csrf})
 def test_unknown_location_requires_21_and_cannot_be_overridden_by_headers(self):
  info=self.viewer.get(self.base+'/age-policy',headers={'X-Country':'ES','X-VPN':'false'}).json
  self.assertEqual(info['minimum_age'],21);self.assertTrue(info['location_uncertain'])
  self.assertEqual(self.viewer.get(self.base+'/access').status_code,403)
  self.assertEqual(self.confirm(20,info['context']).status_code,403)
  self.assertEqual(self.confirm(22,info['context']).status_code,200)
  self.assertEqual(self.viewer.get(self.base+'/access').status_code,200)
  with app.app.app_context(),m.database() as conn:
   row=dict(conn.execute('SELECT * FROM adult_age_declarations').fetchone());self.assertNotIn('birth_date',row)
 def test_trusted_region_18_but_vpn_or_region_change_invalidates_declaration(self):
  with patch.dict(app.app.extensions,{'adult_region_assessor':lambda req:{'trusted':True,'country':'ES','vpn':False}}):
   info=self.viewer.get(self.base+'/age-policy').json;self.assertEqual(info['minimum_age'],18)
   self.assertEqual(self.confirm(20,info['context']).status_code,200)
   self.assertEqual(self.viewer.get(self.base+'/access').status_code,200)
  with patch.dict(app.app.extensions,{'adult_region_assessor':lambda req:{'trusted':True,'country':'US','vpn':True}}):
   self.assertEqual(self.viewer.get(self.base+'/age-policy').json['minimum_age'],21)
   self.assertEqual(self.viewer.get(self.base+'/access').status_code,403)
   self.assertEqual(self.confirm(22,info['context']).status_code,409)
 def test_token_and_chat_require_age_and_admin_classification_cannot_be_undone(self):
  with patch.object(st,'live_ready',return_value=True),patch.object(st,'mint_token') as mint:
   result=self.viewer.post(self.base+'/token',json={'publish':False},headers={'X-CSRF-Token':self.csrf});self.assertEqual(result.status_code,403);mint.assert_not_called()
  self.assertEqual(self.viewer.get(self.base+'/comments').status_code,403)
  self.assertEqual(self.admin.post('/api/admin/live-channels/adult-content',json={'channel_id':self.channel,'adult_content':True}).status_code,200)
  self.admin.post('/api/streamers/me',json={'title':'Cambio normal','adult_content':False})
  self.assertTrue(self.admin.get('/api/streamers').json['mine']['adult_content'])
  self.assertEqual(self.viewer.post('/api/admin/live-channels/adult-content',json={'channel_id':self.channel,'adult_content':False},headers={'X-CSRF-Token':self.csrf}).status_code,403)
