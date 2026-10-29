"""Music stays the landing while accounts return for the Livis opening."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page()
  for width in [320,390,1440]:
   page.set_viewport_size({'width':width,'height':900});page.goto(BASE_URL+'/')
   page.locator('#library').wait_for();page.wait_for_function("document.querySelector('.header-account').getAttribute('href')==='/account'")
   assert page.locator('#main-nav a[href="/account"],#mobile-nav a[href="/account"]').count()==2
   page.goto(BASE_URL+'/account');assert page.locator('#register-form').is_visible();assert page.locator('#login-form').is_visible();assert page.locator('#account-welcome').is_visible()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.goto(BASE_URL+'/account#reset-password=example');assert page.locator('#password-reset-form').is_visible()
  page.goto(BASE_URL+'/live');assert 'Ol Livis' in page.title()
  b.close()
 print('OK: music landing, restored account/registration/welcome, Ol Livis name and private recovery')
if __name__=='__main__':run()
