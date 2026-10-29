"""Filling the 100 founder numbers never blocks standard annual admission."""
import app,membership as m
import test_managed_payments as managed
from unittest.mock import patch

class StandardAfterFoundersTests(managed.ManagedPaymentTests):
 def test_standard_annual_checkout_and_broadcast_access_after_all_founder_numbers_taken(self):
  with app.app.app_context(),m.database() as db:
   for number in range(1,101):
    ident='founder-full-'+str(number);db.execute('INSERT INTO members(id,username,created_at) VALUES(?,?,?)',(ident,ident,m.stamp(m.now_utc())))
    db.execute('INSERT INTO live_founders(member_id,number,claimed_at) VALUES(?,?,?)',(ident,number,m.stamp(m.now_utc())))
  self.assertEqual(self.client.get('/api/live/founders').json['remaining'],0)
  order=self.checkout(checkout_id='cs_after_100');self.assertEqual(self.event(order).status_code,200)
  user=self.client.get('/api/account/me').json['user'];self.assertTrue(user['live_annual']);self.assertTrue(user['streamer_active']);self.assertIsNone(user['founder_number']);self.assertFalse(user['founder_active'])
  with patch('human_check.new_code',return_value='OL234'):proof=self.client.get('/api/account/human-check').json
  result=self.post(self.client,'/api/live/founders/claim',{'human_id':proof['id'],'human_answer':'OL234'})
  self.assertEqual(result.status_code,409);self.assertIn('acceso anual ordinario',result.json['error'])
  self.assertTrue(self.client.get('/api/account/me').json['user']['live_annual'])
