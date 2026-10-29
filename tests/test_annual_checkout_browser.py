"""Real local account and signed payment flow; only the external Stripe boundary is simulated."""
import hashlib,hmac,json,os,secrets,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  ctx=browser.new_context(viewport={'width':390,'height':844});page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  email='annual-'+secrets.token_hex(5)+'@example.test'
  mail_path=Path(os.environ['OL_TEST_MAIL_CAPTURE_DIR'])/(hashlib.sha256(email.encode()).hexdigest()+'.jsonl')
  page.goto(BASE_URL+'/account');page.locator('#register-form [name=username]').fill(email.split('@')[0]);page.locator('#register-form [name=email]').fill(email);page.locator('#register-form [name=password]').fill(secrets.token_urlsafe(20))
  page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
  page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click();page.locator('#member-panel').wait_for()
  confirmation=json.loads(mail_path.read_text().splitlines()[-1]);link=next(line for line in confirmation['body'].splitlines() if line.startswith('https://'))
  page.goto(BASE_URL+'/account#'+urlsplit(link).fragment);page.locator('#confirm-email-link').click()
  page.wait_for_function("document.querySelector('#email-link-status').textContent.includes('Correo confirmado')")
  page.goto(BASE_URL+'/account#pricing');page.wait_for_function("!document.querySelector('#trial-start').disabled")
  page.locator('#trial-start').click();assert not page.locator('#annual-terms').is_checked()
  assert ctx.request.get(BASE_URL+'/api/account/me').json()['payments']==[]
  page.locator('#annual-terms').check()
  page.route('https://checkout.stripe.com/**',lambda r:r.fulfill(content_type='text/html',body='<p>Proveedor Stripe simulado: 25 EUR por un año</p>'))
  page.locator('#trial-start').click();page.wait_for_url('https://checkout.stripe.com/**')
  query=parse_qs(urlsplit(page.url).query);order=query['order'][0];checkout=query['checkout'][0]
  # Returning from Checkout alone never grants access.
  page.goto(BASE_URL+'/account?payment=processing');page.locator('#member-panel').wait_for()
  assert not ctx.request.get(BASE_URL+'/api/account/me').json()['user']['live_annual']
  event={'id':'evt_browser_'+secrets.token_hex(8),'livemode':True,'type':'checkout.session.completed','data':{'object':{'id':checkout,'payment_status':'paid','amount_total':2500,'currency':'eur','metadata':{'ol_order':order},'payment_intent':'pi_browser_'+secrets.token_hex(8)}}}
  raw=json.dumps(event).encode();timestamp=str(int(time.time()));signature=hmac.new(b'whsec_browser_local_fixture',timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  headers={'Content-Type':'application/json','Stripe-Signature':'t='+timestamp+',v1='+signature}
  assert ctx.request.post(BASE_URL+'/api/payments/webhook/platform',data=raw,headers=headers).status==200
  assert ctx.request.post(BASE_URL+'/api/payments/webhook/platform',data=raw,headers=headers).status==200
  page.reload();page.wait_for_function("document.querySelector('#access-status').textContent.includes('anual activo')")
  account=ctx.request.get(BASE_URL+'/api/account/me').json();assert account['user']['live_annual'] and len(account['payments'])==1
  mails=[json.loads(line) for line in mail_path.read_text().splitlines()]
  invites=[m for m in mails if 'solicita tu plaza' in m['title']]
  assert len(invites)==1 and '/live#founders' in invites[0]['body']
  page.goto(BASE_URL+'/live#founders');page.wait_for_function("document.querySelector('#founder-claim').textContent==='Solicitar mi plaza de fundador'")
  page.locator('#founder-claim').click();page.wait_for_function("!document.querySelector('#human-answer').disabled&&document.querySelector('#human-image').src.length>0")
  page.locator('#human-answer').fill('OL234');page.locator('#founder-claim').click();page.wait_for_url('**/live?welcome=founder#creator-panel')
  assert ctx.request.get(BASE_URL+'/api/account/me').json()['user']['founder_number']==1
  assert not errors,errors;browser.close()
 print('OK: register, verify email, accept annual terms, 25 EUR Checkout, no access on return alone, signed confirmation once, one customer email, then founder claim')
if __name__=='__main__':run()
