"""Music stays the landing while accounts return for the Livis opening."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page()
  for width in [320,390,1440]:
   page.set_viewport_size({'width':width,'height':900});page.goto(BASE_URL+'/')
   page.locator('#library').wait_for();page.wait_for_function("document.querySelector('.header-account').getAttribute('href')==='/account'")
   if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()
   assert page.locator('#main-nav a[href="/account"],#mobile-nav a[href="/account"]').count()==2
   page.locator('.search-granel-link').click();page.wait_for_url(BASE_URL+'/account')
   assert page.locator('#register-form').is_visible();assert page.locator('#login-form').is_visible();assert page.locator('#account-welcome').is_visible()
   page.locator('#granel-poster').scroll_into_view_if_needed()
   page.wait_for_function("document.querySelector('#granel-poster').naturalWidth===1024&&document.querySelector('#granel-poster').naturalHeight===1536")
   assert page.locator('#granel-poster').get_attribute('alt')=='72 horas son de granel'
   assert page.locator('#granel-poster').evaluate('e=>{const r=e.getBoundingClientRect();return Math.abs(r.height/r.width-1.5)<.02}')
   if width in [390,1440]:page.locator('#account-welcome').screenshot(path=f'/tmp/electronicama-granel-poster-{width}.png')
   page.locator('#granel-access-link').click()
   assert page.evaluate('document.activeElement.id')=='granel-access-title'
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.goto(BASE_URL+'/account#reset-password=example');assert page.locator('#password-reset-form').is_visible()
  page.goto(BASE_URL+'/live');assert 'Ol Live' in page.title()
  b.close()
 print('OK: music landing, restored account/registration/welcome, Ol Live name and private recovery')
if __name__=='__main__':run()
