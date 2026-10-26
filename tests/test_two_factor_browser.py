import base64,hashlib,hmac,secrets,struct,time
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def code(secret):
 digest=hmac.new(base64.b32decode(secret),struct.pack('>Q',int(time.time())//30),hashlib.sha1).digest();offset=digest[-1]&15
 return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':844});name='secure-'+secrets.token_hex(3);password=secrets.token_urlsafe(24)
  csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf'];assert context.request.post(BASE_URL+'/api/account/register',data=__import__('registration_support').registration_data(context,{'username':name,'password':password}),headers={'X-CSRF-Token':csrf}).status==201
  page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto(BASE_URL+'/account');page.locator('#two-factor-settings > summary').click()
  page.wait_for_function("document.querySelector('#two-factor-status').textContent.includes('desactivada')")
  page.locator('#two-factor-setup [name=password]').fill(password);page.locator('#two-factor-setup button').click();page.locator('#two-factor-confirm').wait_for(state='visible')
  secret=page.locator('#two-factor-secret').input_value();page.locator('#two-factor-confirm [name=otp]').fill(code(secret));page.locator('#two-factor-confirm button').click()
  page.locator('#two-factor-recovery-box').wait_for(state='visible');recovery=page.locator('#two-factor-recovery-codes').input_value().splitlines();assert len(recovery)==8
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.locator('#two-factor-hide').click();assert page.locator('#two-factor-recovery-codes').input_value()==''
  second=browser.new_context();login=second.new_page();login.on('pageerror',lambda e:errors.append(str(e)));login.goto(BASE_URL+'/account')
  login.locator('#login-form [name=username]').fill(name);login.locator('#login-form [name=password]').fill(password);login.locator('#login-form button').click();login.locator('#login-second-factor').wait_for(state='visible');assert login.locator('#member-panel').is_hidden()
  login.locator('#login-form [name=recovery_code]').fill(recovery[0]);login.locator('#login-form button').click();login.locator('#member-panel').wait_for(state='visible')
  login.locator('#two-factor-settings > summary').click();login.locator('#two-factor-disable').wait_for(state='visible')
  login.locator('#two-factor-disable [name=password]').fill(password);login.locator('#two-factor-disable [name=recovery_code]').fill(recovery[1]);login.locator('#two-factor-disable button').click()
  login.wait_for_function("document.querySelector('#two-factor-status').textContent.includes('desactivada')")
  assert not errors,errors;browser.close()
 print('OK: optional authenticator setup, explicit TOTP confirmation, recovery codes hidden after saving, login challenge, single-use recovery, self-disable, four widths')

if __name__=='__main__':run()
