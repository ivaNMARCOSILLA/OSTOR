"""An administrator can close test accounts without losing their private history."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context


def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  admin=browser.new_context(viewport={'width':390,'height':900});owner=login_context(admin)
  users={};contexts={};errors=[]
  # Register ordinary accounts through the same form and human check as visitors.
  for name in ['amigo','prueba','prueba2']:
   context=browser.new_context();view=context.new_page();view.on('pageerror',lambda error:errors.append(str(error)))
   view.goto(BASE_URL+'/account');view.locator('#register-form [name=username]').fill(name)
   if name=='amigo':view.locator('#register-form [name=nickname]').fill('admin')
   view.locator('#register-form [name=password]').fill('account-archive-browser-password-123')
   view.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
   view.locator('#registration-human-answer').fill('OL234');view.locator('#registration-submit').click()
   view.wait_for_url('**/account?registered=1');view.locator('#member-panel').wait_for(state='visible')
   users[name]=context.request.get(BASE_URL+'/api/account/me').json()['user'];contexts[name]=context
   assert users[name]['role']=='member'
  page=admin.new_page();page.on('pageerror',lambda error:errors.append(str(error)));page.on('dialog',lambda dialog:dialog.accept())
  page.goto(BASE_URL+'/account');page.locator('#admin-members [data-member-archive]').first.wait_for()
  def row(name):return page.locator('#admin-members tr[data-member-id="'+users[name]['id']+'"]')
  assert 'amigo · admin' in row('amigo').inner_text()
  assert row('amigo').get_by_role('button',name='Dar de baja cuenta',exact=True).count()==1
  assert page.locator('#admin-members tr[data-member-id="'+owner['id']+'"] [data-member-archive]').count()==0
  assert '3 clientes' in page.locator('#admin-counters').inner_text()

  # Failure feedback stays beside the table and leaves the account operational.
  page.route('**/api/admin/members/archive',lambda route:route.fulfill(status=503,json={'error':'No se pudo completar la baja de prueba.'}),times=1)
  row('prueba').get_by_role('button',name='Dar de baja cuenta',exact=True).click()
  page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes('No se pudo completar la baja de prueba')")
  assert row('prueba').get_by_role('button',name='Dar de baja cuenta',exact=True).is_enabled()
  assert contexts['prueba'].request.get(BASE_URL+'/api/account/me').json()['user']['id']==users['prueba']['id']
  assert page.locator('#clients-account-status').get_attribute('role')=='status'

  # Repeated events while saving cannot send a second close request.
  held=[];page.route('**/api/admin/members/archive',lambda route:held.append(route),times=1)
  row('prueba').get_by_role('button',name='Dar de baja cuenta',exact=True).click()
  page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes('Actualizando la cuenta de prueba')")
  assert len(held)==1 and row('prueba').locator('[data-member-archive]').is_disabled()
  row('prueba').locator('[data-member-archive]').dispatch_event('click')
  assert len(held)==1
  response=held[0].fetch();assert response.ok;held[0].fulfill(response=response)
  page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes('Cuenta prueba dada de baja')")
  assert row('prueba').count()==0
  assert contexts['prueba'].request.get(BASE_URL+'/api/account/me').json()['user'] is None
  assert '2 clientes' in page.locator('#admin-counters').inner_text()

  # A late response from the optional archived list cannot restore hidden rows.
  stale=[];page.route('**/api/admin/members?archived=1',lambda route:stale.append(route),times=1)
  page.locator('#show-archived-members').check();page.wait_for_timeout(50);assert len(stale)==1
  with page.expect_response(lambda response:'/api/admin/members' in response.url and '?' not in response.url):
   page.locator('#show-archived-members').uncheck()
  stale_response=stale[0].fetch();stale[0].fulfill(response=stale_response)
  page.wait_for_timeout(100);assert row('prueba').count()==0

  page.locator('#show-archived-members').check();row('prueba').get_by_role('button',name='Restaurar cuenta',exact=True).wait_for()
  assert 'Cuenta dada de baja' in row('prueba').inner_text()
  assert row('prueba').get_by_role('button').count()==2
  assert row('prueba').get_by_role('button',name='Eliminar cuenta sin pagos',exact=True).count()==1
  assert row('prueba').locator('select').count()==0
  assert '2 clientes' in page.locator('#admin-counters').inner_text()
  row('prueba').get_by_role('button',name='Restaurar cuenta',exact=True).click()
  page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes('Cuenta prueba restaurada')")
  assert row('prueba').get_by_role('button',name='Dar de baja cuenta',exact=True).count()==1
  # Restoration never revives the old session; the account signs in again.
  assert contexts['prueba'].request.get(BASE_URL+'/api/account/me').json()['user'] is None
  assert '3 clientes' in page.locator('#admin-counters').inner_text()

  for name in ['amigo','prueba','prueba2']:
   row(name).get_by_role('button',name='Dar de baja cuenta',exact=True).click()
   page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes("+repr('Cuenta '+name+' dada de baja')+")")
  page.locator('#show-archived-members').uncheck()
  page.wait_for_function("document.querySelectorAll('#admin-members [data-member-archive]').length===0")
  assert '0 clientes' in page.locator('#admin-counters').inner_text()
  page.reload();page.locator('#admin-members tr').first.wait_for()
  assert page.locator('#admin-members [data-member-archive]').count()==0
  assert page.locator('#admin-members [data-member-delete]').count()==0
  page.locator('#show-archived-members').check();row('amigo').get_by_role('button',name='Eliminar cuenta sin pagos',exact=True).wait_for()
  # A blocked deletion retains the account and makes the reason visible.
  page.route('**/api/admin/members/delete',lambda route:route.fulfill(status=409,json={'error':'Existen registros que deben conservarse.'}),times=1)
  row('amigo').get_by_role('button',name='Eliminar cuenta sin pagos',exact=True).click()
  page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes('Existen registros que deben conservarse')")
  assert row('amigo').get_by_role('button',name='Eliminar cuenta sin pagos',exact=True).is_enabled()
  # Physical deletion removes the three accounts even from the archived API list.
  for name in ['amigo','prueba','prueba2']:
   row(name).get_by_role('button',name='Eliminar cuenta sin pagos',exact=True).click()
   page.wait_for_function("document.querySelector('#clients-account-status').textContent.includes("+repr('Cuenta '+name+' eliminada definitivamente')+")")
   assert row(name).count()==0
   remaining=admin.request.get(BASE_URL+'/api/admin/members?archived=1').json()['members']
   assert all(member['id']!=users[name]['id'] for member in remaining)
   csrf=contexts[name].request.get(BASE_URL+'/api/account/me').json()['csrf']
   login=contexts[name].request.post(BASE_URL+'/api/account/login',data={'username':name,'password':'account-archive-browser-password-123'},headers={'X-CSRF-Token':csrf})
   assert login.status==401
   assert contexts[name].request.get(BASE_URL+'/api/account/me').json()['user'] is None
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: real registrations, nickname is not authority, archive failure feedback, one in-flight mutation, stale list ignored, sessions closed, restoration, protected deletion errors, physical deletion and four widths')


if __name__=='__main__':run()
