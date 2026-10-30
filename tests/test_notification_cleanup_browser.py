"""Clear old notices except Flores, while future notifications remain normal."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL, login_context


def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  admin=browser.new_context(viewport={'width':390,'height':900});login_context(admin)
  contexts=[]
  def register(name,nickname=''):
   context=browser.new_context();contexts.append(context);page=context.new_page();page.goto(BASE_URL+'/account')
   page.locator('#register-form [name=username]').fill(name)
   if nickname:page.locator('#register-form [name=nickname]').fill(nickname)
   page.locator('#register-form [name=password]').fill('notification-browser-password-123')
   page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
   page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click()
   page.wait_for_url('**/account?registered=1');page.locator('#member-panel').wait_for()
   return context
  flores=register('rosas','Flores');other=register('other-account')
  page=admin.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.on('dialog',lambda dialog:dialog.accept())
  page.goto(BASE_URL+'/account');page.locator('#admin-panel').wait_for();page.locator('#notification-history summary').click()
  page.wait_for_function("document.querySelector('#admin-notifications').children.length===2")
  page.locator('#clear-notifications-except-flores').click()
  page.wait_for_function("document.querySelector('#notification-clear-status').textContent.includes('1 avisos eliminados')")
  page.wait_for_function("document.querySelector('#admin-notifications').children.length===1")
  notices=admin.request.get(BASE_URL+'/api/admin/notifications').json()
  assert notices['total']==notices['pending']==1
  assert all(item['status']=='pending' for item in notices['notifications'])
  assert other.request.get(BASE_URL+'/api/account/me').json()['user']['username']=='other-account'
  assert flores.request.get(BASE_URL+'/api/account/me').json()['user']['username']=='rosas'
  register('future-account')
  notices=admin.request.get(BASE_URL+'/api/admin/notifications').json()
  assert notices['total']==notices['pending']==2
  assert all(item['status']=='pending' for item in notices['notifications'])
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: real registrations, historic notices deleted except Flores, accounts retained, future notices remain pending normally, four widths')


if __name__=='__main__':run()
