"""Public real visits without identity leakage; explicit consent and withdrawal."""
from playwright.sync_api import sync_playwright,expect
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page();requests=[];errors=[];public_requests=[]
  page.clock.install()
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:requests.append(r.url) if r.method=='POST' and r.url.endswith('/api/visits') else None)
  page.on('request',lambda r:public_requests.append(r.url) if '/api/visits/public' in r.url else None)
  page.goto(BASE_URL+'/');page.locator('#public-visit-registry').wait_for();page.locator('#consent-decline').click();page.wait_for_timeout(500)
  assert not requests,'declining must not create visit records'
  initial=context.request.get(BASE_URL+'/api/visits/public').json()
  assert initial['summary']['sessions']==0 and initial['cumulative']['sessions']==0
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('0')
  assert page.locator('#public-visit-history').get_attribute('open') is None
  assert public_requests and all('compact=1' in url for url in public_requests),'closed recent details must use the inexpensive aggregate-only API'
  page.locator('#privacy-button').click();page.locator('#consent-accept').click()
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('1')
  expect(page.locator('#public-visit-list li')).to_have_count(0)
  page.locator('#public-visit-history>summary').click()
  page.locator('#public-visit-recent>summary').click()
  page.wait_for_function("document.querySelector('#public-visit-list').children.length===1")
  assert len(requests)==1
  public=context.request.get(BASE_URL+'/api/visits/public').json()
  assert public['summary']['sessions']==1 and public['summary']['browsers']==1
  assert public['cumulative']['sessions']==1
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('1')
  expect(page.locator('#public-visit-count')).to_contain_text('entrada acumulada')
  expect(page.locator('#public-visit-since')).to_contain_text('Desde el')
  assert '24 horas' not in page.locator('#public-visit-count').inner_text()
  assert 'navegadores' not in page.locator('#public-visit-count').inner_text()
  since=public['cumulative']['since'];period=page.locator('#public-visit-since').inner_text()
  assert set(public['visits'][0])=={'at','device','page'}
  for width in [1440,390,320]:
   page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   assert page.locator('#public-visit-registry').is_visible()
  page.locator('#public-visit-registry').screenshot(path='/tmp/electronicama-public-visits.png')
  page.locator('#privacy-button').click();page.locator('#consent-decline').click()
  page.wait_for_function("document.querySelector('#public-visit-list').children.length===0")
  after=context.request.get(BASE_URL+'/api/visits/public').json()
  assert after['summary']['sessions']==0 and after['cumulative']['sessions']==1
  assert after['cumulative']['since']==since
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('1')
  expect(page.locator('#public-visit-since')).to_have_text(period)
  page.locator('#public-visit-history>summary').click()
  expect(page.locator('#public-visit-status')).to_contain_text('El total acumulado se mantiene')
  # A failed refresh keeps the last real total and its fixed starting date.
  page.route('**/api/visits/public*',lambda route:route.fulfill(status=503,json={'error':'temporary'}))
  page.evaluate("window.dispatchEvent(new Event('electronicama:visit-recorded'))")
  expect(page.locator('#public-visit-update-status')).to_be_visible()
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('1')
  expect(page.locator('#public-visit-since')).to_have_text(period)
  page.unroute('**/api/visits/public*')
  page.evaluate("window.dispatchEvent(new Event('electronicama:visit-recorded'))")
  expect(page.locator('#public-visit-update-status')).to_be_hidden()
  page.reload();expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('1')
  expect(page.locator('#public-visit-since')).to_have_text(period)
  # A new browser's real entry reaches the existing page through its normal
  # periodic refresh, without reloading or inventing a client-side increment.
  other=browser.new_context();csrf=other.request.get(BASE_URL+'/api/account/me').json()['csrf']
  assert other.request.post(BASE_URL+'/api/visits',data={'consent':True,'page':'/','event':'page'},headers={'X-CSRF-Token':csrf}).status==200
  page.clock.fast_forward(30000)
  expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('2')
  expect(page.locator('#public-visit-count')).to_contain_text('entradas acumuladas')
  expect(page.locator('#public-visit-since')).to_have_text(period)
  # Direct entry to account has the same optional choice without blocking login.
  direct=browser.new_context();account=direct.new_page();account.goto(BASE_URL+'/account');account.locator('#visitor-consent-panel').wait_for()
  account.get_by_role('button',name='Solo necesarias',exact=True).click();assert account.locator('#login-form').is_visible()
  assert not errors,errors;browser.close()
 print('OK: real cumulative total and fixed date, explicit opt-in, private details removed on withdrawal, total preserved, recoverable refresh failure and three widths')
if __name__=='__main__':run()
