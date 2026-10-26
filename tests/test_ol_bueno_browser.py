from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda r:r.fulfill(json=[]))
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
  intro=page.locator('#ol-intro');assert intro.is_visible()
  page.locator('#intro-next').click();assert '25 €' in page.locator('#ol-intro-copy').inner_text()
  page.locator('#intro-next').click();assert page.locator('#intro-start').is_visible()
  page.locator('#intro-next').click();assert intro.is_hidden()
  page.reload();assert page.locator('#ol-intro').is_hidden()
  page.evaluate("localStorage.removeItem('ol_intro_bueno_v1')");page.reload()
  page.locator('#intro-skip').click();assert intro.is_hidden()
  assert 'maximum-scale' not in page.locator('meta[name=viewport]').get_attribute('content')
  assert 'user-scalable=no' not in page.locator('meta[name=viewport]').get_attribute('content')
  assert page.locator('#hero .gold-text').is_visible()
  assert '25 €' in page.locator('#planes .plan.featured h3').inner_text()
  assert all(old not in page.locator('#planes').inner_text() for old in ['1 €','6 €','8 €'])
  page.goto(BASE_URL+'/account');assert page.locator('#trial-start').is_disabled()
  assert page.locator('#pay-lifetime').count()==0
  assert page.locator('#payment-form').count()==0
  assert page.locator('#trial-start').inner_text()=='Iniciar mis siete días'
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   assert page.locator('#login-form input').first.evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')>=16
  admin_context=browser.new_context();login_context(admin_context);admin=admin_context.new_page();admin.goto(BASE_URL+'/account')
  admin.locator('#statistics-cards article').first.wait_for()
  admin.locator('#founder-activity-admin > summary').click()
  admin.wait_for_function("document.querySelector('#admin-founder-activity').children.length>0")
  # Wait for own-site intro metrics instead of asserting a tracking network exists.
  data=admin_context.request.get(BASE_URL+'/api/admin/statistics').json();assert data['promotion'].get('next',0)>=2
  assert data['promotion'].get('complete',0)>=1 and data['promotion'].get('skip',0)>=1
  page.goto(BASE_URL+'/');page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/ol-del-bueno-mobile.png')
  assert not errors,errors;browser.close()
 print('OK: gold/soft palette, functional optional introduction and aggregate metrics, 25-euro single plan, no early trial/billing, admin founder review, accessible iPhone scaling, four widths')

if __name__=='__main__':run()
