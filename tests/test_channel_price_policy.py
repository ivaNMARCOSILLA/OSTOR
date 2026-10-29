"""Automatic channel pricing is bounded, existing subscribers keep their price, months follow local time."""
from datetime import datetime,timezone
from unittest.mock import patch
import json
import membership as m,subscriptions as sub,app
import test_subscriptions as legacy

class ChannelPricePolicyTests(legacy.CreatorSubscriptionTests):
 def test_new_prices_are_between_three_and_four_and_monthly(self):
  for price,period in [(299,'month'),(401,'month'),(350,'once'),(True,'month')]:
   r=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':price,'period':period,'benefits':['badge']});self.assertEqual(r.status_code,400)
 def test_no_stripe_connection_saves_draft_instead_of_losing_proposal(self):
  with patch.dict('os.environ',{'OL_PAYMENT_PROVIDER':'stripe'}):
   r=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':350,'period':'month','benefits':['badge']})
   self.assertEqual(r.status_code,200);self.assertTrue(r.json['draft']);self.assertFalse(r.json['published']);self.assertIn('Conectar Stripe del creador',r.json['pending'])
   dashboard=self.creator.get('/api/channel-subscriptions/creator').json;self.assertEqual(dashboard['draft']['price_cents'],350)
 def test_price_increase_keeps_prior_subscriber_price_and_period(self):
  self.approve_all(self.proposal(350));self.assertEqual(self.confirm().status_code,200)
  before=self.viewer.get('/api/channel-subscriptions/'+self.channel).json['subscription_ends_at']
  update=self.post(self.creator,'/api/channel-subscriptions/propose',{'price_cents':400,'period':'month','benefits':['badge','subscriber_chat','exclusive_live']})
  self.assertTrue(update.json['automatic_price'])
  self.assertEqual(self.viewer.get('/api/channel-subscriptions/'+self.channel).json['agreement']['price_cents'],350)
  self.assertEqual(self.other.get('/api/channel-subscriptions/'+self.channel).json['agreement']['price_cents'],400)
  self.assertEqual(self.viewer.get('/api/channel-subscriptions/'+self.channel).json['subscription_ends_at'],before)
  with app.app.app_context(),m.database() as db:
   self.assertEqual(db.execute('SELECT amount_cents FROM creator_subscriptions').fetchone()['amount_cents'],350)
   self.assertEqual(db.execute('SELECT COUNT(*) AS n FROM subscription_approvals').fetchone()['n'],3)
 def test_calendar_month_preserves_local_hour_across_dst_and_short_months(self):
  start=datetime(2027,3,1,11,tzinfo=timezone.utc)
  self.assertEqual(sub.month_end(start,'Europe/Madrid'),datetime(2027,4,1,10,tzinfo=timezone.utc))
  self.assertEqual(sub.month_end(datetime(2027,1,31,12,tzinfo=timezone.utc),'UTC'),datetime(2027,2,28,12,tzinfo=timezone.utc))
  self.assertEqual(sub.month_end(datetime(2027,10,1,10,tzinfo=timezone.utc),'Europe/Madrid'),datetime(2027,11,1,11,tzinfo=timezone.utc))
