"""Public premiere hides working panels while admin retains preparation access."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000});page.goto(BASE_URL+'/live')
   page.wait_for_function("document.querySelector('[data-premiere-state]').textContent.includes('Próximo estreno')")
   assert page.locator('.ol-live-premiere').is_visible()
   assert page.locator('#creator-panel').is_hidden()
   assert page.locator('#live-catalogue').is_hidden()
   assert page.locator('#stream-studio').is_hidden()
   assert page.locator('.premiere-public-actions a').first.is_visible()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.goto(BASE_URL+'/account');page.wait_for_function("document.querySelector('#trial-start').textContent.includes('Próximo estreno')")
  assert page.locator('#trial-start').is_disabled()
  admin_context=browser.new_context();login_context(admin_context)
  admin=admin_context.new_page();admin.goto(BASE_URL+'/live')
  admin.locator('#video-setup').wait_for(state='visible')
  assert not admin.locator('body').evaluate("e=>e.classList.contains('ol-live-premiere-only')")
  admin.goto(BASE_URL+'/account');admin.locator('#statistics-cards article').first.wait_for()
  assert admin.locator('[data-stripe-setup]').is_hidden()
  admin.locator('#operations-admin > summary').click()
  assert admin.locator('#paypal-current-status').is_visible()
  assert not errors,errors
  page.goto(BASE_URL+'/live');page.screenshot(path='/tmp/ol-980-premiere-mobile.png',full_page=True)
  browser.close()
 print('OK: premiere at four widths, public panels hidden, trial disabled, admin studio retained, Stripe hidden, PayPal disclosure visible')

if __name__=='__main__':run()
