from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':844});login_context(context)
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE_URL+'/account')
  page.locator('#fan-alias-panel').wait_for(state='visible');page.locator('#fan-alias').select_option('Loles');page.locator('#fan-alias-form button').click();page.wait_for_function("document.querySelector('#fan-alias-status').textContent.includes('Apodo guardado')")
  page.reload();page.wait_for_function("document.querySelector('#fan-alias').value==='Loles'")
  page.locator('#operations-admin > summary').click();page.locator('#maintenance-scope').select_option('all');page.locator('#maintenance-message').fill('Ol en mantenimiento. Estamos mejorando tu mejor momento.');page.locator('#maintenance-form button').click();page.wait_for_function("document.querySelector('#operations-status').textContent.includes('Estado guardado')")
  guest=browser.new_context();r=guest.request.get(BASE_URL+'/');assert r.status==503 and 'Ol en mantenimiento' in r.text();assert guest.request.get(BASE_URL+'/account').status==200
  page.locator('#maintenance-scope').select_option('off');page.locator('#maintenance-form button').click();page.wait_for_function("document.querySelector('#ol-maintenance-banner').hidden")
  assert guest.request.get(BASE_URL+'/').status==200
  page.goto(BASE_URL+'/live#video-setup');page.wait_for_function("document.activeElement.textContent==='Comprobar conexión de vídeo'");assert page.locator('.web-funds-note').inner_text().find('Fondos Web')>=0
  page.goto(BASE_URL+'/#mi-espacio');page.locator('#consent-decline').click();assert page.locator('#space-theme').count()==0
  page.locator('#ol-collection > summary').click();page.locator('.collection-sticker').first.wait_for()
  animation=page.locator('.collection-sticker').first.evaluate("e=>getComputedStyle(e,'::before').animationName");assert animation=='ol-horizon-drift'
  page.locator('.sticker-motion-control').click();assert page.evaluate("document.documentElement.dataset.stickerMotion==='off'")
  page.emulate_media(reduced_motion='reduce');assert page.locator('.collection-sticker').first.evaluate("e=>getComputedStyle(e,'::before').animationName")=='none'
  for width in [1440,768,390,320]:page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: real maintenance controls, administrator recovery, fan aliases, fixed palette, animated horizon and pause/reduced motion, four widths')
if __name__=='__main__':run()
