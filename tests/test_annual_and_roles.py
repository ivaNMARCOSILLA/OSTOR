"""Paid annual access expires; cancelling keeps the paid year; community roles never grant authority."""
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import app,membership as m
import test_managed_payments as managed

class AnnualAndRoleTests(managed.ManagedPaymentTests):
 def test_annual_paid_expiry_and_cancellation(self):
  self.assertEqual(self.post(self.client,'/api/account/live-trial',{}).status_code,410)
  self.assertFalse(self.client.get('/api/account/me').json['user']['active'])
  order=self.checkout();self.assertEqual(order['kind'],'platform_annual');self.assertEqual(order['amount_cents'],2500)
  self.assertEqual(self.event(order).status_code,200)
  before=self.client.get('/api/account/me').json;user=before['user'];self.assertTrue(user['live_annual']);self.assertFalse(user['live_lifetime']);self.assertTrue(user['streamer_active'])
  payment=before['payments'][0];self.assertEqual(payment['plan'],'annual');self.assertIn((datetime.fromisoformat(payment['ends_at'])-datetime.fromisoformat(payment['starts_at'])).days,[365,366])
  cancel=self.post(self.client,'/api/account/annual/cancel',{});self.assertEqual(cancel.status_code,200);self.assertEqual(cancel.json['access_until'],user['access_until'])
  self.assertTrue(self.client.get('/api/account/me').json['user']['live_annual']);self.assertEqual(self.post(self.client,'/api/account/annual/cancel',{}).status_code,200)
  after=datetime.fromisoformat(user['access_until'])+timedelta(seconds=1)
  with patch('membership.now_utc',return_value=after):
   expired=self.client.get('/api/account/me').json['user'];self.assertFalse(expired['live_annual']);self.assertFalse(expired['active']);self.assertFalse(expired['streamer_active'])
 def test_admin_approves_role_without_elevating_permissions(self):
  self.assertEqual(self.client.get('/api/account/me').json['user']['community_role'],'activo')
  data={'member_id':self.ident,'community_role':'docente'}
  self.assertEqual(self.post(self.client,'/api/admin/community-role',data).status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/community-role',data).status_code,200)
  user=self.client.get('/api/account/me').json['user'];self.assertEqual(user['community_role'],'docente');self.assertEqual(user['role'],'member');self.assertFalse(user['active'])
  self.assertEqual(self.client.get('/api/admin/members').status_code,403)
  self.assertEqual(self.post(self.admin,'/api/admin/community-role',{'member_id':self.ident,'community_role':'admin'}).status_code,400)
  self.assertEqual(self.post(self.admin,'/api/admin/community-role',{'member_id':self.ident,'community_role':'activo'}).status_code,200)
 def test_annual_terms_required_before_creating_a_checkout(self):
  import payments
  with patch.object(payments,'ready',return_value=True),patch.object(payments,'stripe') as provider:
   result=self.post(self.client,'/api/payments/checkout',{})
   self.assertEqual(result.status_code,409);provider.assert_not_called()
  with app.app.app_context(),m.database() as db:self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM stripe_orders').fetchone()['n'],0)
 def test_renewal_adds_a_year_and_old_refund_does_not_remove_new_payment(self):
  import payments
  first=self.checkout(checkout_id='cs_first_year');self.assertEqual(self.event(first).status_code,200)
  end=datetime.fromisoformat(self.client.get('/api/account/me').json['user']['access_until']);near=end-timedelta(days=15)
  with patch('membership.now_utc',return_value=near),patch('payments.now_utc',return_value=near):
   renewal=self.checkout(checkout_id='cs_second_year')
   obj={'id':renewal['checkout_id'],'payment_status':'paid','amount_total':2500,'currency':'eur','metadata':{'ol_order':renewal['id']},'payment_intent':'pi_second_year'}
   self.assertEqual(self.event(renewal,ident='evt_renewal',obj=obj).status_code,200)
   user=self.client.get('/api/account/me').json['user'];self.assertEqual(user['access_until'],m.stamp(m.end_of_plan(end,'annual')))
   self.assertEqual(self.event(first,ident='evt_old_refund',kind='charge.refunded',obj={'payment_intent':'pi_local_test','refunded':True}).status_code,200)
   self.assertTrue(self.client.get('/api/account/me').json['user']['live_annual'])
 def test_calendar_year_handles_leap_day(self):
  start=datetime(2028,2,29,tzinfo=timezone.utc);self.assertEqual(m.end_of_plan(start,'annual'),datetime(2029,2,28,tzinfo=timezone.utc))
