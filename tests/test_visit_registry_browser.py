"""Readable consented visit registry, separate browser IDs and role boundaries."""
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.clock.install();requests=[];errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  rows=[{'id':'session-one','device_id':'phone1111','network_id':'shared1234','network_day':'2026-10-30','username':None,'device':'Móvil','os':'Android','browser':'Chrome','started_at':'2026-10-30T12:15:00Z','last_seen':'2026-10-30T12:25:00Z','pageviews':3,'last_page':'/live'},{'id':'session-two','device_id':'laptop2222','network_id':'shared1234','network_day':'2026-10-30','username':'<img src=x onerror=alert(1)>','device':'Ordenador','os':'Windows','browser':'Edge','started_at':'2026-10-30T12:16:00Z','last_seen':'2026-10-30T12:24:00Z','pageviews':2,'last_page':'/'}]
  def registry(route):
   query=parse_qs(urlparse(route.request.url).query);requests.append(query);number=int(query.get('page',['1'])[0]);kind=query.get('kind',['all'])[0]
   visits=rows if number==1 else [dict(rows[0],id='session-three',device_id='tablet3333',device='Tablet',os='iPadOS',browser='Safari')]
   if kind=='registered':visits=[rows[1]]
   route.fulfill(json={'visits':visits,'page':number,'pages':1 if kind=='registered' else 2,'total':1 if kind=='registered' else 26,'retention_days':7,'summary':{'sessions':1 if kind=='registered' else 26,'browsers':1 if kind=='registered' else 3,'registered':1,'guests':0 if kind=='registered' else 25}})
  page.route('**/api/admin/visits?*',registry)
  page.goto(BASE_URL+'/account');page.locator('#statistics-cards article').first.wait_for();page.locator('#visitor-registry > summary').click();expect(page.locator('.visitor-session')).to_have_count(2)
  assert 'Navegador D-phone1111' in page.locator('#visitor-registry-list').inner_text()
  assert 'Navegador D-laptop2222' in page.locator('#visitor-registry-list').inner_text()
  assert page.locator('#visitor-registry-list').inner_text().count('R-shared1234')==2
  assert '<img src=x onerror=alert(1)>' in page.locator('#visitor-registry-list').inner_text()
  assert page.locator('#visitor-registry-list img').count()==0
  assert '13:15' in page.locator('#visitor-registry-list').inner_text()
  assert 'Europe/Madrid' in page.locator('#visitor-registry').inner_text()
  assert 'IP completas' in page.locator('#visitor-registry').inner_text()
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   assert page.locator('.visitor-session').first.evaluate('e=>e.scrollWidth<=e.clientWidth+1'),width
  page.screenshot(path='/tmp/ol-visit-registry-mobile.png',full_page=True)
  page.locator('#visitor-registry-next').click();expect(page.locator('#visitor-registry-list')).to_contain_text('Navegador D-tablet3333');expect(page.locator('#visitor-registry-page')).to_contain_text('Página 2')
  page.locator('#visitor-registry-filter').select_option('registered');expect(page.locator('.visitor-session')).to_have_count(1);expect(page.locator('#visitor-registry-page')).to_contain_text('Página 1 de 1')
  assert requests[-1]['kind']==['registered'] and requests[-1]['page']==['1']
  before=len(requests);page.clock.fast_forward(30000);expect(page.locator('#visitor-registry-refresh')).to_be_enabled();page.wait_for_timeout(100);assert len(requests)==before+1
  page.locator('#visitor-registry > summary').click();before=len(requests);page.clock.fast_forward(30000);page.wait_for_timeout(100);assert len(requests)==before
  guestctx=browser.new_context();guest=guestctx.new_page();guest_requests=[];guest.route('**/api/admin/visits?*',lambda r:(guest_requests.append(r.request.url),r.fulfill(status=403,json={'error':'Solo administración'})));guest.goto(BASE_URL+'/account');assert not guest.locator('#visitor-registry').is_visible();assert not guest_requests
  assert not errors,errors;browser.close()
 print('OK: private visit registry, distinct browser labels on one protected network, safe text, Madrid times, pagination/filter, four widths and scoped 30s refresh')
if __name__=='__main__':run()
