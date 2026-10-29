"""An edit from another browser context updates the existing page without navigation."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);first=browser.new_context();second=browser.new_context();login_context(first);login_context(second)
  def save(ctx,title):
   csrf=ctx.request.get(BASE_URL+'/api/account/me').json()['csrf'];result=ctx.request.post(BASE_URL+'/api/streamers/me',data={'title':title},headers={'X-CSRF-Token':csrf});assert result.status==200
  save(first,'Nombre inicial');page=first.new_page();navigations=[];page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
  page.goto(BASE_URL+'/live');page.wait_for_function("document.querySelector('#channel-title').value==='Nombre inicial'")
  page.wait_for_timeout(500);save(second,'Cambio desde otro dispositivo')
  page.wait_for_function("document.querySelector('#channel-title').value==='Cambio desde otro dispositivo'",timeout=12000)
  assert len(navigations)==1,navigations
  page.locator('#channel-title').fill('Mi borrador sin guardar');save(second,'Segundo cambio remoto');page.wait_for_timeout(4000)
  assert page.locator('#channel-title').input_value()=='Mi borrador sin guardar'
  browser.close()
 print('OK: cross-device channel edits arrive without F5 and focused drafts are preserved')
if __name__=='__main__':run()
