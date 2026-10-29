"""Only administration approves community roles; members contact the owner by Gmail."""
import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE_URL+'/account');name='collaborator-'+secrets.token_hex(3)
  page.locator('#register-form [name=username]').fill(name);page.locator('#register-form [name=password]').fill('community-browser-password-123')
  page.wait_for_function("document.querySelector('#registration-human-id').value.length===32");page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click();page.locator('#member-panel').wait_for()
  assert 'Activo' in page.locator('#community-role-status').inner_text()
  assert page.locator('a[href^="mailto:normalesoutro@gmail.com"]').is_visible()
  adminctx=b.new_context();login_context(adminctx);admin=adminctx.new_page();admin.goto(BASE_URL+'/account');admin.locator('#admin-member-search').fill(name)
  label=admin.get_by_label('Rol de comunidad · '+name);label.wait_for();label.select_option('docente')
  row=label.locator('xpath=ancestor::tr');row.get_by_role('button',name='Aprobar rol',exact=True).click();admin.wait_for_function("document.querySelector('#account-status').textContent.includes('Rol de comunidad aprobado')")
  page.reload();page.wait_for_function("document.querySelector('#community-role-status').textContent.includes('Docente')")
  assert not page.locator('#admin-panel').is_visible();assert 'gratuitas' in page.locator('#access-status').inner_text()
  assert not errors,errors;b.close()
 print('OK: Gmail collaboration contact, admin role approval, own role visible without admin access')
if __name__=='__main__':run()
