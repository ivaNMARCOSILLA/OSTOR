"""Consent controls actual first-party click logging; only the professional admin profile can view it."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda r:r.fulfill(json=[]));page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('#search-input').fill('never-store-private-search');page.locator('#search-button').click();page.wait_for_timeout(1800)
  adminctx=b.new_context();login_context(adminctx)
  initial=adminctx.request.get(BASE_URL+'/api/admin/guest-journeys').json();baseline=initial['total'];initial_ids={v['id'] for v in initial['visits']}
  page.locator('[data-cookie-preferences]:visible').first.click();page.locator('#consent-accept').click();page.wait_for_timeout(300)
  page.locator('#search-input').fill('never-store-private-search');page.locator('#search-button').click();page.locator('[data-view=favorites]').first.click();page.wait_for_timeout(1800)
  assert ctx.request.get(BASE_URL+'/api/admin/guest-journeys').status==403
  visits=adminctx.request.get(BASE_URL+'/api/admin/guest-journeys').json();assert visits['total']==baseline+1
  visit_id=next(v['id'] for v in visits['visits'] if v['id'] not in initial_ids)
  events=adminctx.request.get(BASE_URL+'/api/admin/guest-journeys?visit='+visit_id).json()['events']
  assert any(e['target']=='buscar-musica' for e in events);assert any(e['target']=='favoritos' for e in events);assert 'never-store-private-search' not in str(events)
  admin=adminctx.new_page();admin.goto(BASE_URL+'/account');admin.locator('#guest-journeys > summary').click();admin.locator('#guest-journey-list button').first.wait_for();admin.locator('#guest-journey-list button').filter(has_text=visit_id[:8]).first.click();admin.locator('#guest-journey-events li').first.wait_for()
  assert 'Buscar música' in admin.locator('#guest-journey-events').inner_text()
  page.locator('[data-cookie-preferences]:visible').first.click();page.locator('#consent-decline').click();page.wait_for_timeout(300)
  assert adminctx.request.get(BASE_URL+'/api/admin/guest-journeys').json()['total']==baseline
  assert not errors,errors;b.close()
 print('OK: decline stores no clicks; opt-in records ordered safe actions; admin profile reads them; withdrawal erases them')
if __name__=='__main__':run()
