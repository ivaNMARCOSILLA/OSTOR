import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def post(context,path,data):
 csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf']
 return context.request.post(BASE_URL+path,data=data,headers={'X-CSRF-Token':csrf})

def register(context,name):
 r=post(context,'/api/account/register',{'username':name,'password':secrets.token_urlsafe(24)});assert r.status==201

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);errors=[]
  owner=browser.new_context(viewport={'width':390,'height':844});register(owner,'creator-'+secrets.token_hex(3))
  proof=owner.request.get(BASE_URL+'/api/account/human-check').json()
  assert post(owner,'/api/live/founders/claim',{'human_id':proof['id'],'human_answer':'OL234'}).ok
  channel=post(owner,'/api/streamers/me',{'title':'Canal de pruebas Ol','paypal_url':'https://paypal.me/CreatorOnly','owns_paypal':True}).json()['channel']['id']
  mod=browser.new_context();register(mod,'gref')
  admin=browser.new_context();login_context(admin)
  assert post(admin,'/api/admin/subscription-moderator',{'username':'Gref'}).ok
  assert mod.request.get(BASE_URL+'/api/channel-subscriptions/review').status==403
  controls=admin.new_page();controls.goto(BASE_URL+'/account')
  controls.locator('#subscription-review-panel > summary').click()
  assert not controls.locator('#moderator-review').is_checked()
  assert not controls.locator('#moderator-approve').is_checked()
  controls.locator('#moderator-approve').check()
  assert controls.locator('#moderator-review').is_checked()
  controls.locator('#moderator-permissions-form button[type=submit]').click()
  controls.wait_for_function("document.querySelector('#moderator-permissions-status').textContent.includes('Permisos guardados')")
  assert mod.request.get(BASE_URL+'/api/channel-subscriptions/review').status==200
  controls.locator('#moderator-revoke-all').click()
  controls.wait_for_function("document.querySelector('#moderator-permissions-status').textContent.includes('Todos los permisos retirados')")
  assert mod.request.get(BASE_URL+'/api/channel-subscriptions/review').status==403
  controls.locator('#moderator-approve').check()
  controls.locator('#moderator-permissions-form button[type=submit]').click()
  controls.wait_for_function("document.querySelector('#moderator-permissions-status').textContent.includes('Permisos guardados')")
  controls.close()
  creator=owner.new_page();creator.on('pageerror',lambda e:errors.append(str(e)));creator.goto(BASE_URL+'/live')
  creator.locator('#creator-subscriptions').wait_for(state='visible')
  creator.locator('#creator-offer-price').fill('4,50');creator.locator('#creator-offer-form button').click()
  creator.locator('#creator-offer-approve').wait_for(state='visible');creator.locator('#creator-offer-approve').click()
  creator.wait_for_function("document.querySelector('#creator-agreement-current').textContent.includes('Creador: aprobado')")
  manager=admin.new_page();manager.on('pageerror',lambda e:errors.append(str(e)));manager.goto(BASE_URL+'/account')
  manager.locator('#subscription-review-panel').wait_for(state='visible');manager.locator('#subscription-review-panel > summary').click()
  manager.locator('#subscription-review-list button').first.click()
  manager.wait_for_function("document.querySelector('#subscription-review-list').textContent.includes('Administración: aprobado')")
  moderator=mod.new_page();moderator.on('pageerror',lambda e:errors.append(str(e)));moderator.goto(BASE_URL+'/account')
  moderator.locator('#subscription-review-list button').first.wait_for()
  assert moderator.locator('#admin-panel').is_hidden();assert mod.request.get(BASE_URL+'/api/admin/members').status==403
  moderator.locator('#subscription-review-list button').first.click()
  moderator.wait_for_function("document.querySelector('#subscription-review-list').textContent.includes('Gref: aprobado')")
  offer=owner.request.get(BASE_URL+'/api/channel-subscriptions/'+channel).json()
  assert offer['agreement']['price_cents']==450 and not offer['payments_enabled'] and offer['subscriber_count']==0
  creator.locator('#creator-subscriptions > details').first.locator('summary').click()
  creator.locator('#creator-exclusive-form > label').first.locator('input').check()
  creator.locator('#creator-exclusive-form button').click()
  creator.wait_for_function("document.querySelector('#creator-offer-status').textContent.includes('Modos del canal guardados')")
  creator.evaluate("async id=>{const ui=await import('/assets/subscriptions.js?v=9.6.4');await ui.openSubscription(id)}",channel)
  assert creator.locator('#creator-subscription-dialog').is_visible()
  assert '4,50' in creator.locator('#creator-subscription-details').inner_text()
  assert creator.locator('#creator-subscription-details a').count()==0
  creator.locator('#creator-subscription-close').click()
  for width in [1440,768,390,320]:
   creator.set_viewport_size({'width':width,'height':1000});moderator.set_viewport_size({'width':width,'height':1000})
   assert creator.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   assert moderator.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  assert not errors,errors;browser.close()
 print('OK: real creator/admin/Gref agreement, explicit three-party approvals, restricted moderator, exclusive mode, honest zero subscribers, no early payment, four widths')

if __name__=='__main__':run()
