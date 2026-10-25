from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();login_context(context);page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
  page.goto(BASE_URL+'/#ol-collection')
  page.locator('.collection-sticker').first.wait_for()
  assert page.locator('#ol-collection').get_attribute('open') is not None
  assert page.locator('.collection-sticker').count()==context.request.get(BASE_URL+'/api/rewards').json()['total']
  assert page.locator('.collection-sticker.unlocked').count()==1
  assert page.locator('#reward-points').inner_text()=='0'
  assert len(page.evaluate('window.OlCollection.stickers'))==1
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.goto(BASE_URL+'/streamers#ol-collection');page.locator('.collection-sticker').first.wait_for()
  assert page.locator('#comment-stickers button').count()==1
  assert page.locator('#comment-stickers button').first.get_attribute('aria-label')=='Enviar sticker Creador de Ol'
  assert not errors,errors
  browser.close()
 print('OK: account album, 12 stickers, starter unlocked, locked rewards, chat picker, 4 widths')

if __name__=='__main__':run()
