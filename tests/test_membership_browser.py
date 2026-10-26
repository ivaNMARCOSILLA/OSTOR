"""Free registration, premium gate, private invitations and admin layout."""
import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context();page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE_URL+'/account')
  page.locator('#credentials > details > summary').click();name='free-'+secrets.token_hex(4);password=secrets.token_urlsafe(20)
  page.locator('#register-form [name=username]').fill(name);page.locator('#register-form [name=password]').fill(password);page.locator('#register-form button').click();page.locator('#member-panel').wait_for(state='visible')
  assert page.locator('#enter-maggy').is_visible();assert 'gratuita' in page.locator('#access-status').inner_text()
  assert context.request.get(BASE_URL+'/api/rewards').status==200
  assert context.request.get(BASE_URL+'/api/streamers').status==402
  assert page.locator('#pay-monthly').get_attribute('href') is None
  admin_context=browser.new_context();login_context(admin_context);admin=admin_context.new_page();admin.goto(BASE_URL+'/account');admin.locator('#admin-panel').wait_for()
  admin.locator('#create-invite [name=username]').fill('invited-'+secrets.token_hex(4));admin.locator('#create-invite button').click();link=admin.locator('#invite-result a');link.wait_for();path=link.get_attribute('href')
  invited_context=browser.new_context();invited=invited_context.new_page();invited.goto(BASE_URL+path);invited.locator('#invite-form [name=password]').fill(secrets.token_urlsafe(20));invited.locator('#invite-form button').click();invited.locator('#member-panel').wait_for()
  assert invited.locator('#enter-maggy').is_visible();assert 'Ol Live gratuito' in invited.locator('#access-status').inner_text();assert not invited.locator('#pricing').is_visible();assert not invited.locator('#admin-panel').is_visible()
  for width in [1440,768,390,320]:
   admin.set_viewport_size({'width':width,'height':900});assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  admin.set_viewport_size({'width':1440,'height':1000});admin.locator('#invite-result').evaluate("node=>node.textContent='Invitación gratuita de Ol Live creada. Enlace privado oculto en esta captura.'");admin.screenshot(path='docs/maggy-admin.png',full_page=True)
  assert not errors,errors;browser.close()
 print('OK: free music/account collection, premium-only Ol Live, no premature billing, free friend invitations, 4 widths')

if __name__=='__main__':run()
