"""Automatic locale, manual persistence and user-content safety in actual DOM."""
from playwright.sync_api import sync_playwright,expect
from browser_support import BASE_URL

HTML='''<!doctype html><html lang="es"><head><meta charset="utf-8"><link rel="stylesheet" href="/assets/site-language.css"><script defer src="/assets/site-language.js"></script></head><body><header class="topbar"></header><main><h1>Mi cuenta</h1><button id="action">Crear cuenta</button><input id="search" placeholder="Buscar música"><div class="track-title">Mi cuenta</div><blockquote lang="ca">AVUI TORNAREM AL CEL</blockquote><div id="live-comments"><p>Crear cuenta</p></div><div id="dynamic"></div><p id="clicks">0</p></main><footer></footer><script>document.getElementById('action').addEventListener('click',()=>document.getElementById('clicks').textContent=Number(document.getElementById('clicks').textContent)+1)</script></body></html>'''

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context(locale='en-US');page=ctx.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
  page.route('**/language-fixture',lambda r:r.fulfill(content_type='text/html',body=HTML));page.route('**/api/locale',lambda r:r.fulfill(json={'language':'fr','source':'country','supported':['es','ca','en','fr','pt','de','it']}))
  page.goto(BASE_URL+'/language-fixture');expect(page.locator('html')).to_have_attribute('lang','fr');expect(page.locator('h1')).to_have_text('Mon compte');expect(page.locator('#action')).to_have_text('Créer un compte')
  page.locator('[data-site-language]').select_option('en');expect(page.locator('h1')).to_have_text('My account');expect(page.locator('#search')).to_have_attribute('placeholder','Search music');page.locator('#action').click();expect(page.locator('#clicks')).to_have_text('1')
  expect(page.locator('.track-title')).to_have_text('Mi cuenta');expect(page.locator('#live-comments')).to_have_text('Crear cuenta');expect(page.locator('blockquote')).to_have_text('AVUI TORNAREM AL CEL')
  page.evaluate("document.querySelector('#dynamic').textContent='Activar sonido'");expect(page.locator('#dynamic')).to_have_text('Enable sound')
  page.reload();expect(page.locator('html')).to_have_attribute('lang','en');expect(page.locator('h1')).to_have_text('My account')
  page.locator('[data-site-language]').select_option('ca');expect(page.locator('h1')).to_have_text('El meu compte');page.locator('[data-site-language]').select_option('es');expect(page.locator('h1')).to_have_text('Mi cuenta');expect(page.locator('#action')).to_have_text('Crear cuenta')
  for width in [320,390,1440]:page.set_viewport_size({'width':width,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  page.locator('[data-site-language]').select_option('auto');expect(page.locator('html')).to_have_attribute('lang','fr');assert page.evaluate("localStorage.getItem('electronicama_language')") is None
  assert not errors,errors;browser.close()
 print('OK: trusted automatic locale fixture, saved en/ca/es, live labels and attributes, controls retained, user content preserved and three widths')
if __name__=='__main__':run()
