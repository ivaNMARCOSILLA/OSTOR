"""Adult declaration blocks the player until accepted; cancellation stays outside."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx)
  csrf=ctx.request.get(BASE_URL+'/api/account/me').json()['csrf']
  ctx.request.post(BASE_URL+'/api/streamers/me',data={'title':'Canal adulto','adult_content':True,'adult_rules_accepted':True},headers={'X-CSRF-Token':csrf})
  channel=ctx.request.get(BASE_URL+'/api/streamers').json()['mine'];page=ctx.new_page();page.add_init_script(SDK)
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':channel,'channels':[channel]}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/assets/community.js*',lambda r:r.fulfill(content_type='text/javascript',body='export class StreamCommunity {start(){} stop(){} syncMicrophone(){}}'))
  page.goto(BASE_URL+'/live');page.get_by_role('button',name='Ver vídeo en directo de Canal adulto',exact=True).click();page.locator('#adult-age-dialog').wait_for(state='visible')
  assert '21' in page.locator('#adult-age-explanation').inner_text();assert not page.locator('#live-stage').is_visible()
  page.locator('#adult-age-cancel').click();assert not page.locator('#live-stage').is_visible()
  page.get_by_role('button',name='Ver vídeo en directo de Canal adulto',exact=True).click();page.locator('#adult-birth-date').fill('1990-01-01');page.locator('#adult-accept-rules').check();page.get_by_role('button',name='Confirmar edad y continuar').click()
  page.locator('#live-stage').wait_for(state='visible');assert page.locator('#adult-birth-date').input_value()==''
  browser.close()
 print('OK: adult gate, conservative 21-year minimum, cancellation and declaration before player')
if __name__=='__main__':run()
