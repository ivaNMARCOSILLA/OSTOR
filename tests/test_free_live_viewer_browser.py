"""Free logged-in viewers can connect and refresh without gaining studio access."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.add_init_script(SDK)
  def free_account(route):
   response=route.fetch();data=response.json();data['user'].update(active=False,streamer_active=False,role='member',full_service=False,live_annual=False);route.fulfill(response=response,json=data)
  page.route('**/api/account/me',free_account)
  channel={'id':'d'*32,'title':'Directo público','username':'Creador','category':'musica','bio':'Bienvenidos'}
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':False,'mine':None,'channels':[channel],'setup_checks':None}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True}))
  page.route('**/assets/community.js*',lambda r:r.fulfill(content_type='text/javascript',body='export class StreamCommunity {start(){} stop(){} syncMicrophone(){}}'))
  page.goto(BASE_URL+'/live');page.get_by_role('button',name='Ver vídeo en directo de Directo público',exact=True).click();page.locator('#live-stage').wait_for(state='visible')
  assert not page.locator('#creator-panel').is_visible()
  assert not page.evaluate('window.MaggySession.premium')
  page.get_by_role('button',name='Actualizar canales',exact=True).click();page.wait_for_timeout(500)
  assert page.locator('#live-stage').is_visible()
  browser.close()
 print('OK: free account watches and refreshes a public stream without creator access')
if __name__=='__main__':run()
