"""Reconciliation gives visible row feedback and remains retryable after every outcome."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();errors=[];held=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  member={'id':'sync-fixture','username':'rosas-fixture','role':'member','active':False,'account_activated':True,'access_until':None}
  page.route('**/api/admin/members',lambda r:r.fulfill(json={'members':[member],'payments':[]}))
  page.route('**/api/admin/payments/reconcile',lambda r:held.append(r))
  page.goto(BASE_URL+'/account');button=page.get_by_role('button',name='Sincronizar pago con Stripe',exact=True);button.wait_for()
  notice=page.locator('.client-payment-sync-status')
  for code,data,expected in [(200,{'confirmed':True},'Pago confirmado'),(200,{'pending':True},'Pago pendiente'),(200,{'confirmed':False,'pending':False},'No se encontró'),(503,{'error':'Stripe temporalmente no disponible'},'No se pudo sincronizar')]:
   button.click();page.wait_for_function("document.querySelector('.client-payment-sync-status').textContent.includes('Consultando')")
   assert page.get_by_role('button',name='Comprobando Stripe…',exact=True).is_disabled()
   page.wait_for_timeout(30);assert held
   request=held.pop(0);assert request.request.post_data_json=={'member_id':'sync-fixture'}
   request.fulfill(status=code,json=data)
   page.wait_for_function('(text)=>document.querySelector(".client-payment-sync-status").textContent.includes(text)',arg=expected)
   button=page.get_by_role('button',name='Sincronizar pago con Stripe',exact=True);button.wait_for();assert button.is_enabled()
   assert notice.is_visible();assert expected in notice.inner_text()
  assert not errors,errors;browser.close()
 print('OK: inline checking, confirmed/pending/no-order/error feedback survives table refresh; button always permits retry')
if __name__=='__main__':run()
