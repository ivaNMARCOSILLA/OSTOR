"""Creator Stripe linking remains usable when unrelated status checks fail."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL, login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context();login_context(context);page=context.new_page()
  page.route('**/api/status',lambda r:r.fulfill(status=503,json={'error':'Temporal'}))
  page.route('**/api/payments/status',lambda r:r.fulfill(json={'connect_available':True,'creator_connected':False}))
  page.route('**/api/payments/connect',lambda r:r.fulfill(status=503,json={'error':'Stripe temporalmente no disponible'}))
  page.goto(BASE_URL+'/live#creator-subscriptions')
  button=page.locator('#creator-connect-stripe')
  page.wait_for_function("document.querySelector('#creator-processor-status').textContent.includes('Conecta tu propia cuenta')")
  assert button.is_enabled()
  page.evaluate("document.querySelector('#creator-connect-stripe').click()")
  page.wait_for_function("document.querySelector('#creator-connect-stripe').textContent.includes('Reintentar')")
  assert button.is_enabled()
  assert 'Stripe temporalmente no disponible' in page.locator('#creator-processor-status').inner_text()
  browser.close()
 print('OK: Stripe button independent of failed diagnostics; failed connection permits retry')
if __name__=='__main__':run()
