from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  visitor=browser.new_context();guest=visitor.new_page();errors=[]
  guest.on('pageerror',lambda e:errors.append(str(e)))
  guest.goto(BASE_URL+'/live')
  assert guest.locator('[data-online-counter]').is_hidden()
  assert visitor.request.get(BASE_URL+'/api/admin/statistics').status==403
  context=browser.new_context();login_context(context);page=context.new_page()
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account')
  page.locator('#statistics-cards article').first.wait_for()
  assert page.locator('#statistics-cards article').count()>=18
  assert page.locator('#statistics-days tr').count()==7
  page.locator('#refresh-statistics').click()
  page.wait_for_function("!document.querySelector('#refresh-statistics').disabled")
  assert 'Actualizado:' in page.locator('#statistics-status').inner_text()
  data=context.request.get(BASE_URL+'/api/admin/statistics').json()
  assert data['online']['members']>=1 and data['online']['guests']>=1
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.screenshot(path='/tmp/ol-statistics-mobile.png',full_page=True)
  assert not errors,errors;browser.close()
 print('OK: hidden public counter, private real admin statistics, manual refresh, seven days, four widths')

if __name__=='__main__':run()
