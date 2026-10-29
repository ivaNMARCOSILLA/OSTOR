"""Live discovery links reach a visible catalogue and each action keeps its intent."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  visitor=browser.new_page(viewport={'width':390,'height':844});visitor.goto(BASE_URL+'/streamers')
  visitor.locator('.hero-actions a[href="#live-catalogue"]').click()
  assert visitor.locator('#live-catalogue').is_visible()
  assert visitor.evaluate('document.activeElement.id')=='catalogue-title'
  assert 'Ol Livis' in visitor.locator('#catalogue-status').inner_text() or 'emisiones' in visitor.locator('#catalogue-status').inner_text()
  visitor.locator('.header-live').click()
  assert visitor.locator('#stream-access').is_visible()
  assert 'next=%2Flive%23stream-studio' in visitor.locator('#stream-access a').get_attribute('href')
  context=browser.new_context(viewport={'width':1440,'height':960});login_context(context)
  page=context.new_page();token_calls=[];errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  channels=[{'id':'a'*32,'title':'Piano en vivo','username':'Pianista','bio':'Sesión instrumental','paypal_url':''},{'id':'b'*32,'title':'Conversación','username':'Lucía','bio':'Ideas compartidas','paypal_url':''}]
  payload={'video_ready':True,'streamer_active':False,'channels':channels,'mine':None,'streamer_sales_available':False,'setup_checks':None}
  page.route('**/api/streamers',lambda route:route.fulfill(json=payload))
  def token(route):
   token_calls.append(route.request.post_data_json)
   route.fulfill(status=503,json={'error':'Conexión de vídeo no disponible en esta prueba.'})
  page.route('**/api/streamers/*/token',token)
  page.goto(BASE_URL+'/streamers#live-catalogue')
  page.locator('.live-channel').first.wait_for()
  assert page.locator('.live-channel').count()==2
  page.locator('#channel-filter').fill('pianista');assert page.locator('.live-channel').count()==1
  page.locator('#channel-filter').fill('ausente');assert 'coincidan' in page.locator('#live-empty').inner_text()
  page.locator('#channel-filter').fill('')
  page.locator('.live-channel button').first.click()
  page.wait_for_function("document.querySelector('#stream-status').textContent.includes('Conexión de vídeo no disponible')")
  assert token_calls==[{'publish':False}]
  page.locator('.header-live').click();assert page.locator('#creator-access').is_visible()
  assert 'cobros siguen bloqueados' in page.locator('#creator-access-message').inner_text()
  payload['streamer_active']=True
  page.locator('#refresh-channels').click();page.wait_for_function("!document.querySelector('#refresh-channels').disabled")
  page.locator('.header-live').click();assert page.evaluate('document.activeElement.id')=='creator-form-title'
  payload['channels']=[]
  page.locator('#refresh-channels').click();page.wait_for_function("document.querySelectorAll('.live-channel').length===0")
  assert 'Nadie está emitiendo' in page.locator('#live-empty').inner_text()
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors
  browser.close()
 print('OK: live catalogue destinations, guest access, filter, watch-only token, creator routing, real empty state, 4 widths')

if __name__=='__main__':run()
