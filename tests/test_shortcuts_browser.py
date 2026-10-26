"""Every static destination resolves; clicked shortcuts open the intended visible UI."""
import os
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  guest=browser.new_context();page=guest.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda r:r.fulfill(json=[]))
  premiere=guest.request.get(BASE_URL+'/api/status').json()['live_premiere']
  for width in [1440,390,320]:
   page.set_viewport_size({'width':width,'height':1000});page.goto(BASE_URL+'/')
   page.wait_for_function('Boolean(window.OlNavigation)')
   if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()
   if premiere:
    page.wait_for_function("document.querySelector('#main-nav a[data-ol-original-href=\"/live#live-catalogue\"]')?.getAttribute('href')==='/live#ol-live-premiere'")
    link=page.locator('#main-nav a[data-ol-original-href="/live#live-catalogue"]') if width>=1000 else page.locator('#mobile-nav a[data-ol-original-href="/live#live-catalogue"]')
    if width<1000:page.locator('#mobile-menu').click()
    link.click();page.wait_for_url('**/live#ol-live-premiere');assert page.locator('#ol-live-premiere').is_visible()
    assert page.locator('#live-catalogue').is_hidden()
   page.goto(BASE_URL+'/account');page.wait_for_function('Boolean(window.OlNavigation)')
   # A known old link is repaired to the real registration form, never a guessed route.
   page.evaluate("()=>{const a=document.createElement('a');a.id='old-register-shortcut';a.href='#register';a.textContent='Crear cuenta';document.querySelector('header').append(a);window.OlNavigation.check();}")
   assert page.locator('#old-register-shortcut').get_attribute('href')=='/account#register-form'
   page.locator('#old-register-shortcut').click();assert page.locator('#register-form').is_visible()
   assert page.evaluate("document.activeElement.id==='register-form'")
   assert page.evaluate('window.OlNavigation.check().broken.length')==0
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  # Backward-compatible section aliases still open their actual working page.
  page.goto(BASE_URL+'/streamers#live-catalogue')
  if premiere:
   page.wait_for_function("location.hash==='#ol-live-premiere'");assert page.locator('#ol-live-premiere').is_visible()
  admin_context=browser.new_context();login_context(admin_context);admin=admin_context.new_page();admin.goto(BASE_URL+'/account')
  admin.locator('#admin-panel').wait_for(state='visible');admin.locator('#navigation-health-admin > summary').click();admin.locator('#navigation-check-now').click()
  assert 'Enlaces comprobados' in admin.locator('#navigation-check-status').inner_text()
  assert 'navigation-health.yml' in admin.locator('#navigation-health-admin a').get_attribute('href')
  assert not errors,errors;browser.close()
 print('OK: working shortcuts, premiere-aware live destinations, repaired registration alias, visible focus, admin checker, three widths')

if __name__=='__main__':run()
