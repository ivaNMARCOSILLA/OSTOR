from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();login_context(context);page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account');page.locator('#admin-panel').wait_for(state='visible')
  page.locator('#sticker-manager summary').click();page.locator('#admin-sticker-list article').first.wait_for()
  initial=page.locator('#admin-sticker-list article').count();assert initial>=12
  page.locator('#sticker-design-target').select_option('hello')
  assert page.locator('#sticker-design-points').is_disabled()
  assert page.locator('#sticker-design-points').input_value()=='0'
  page.locator('#sticker-design-target').select_option('')
  page.locator('#sticker-design-name').fill('Mi diseño de prueba')
  page.locator('#sticker-design-points').fill('10')
  page.locator('#sticker-design-file').set_input_files(str(Path(__file__).resolve().parents[1]/'assets/stickers/creator.webp'))
  page.locator('#sticker-design-preview').wait_for(state='visible')
  page.locator('#sticker-design-form button').click()
  page.wait_for_function("document.querySelector('#sticker-design-status').textContent.includes('Diseño guardado')")
  assert page.locator('#admin-sticker-list article').count()==initial+1
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: creator free/pinned, real file upload/preview/resize/save, persistent custom album, 4 widths')

if __name__=='__main__':run()
