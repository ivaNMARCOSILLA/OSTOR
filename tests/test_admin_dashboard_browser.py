from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();login_context(context);page=context.new_page();errors=[];calls=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  members=[{'id':str(i),'username':f'client-{i:03}','role':'member','active':i%2==0,'complimentary':i%3==0,'access_until':None,'streamer_until':None} for i in range(61)]
  page.route('**/api/admin/members',lambda route:route.fulfill(json={'members':members,'payments':[]}))
  def invitations(route):
   calls.append(route.request.url);route.fulfill(json={'total':0,'pages':1,'page':1,'invitations':[]})
  page.route('**/api/admin/invitations?*',invitations)
  page.goto(BASE_URL+'/account');page.locator('#admin-members tr').first.wait_for()
  assert page.locator('#admin-members tr').count()==25
  assert '61 clientes' in page.locator('#admin-counters').inner_text()
  assert not calls
  page.locator('#members-next').click();assert 'Página 2' in page.locator('#member-page').inner_text()
  page.locator('#admin-member-search').fill('client-060');assert page.locator('#admin-members tr').count()==1
  page.locator('#invitation-history summary').click();page.wait_for_function("document.querySelector('#invitation-count').textContent.includes('0 invitaciones')")
  page.locator('#notification-history summary').click();page.wait_for_function("document.querySelector('#mail-status').textContent.includes('normalesoutro@gmail.com')")
  assert page.locator('#retry-notifications').is_disabled()
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: 25 clients per page, counters, search, lazy private invitation history, honest mail setup, 4 widths')

if __name__=='__main__':run()
