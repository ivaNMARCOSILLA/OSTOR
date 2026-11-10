"""Music stays the landing while accounts return for the Livis opening."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page()
  page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
  for width in [320,390,1440]:
   page.set_viewport_size({'width':width,'height':900});page.goto(BASE_URL+'/')
   page.locator('#library').wait_for();page.wait_for_function("document.querySelector('.header-account').getAttribute('href')==='/account'")
   if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()
   assert page.locator('#main-nav a[href="/account"],#mobile-nav a[href="/account"]').count()==2
   page.locator('.header-account:visible, #main-nav a[href="/account"]:visible, #mobile-nav a[href="/account"]:visible, #mobile-dock a[href="/account"]:visible').first.click();page.wait_for_url(BASE_URL+'/account')
   assert page.locator('#register-form').is_visible();assert page.locator('#login-form').is_visible();assert page.locator('#account-welcome').is_visible()
   assert page.locator('#granel-poster,.granel-poster,.search-granel-banner').count()==0
   page.locator('#granel-access-link').click()
   assert page.evaluate('document.activeElement.id')=='granel-access-title'
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.goto(BASE_URL+'/account#reset-password=example');assert page.locator('#password-reset-form').is_visible()
  page.goto(BASE_URL+'/live');assert 'Ol Live' in page.title()
  b.close()
 print('OK: music landing, restored account/registration/welcome, Ol Live name and private recovery')
if __name__=='__main__':run()
