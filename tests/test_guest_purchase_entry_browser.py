"""Guests can reach registration from annual pricing without a dead purchase button."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account#pricing')
  page.wait_for_function("document.querySelector('#trial-start').textContent.includes('Crear cuenta o entrar')")
  button=page.locator('#trial-start');assert button.is_enabled()
  button.click()
  page.wait_for_function("document.activeElement===document.querySelector('#register-form [name=username]')")
  assert 'Crea tu cuenta gratis' in page.locator('#login-feedback').inner_text()
  assert not errors,errors
  browser.close()
 print('OK: annual purchase guest button opens registration and focuses username')
if __name__=='__main__':run()
