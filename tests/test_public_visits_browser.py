"""Public real visits without identity leakage; explicit consent and withdrawal."""
from playwright.sync_api import sync_playwright,expect
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page();requests=[];errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:requests.append(r.url) if r.method=='POST' and r.url.endswith('/api/visits') else None)
  page.goto(BASE_URL+'/');page.locator('#public-visit-registry').wait_for();page.locator('#consent-decline').click();page.wait_for_timeout(500)
  assert not requests,'declining must not create visit records'
  assert context.request.get(BASE_URL+'/api/visits/public').json()['summary']['sessions']==0
  page.locator('#privacy-button').click();page.locator('#consent-accept').click()
  page.wait_for_function("document.querySelector('#public-visit-list').children.length===1")
  assert len(requests)==1
  public=context.request.get(BASE_URL+'/api/visits/public').json()
  assert public['summary']['sessions']==1 and public['summary']['browsers']==1
  assert set(public['visits'][0])=={'at','device','page'}
  for width in [1440,390,320]:
   page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   assert page.locator('#public-visit-registry').is_visible()
  page.locator('#public-visit-registry').screenshot(path='/tmp/electronicama-public-visits.png')
  page.locator('#privacy-button').click();page.locator('#consent-decline').click()
  page.wait_for_function("document.querySelector('#public-visit-list').children.length===0")
  assert context.request.get(BASE_URL+'/api/visits/public').json()['summary']['sessions']==0
  # Direct entry to account has the same optional choice without blocking login.
  direct=browser.new_context();account=direct.new_page();account.goto(BASE_URL+'/account');account.locator('#visitor-consent-panel').wait_for()
  account.get_by_role('button',name='Solo necesarias',exact=True).click();assert account.locator('#login-form').is_visible()
  assert not errors,errors;browser.close()
 print('OK: public real entrance visible on all home screens, explicit opt-in, no private fields, withdrawal removes record, direct-account choice')
if __name__=='__main__':run()
