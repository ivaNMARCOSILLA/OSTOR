from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
  page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda r:r.fulfill(json=[]))
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
  menu=page.locator('#mobile-menu');nav=page.locator('#mobile-nav')
  menu.click();assert menu.get_attribute('aria-expanded')=='true'
  assert nav.locator('.menu-group-title').all_text_contents()==['Música','Ol Live','Tu espacio']
  assert nav.locator('a[href="/account"]').count()==1
  assert nav.locator('a[href="/live#live-catalogue"]').count()==1
  assert nav.locator('a[href="/live#creator-panel"]').count()==1
  # Open navigation stays usable even over the playing bar, without stopping audio.
  page.evaluate("document.querySelector('#player').classList.remove('hidden')")
  nav.locator('a[href="#ol-collection"]').click()
  assert nav.is_hidden() and page.locator('#ol-collection').get_attribute('open') is not None
  page.evaluate('scrollTo(0,0)');menu.click();page.keyboard.press('Escape')
  assert nav.is_hidden() and menu.evaluate('e=>e===document.activeElement')
  menu.click();nav.locator('[data-view="favorites"]').click()
  assert nav.is_hidden();assert page.locator('#main-nav [data-view="favorites"]').get_attribute('aria-pressed')=='true'
  page.evaluate('scrollTo(0,0)');menu.click();nav.locator('#cookie-settings').click()
  assert page.locator('#consent-dialog').is_visible() and nav.is_hidden()
  page.locator('#consent-decline').click()
  page.evaluate('scrollTo(0,0)');menu.click();page.locator('#music-free-banner strong').click()
  assert nav.is_hidden()
  for width in [320,390,768]:
   page.set_viewport_size({'width':width,'height':844});page.evaluate('scrollTo(0,0)');menu.click()
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   for item in nav.locator('a,button').all():
    box=item.bounding_box();assert box['height']>=44 and box['width']>100
   if width==390:page.screenshot(path='/tmp/ol-home-menu-mobile.png')
   page.keyboard.press('Escape')
  page.set_viewport_size({'width':1440,'height':1000});assert menu.is_hidden()
  assert page.locator('#main-nav .menu-group-title').all_text_contents()==['Música','Ol Live','Tu espacio']
  page.locator('#main-nav [data-cookie-preferences]').click();assert page.locator('#consent-dialog').is_visible()
  assert not errors,errors;browser.close()
 print('OK: grouped mobile/desktop menu, working destinations, player overlap, account, cookies, Escape, outside click, touch targets and four widths')

if __name__=='__main__':run()
