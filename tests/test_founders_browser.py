"""A real temporary free account claims a numbered lifetime place and edits only decoration."""
import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)));csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf']
  result=context.request.post(BASE_URL+'/api/account/register',headers={'X-CSRF-Token':csrf},data=__import__('registration_support').registration_data(context,{'username':'founder-'+secrets.token_hex(4),'password':secrets.token_urlsafe(20)}))
  assert result.ok,result.status
  page.goto(BASE_URL+'/live#founders');page.locator('#founder-claim:not([disabled])').wait_for()
  before=context.request.get(BASE_URL+'/api/live/founders').json()['claimed'];page.locator('#founder-claim').click();page.wait_for_function("document.querySelector('#founder-claim').textContent==='Confirmar mi plaza' && !document.querySelector('#human-answer').disabled");page.locator('#human-answer').fill('OL234')
  with page.expect_response('**/api/live/founders/claim') as claim:page.locator('#founder-claim').click()
  assert claim.value.status==200,claim.value.json().get('error')
  page.wait_for_url('**/live?welcome=founder#creator-panel')
  page.locator('#creator-panel').wait_for(state='visible');page.wait_for_function("!document.querySelector('#my-founder-signature').classList.contains('hidden')")
  account=context.request.get(BASE_URL+'/api/account/me').json()['user'];assert account['founder_active'] and account['streamer_active'];assert account['founder_number']==before+1
  assert page.locator('#start-camera').is_hidden()
  page.locator('#my-founder-signature > summary').click();page.locator('#founder-mode').select_option('letra');page.locator('#founder-letter').fill('A');page.locator('#founder-caption').fill('Buenas vibras');page.locator('#founder-signature-save').click()
  page.wait_for_function("document.querySelector('#founder-signature-status').textContent.includes('Insignia personalizada')")
  mine=context.request.get(BASE_URL+'/api/live/founders').json()['mine'];assert mine['number']==before+1 and mine['signature']['letter']=='A'
  page.locator('#founder-mode').select_option('sonido');page.locator('#founder-voice').select_option('aurora');page.locator('#founder-signature-save').click()
  page.wait_for_function("document.querySelector('#founder-signature-status').textContent.includes('Insignia personalizada')")
  audio=page.locator('#founder-signature-preview audio');assert not audio.evaluate('a=>!a.paused');audio.evaluate('a=>a.play()')
  page.wait_for_function("document.querySelector('#founder-signature-preview audio')?.currentTime>0")
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: free founder claim, real ordinal, creator entitlement, letter/tone decoration, no autoplay, native sound, 4 widths')

if __name__=='__main__':run()
