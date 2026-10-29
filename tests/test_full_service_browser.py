"""Admin grants full service without billing or privilege elevation; own page reflects the concession."""
import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account');name='free-full-'+secrets.token_hex(3)
  page.locator('#register-form [name=username]').fill(name);page.locator('#register-form [name=password]').fill('full-service-browser-password-123')
  page.wait_for_function("document.querySelector('#registration-human-id').value.length===32");page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click();page.locator('#member-panel').wait_for()
  ac=b.new_context();login_context(ac);admin=ac.new_page();admin.goto(BASE_URL+'/account');admin.locator('#admin-member-search').fill(name)
  grant=admin.get_by_role('button',name='Dar acceso completo gratuito',exact=True);grant.wait_for();grant.click()
  admin.wait_for_function("document.querySelector('#account-status').textContent.includes('Acceso completo gratuito actualizado')")
  page.reload();page.wait_for_function("document.querySelector('#access-status').textContent.includes('Acceso completo gratuito')")
  assert 'sin pagos' in page.locator('#next-payment').inner_text()
  assert not page.locator('#pricing').is_visible();assert not page.locator('#admin-panel').is_visible()
  user=ctx.request.get(BASE_URL+'/api/account/me').json()['user'];assert user['full_service'] and user['streamer_active'] and user['role']=='member'
  assert ctx.request.get(BASE_URL+'/api/admin/members').status==403
  premiere=ctx.request.get(BASE_URL+'/api/status').json()['live_premiere']
  page.goto(BASE_URL+'/live#creator-panel');page.wait_for_function("!document.body.classList.contains('ol-live-premiere-only')")
  if premiere:assert page.locator('body').evaluate("e=>e.classList.contains('ol-private-preview')")
  page.locator('#creator-panel').wait_for(state='visible');assert page.url.endswith('#creator-panel')
  if premiere:
   page.wait_for_function("document.querySelector('.premiere-badge').textContent==='PRUEBA PRIVADA'")
   assert page.locator('#ol-live-premiere a').get_attribute('href')=='#creator-panel'
  assert not errors,errors;b.close()
 print('OK: full free service grant in admin UI, own free access message, no billing or admin permissions')
if __name__=='__main__':run()
