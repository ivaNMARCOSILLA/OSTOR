import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account')
  assert page.locator('#register-form').is_visible()
  page.locator('#registration-submit').click()
  assert 'usuario' in page.locator('#registration-feedback').inner_text().lower()
  name='signup-'+secrets.token_hex(4)
  page.locator('#register-form [name=username]').fill(name)
  page.locator('#register-form [name=password]').fill('short')
  page.locator('#registration-submit').click()
  assert '12' in page.locator('#registration-feedback').inner_text()
  page.locator('#register-form [name=password]').fill(secrets.token_urlsafe(20))
  page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
  page.locator('#registration-human-answer').fill('WRONG');page.locator('#registration-submit').click()
  page.wait_for_function("document.querySelector('#registration-feedback').textContent.includes('comprobación humana')")
  page.wait_for_function("document.querySelector('#registration-human-answer').value===''")
  page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click()
  page.wait_for_url('**/account?registered=1')
  page.locator('#member-panel').wait_for(state='visible')
  assert 'Cuenta creada' in page.locator('#account-status').inner_text()
  assert context.request.get(BASE_URL+'/api/account/me').json()['user']['username']==name
  assert context.request.get(BASE_URL+'/api/rewards').status==200
  assert context.request.get(BASE_URL+'/api/admin/members').status==403
  assert page.locator('#credentials').is_hidden()
  page.reload();page.locator('#member-panel').wait_for(state='visible')
  assert not errors,errors
  for width in [1440,768,390,320]:
   guest=browser.new_context(viewport={'width':width,'height':1000});view=guest.new_page();view.goto(BASE_URL+'/account')
   assert view.locator('#register-form').is_visible();assert view.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   if width==390:view.screenshot(path='/tmp/ol-registration-mobile.png',full_page=True)
   guest.close()
  browser.close()
 print('OK: visible self-registration, immediate field errors, real human challenge, retry after wrong code, immediate authenticated access without approval, persistence, four widths')

if __name__=='__main__':run()
