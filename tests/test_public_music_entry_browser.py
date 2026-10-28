"""Public entry opens music and keeps account preparation out of the menus."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page()
  for width in [320,390,1440]:
   page.set_viewport_size({'width':width,'height':900});page.goto(BASE_URL+'/account')
   page.wait_for_url('**/#library');page.locator('#library').wait_for()
   page.wait_for_function("document.querySelector('.header-account').textContent==='Escuchar música'")
   assert page.locator('.header-account').get_attribute('href')=='#library'
   assert page.locator('#main-nav a[href="/account"],#mobile-nav a[href="/account"]').count()==0
   assert not page.locator('.content a[href="/account"]:visible').count()
  page.goto(BASE_URL+'/live');page.wait_for_function("document.body.classList.contains('ol-live-premiere-only')")
  assert page.locator('a[href="/account"]:visible').count()==0
  for link in page.locator('#ol-live-premiere a,.premiere-public-actions a').all():
   assert link.is_visible() and link.get_attribute('href').startswith('/#')
   assert link.bounding_box()['height']>=44
  page.locator('#ol-live-premiere a').click();page.wait_for_url('**/#library')
  page.goto(BASE_URL+'/account?manage=1');assert page.locator('#login-form').is_visible()
  page.goto(BASE_URL+'/account#reset-password=example');assert page.locator('#password-reset-form').is_visible()
  b.close()
 print('OK: public account redirects to music; management and private reset link retained')
if __name__=='__main__':run()
