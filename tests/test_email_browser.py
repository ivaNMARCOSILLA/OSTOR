"""Real local email links captured outside the app; no production email or test backdoor."""
import os,json,hashlib,secrets
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  name='mail-'+secrets.token_hex(4);email=name+'@example.test';password=secrets.token_urlsafe(20)
  def mail_fragment():
   path=Path(os.environ['OL_TEST_MAIL_CAPTURE_DIR'])/(hashlib.sha256(email.encode()).hexdigest()+'.jsonl')
   data=json.loads(path.read_text().splitlines()[-1]);link=next(line for line in data['body'].splitlines() if line.startswith('https://'))
   return urlsplit(link).fragment
  page.goto(BASE_URL+'/account');page.locator('#register-form [name=username]').fill(name);page.locator('#register-form [name=email]').fill(email);page.locator('#register-form [name=nickname]').fill('Mi apodo Ol');page.locator('#register-form [name=password]').fill(password)
  page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
  page.locator('#registration-human-answer').fill('OL234');page.locator('#registration-submit').click();page.wait_for_url('**/account?registered=1')
  page.locator('#member-panel').wait_for(state='visible');assert 'Mi apodo Ol' in page.locator('#member-title').inner_text()
  assert 'pendiente' in page.locator('#email-verification-status').inner_text().lower()
  page.goto(BASE_URL+'/account#'+mail_fragment());page.locator('#email-link-panel').wait_for(state='visible')
  assert not page.evaluate('location.hash');page.locator('#confirm-email-link').click();page.wait_for_function("document.querySelector('#email-link-status').textContent.includes('Correo confirmado')")
  page.locator('#logout').click();page.locator('#login-form [name=username]').fill(email);page.locator('#login-form [name=password]').fill(password);page.locator('#login-form button').click();page.locator('#member-panel').wait_for(state='visible')
  page.locator('#logout').click();page.locator('#password-help > summary').click();page.locator('#password-request-form [name=email]').fill(email)
  page.wait_for_function("document.querySelector('#recovery-human-id').value.length===32")
  page.locator('#recovery-human-answer').fill('OL234');page.locator('#password-request-form button[type=submit]').click();page.wait_for_function("document.querySelector('#password-request-status').textContent.includes('recibirás')")
  page.goto(BASE_URL+'/account#'+mail_fragment());page.locator('#password-reset-panel').wait_for(state='visible');assert not page.evaluate('location.hash')
  new=secrets.token_urlsafe(20);page.locator('#password-reset-form [name=password]').fill(new);page.locator('#password-reset-form [name=password_confirm]').fill(new);page.locator('#password-reset-form button').click();page.wait_for_url('**/account?password_reset=1')
  page.locator('#login-form [name=username]').fill(email);page.locator('#login-form [name=password]').fill(new);page.locator('#login-form button').click();page.locator('#member-panel').wait_for(state='visible')
  assert context.request.get(BASE_URL+'/api/account/me').json()['profile']['email_verified'] is True
  assert not errors,errors;browser.close()
 print('OK: registration email/nickname, private captured confirmation, confirmed-email login, recovery with human check, new password login, token removed from browser address')

if __name__=='__main__':run()
