"""Cancel unaccepted invitations next to clients without removing accepted accounts."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':900});login_context(context)
  csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf']
  def invite(name):return context.request.post(BASE_URL+'/api/admin/invite',data={'username':name},headers={'X-CSRF-Token':csrf}).json()['path'].split('=',1)[1]
  invite('pending-browser-friend');accepted_token=invite('accepted-browser-friend')
  friend=browser.new_context();friend_csrf=friend.request.get(BASE_URL+'/api/account/me').json()['csrf']
  assert friend.request.post(BASE_URL+'/api/account/accept-invite',data={'token':accepted_token,'password':'accepted-browser-password-123'},headers={'X-CSRF-Token':friend_csrf}).status==200
  page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.goto(BASE_URL+'/account')
  page.wait_for_function("document.querySelector('#clients-invitation-count').textContent.includes('1 invitaciones no aceptadas')")
  assert 'accepted-browser-friend' in page.locator('#admin-members').inner_text()
  assert 'pending-browser-friend' not in page.locator('#admin-members').inner_text()
  page.locator('#show-unactivated-members').check();assert 'pending-browser-friend' in page.locator('#admin-members').inner_text()
  page.locator('#show-unactivated-members').uncheck();page.locator('#clients-clear-pending').click()
  page.wait_for_function("document.querySelector('#clients-invitation-status').textContent.includes('canceladas: 1')")
  assert context.request.get(BASE_URL+'/api/admin/invitations?summary=1').json()=={'total':1,'pending':0}
  assert friend.request.get(BASE_URL+'/api/account/me').json()['user']['complimentary']
  assert 'accepted-browser-friend' in page.locator('#admin-members').inner_text()
  page.locator('#clients-clear-history').click();page.wait_for_function("document.querySelector('#clients-invitation-status').textContent.includes('eliminados: 1')")
  assert context.request.get(BASE_URL+'/api/admin/invitations?summary=1').json()=={'total':0,'pending':0}
  page.locator('#clients-show-history').click();assert page.locator('#invitation-history').get_attribute('open') is not None
  for width in [320,390,768,1440]:page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: cleanup from clients, correct pending count, inactive placeholders separated, accepted accounts/access preserved, history shortcut and four widths')
if __name__=='__main__':run()
