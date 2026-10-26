"""The same reserved founder sees payment only in the final week; no charge is automatic."""
from datetime import datetime,timedelta,timezone
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});login_context(context)
  original=context.request.get(BASE_URL+'/api/account/me').json();state={'days':8};now=datetime.now(timezone.utc)
  def account(route):
   until=now+timedelta(days=state['days']);opens=until-timedelta(days=7)
   data=dict(original,user=dict(original['user'],role='member',active=True,complimentary=False,founder_number=1,founder_active=True,live_lifetime=False,trial_active=True,live_trial_until=until.isoformat()),streamer_available=True,live_video_ready=True,founder_reservation={'number':1,'trial_until':until.isoformat(),'confirmed':False,'payment_opens_at':opens.isoformat()})
   route.fulfill(json=data)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/api/account/me',account)
  page.goto(BASE_URL+'/account');page.locator('#member-panel').wait_for()
  assert page.locator('#pricing').is_visible()
  assert page.locator('#pay-lifetime').get_attribute('href') is None
  state['days']=6;page.reload();page.wait_for_function("document.querySelector('#pay-lifetime').getAttribute('href')?.endsWith('/25EUR')")
  assert page.locator('#pay-lifetime').get_attribute('href')=='https://paypal.me/IMarcosIlla/25EUR'
  assert 'reservada' in page.locator('#access-status').inner_text()
  assert 'sin pago' in page.locator('#next-payment').inner_text().lower()
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: reserved-founder pricing visible, payment closed before final week, voluntary 25-euro external link in final week, expiry notice, four widths')

if __name__=='__main__':run()
