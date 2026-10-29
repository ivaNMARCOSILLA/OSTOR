"""Returning from a confirmed Stripe link resumes the saved draft once, without inventing approvals."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();login_context(ctx);page=ctx.new_page();calls=[];errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  def dashboard(r):r.fulfill(json={'stripe_connected':True,'channel':{'id':'a'*32,'title':'Canal de prueba','subscriber_count':0,'gross_confirmed_cents':0},'draft':None if calls else {'price_cents':350,'benefits':['badge']},'latest':None,'settings':{'subscriber_chat':0,'exclusive_live':0},'benefits':{'badge':'Insignia'},'current_price_cents':350})
  page.route('**/api/channel-subscriptions/creator',dashboard)
  def propose(r):calls.append(r.request.post_data_json);r.fulfill(json={'ok':True,'draft':False,'agreement_id':'fixture','published':False})
  page.route('**/api/channel-subscriptions/propose',propose)
  page.goto(BASE_URL+'/live?stripe=connected#creator-subscriptions')
  page.wait_for_function("document.querySelector('#creator-offer-status').textContent.includes('recuperada automáticamente')")
  assert calls==[{'price_cents':350,'period':'month','benefits':['badge']}]
  assert page.locator('#channel-subscription-settings').evaluate('(e)=>e.open')
  assert 'stripe=connected' not in page.url
  page.reload();page.wait_for_timeout(300);assert len(calls)==1
  assert not errors,errors;b.close()
 print('OK: connected creator resumes draft once; no automatic approval or charge; return flag removed')
if __name__=='__main__':run()
