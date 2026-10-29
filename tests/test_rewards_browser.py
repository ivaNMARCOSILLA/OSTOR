from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();login_context(context);page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
  page.add_init_script("window.__phrases=[];window.speechSynthesis.speak=u=>window.__phrases.push(u.text);window.speechSynthesis.cancel=()=>{}")
  page.goto(BASE_URL+'/#ol-collection')
  page.locator('#consent-decline').click()
  page.locator('.collection-sticker').first.wait_for()
  assert page.locator('#ol-collection').get_attribute('open') is not None
  assert page.locator('.collection-sticker').count()==min(24,context.request.get(BASE_URL+'/api/rewards').json()['total'])
  assert page.locator('.collection-sticker.unlocked').count()==1
  assert page.locator('#reward-points').inner_text()=='0'
  assert len(page.evaluate('window.OlCollection.stickers'))==1
  assert not page.evaluate("performance.getEntriesByType('resource').some(e=>e.name.endsWith('/sound.wav'))")
  assert page.evaluate('window.__phrases.length')==0
  page.locator('.sticker-sound-button').first.click()
  page.wait_for_function('window.__phrases.length===1')
  assert len(page.evaluate('window.__phrases[0]'))>5
  assert 'Frase del sticker' in page.locator('.sticker-sound-button').first.get_attribute('aria-label')
  page.locator('#reward-next-page').click()
  page.wait_for_function("document.querySelector('#reward-page').textContent.includes('Página 2')")
  assert page.locator('.collection-sticker').count()==24
  page.locator('#reward-search').fill('1000')
  page.wait_for_function("document.querySelectorAll('.collection-sticker').length===1 && document.querySelector('.collection-sticker strong').textContent.includes('1000')")
  page.locator('#reward-search').fill('')
  page.wait_for_function("document.querySelectorAll('.collection-sticker').length===24")
  page.locator('#reward-owned').check()
  page.wait_for_function("document.querySelectorAll('.collection-sticker').length===1")
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.goto(BASE_URL+'/streamers#ol-collection');page.locator('.collection-sticker').first.wait_for()
  assert page.locator('#comment-stickers button').count()==1
  assert page.locator('#comment-stickers button').first.get_attribute('aria-label')=='Enviar sticker Creador de electronicama'
  assert not errors,errors
  browser.close()
 print('OK: 1000-sticker album, pagination, numeric search, owned filter, manual sound, chat picker, 4 widths')

if __name__=='__main__':run()
