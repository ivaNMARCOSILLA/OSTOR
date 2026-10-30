"""CSP blocks injected inline/foreign code while real first-party UI keeps working."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page()
  page.add_init_script("window.policyViolations=[];document.addEventListener('securitypolicyviolation',event=>policyViolations.push({directive:event.effectiveDirective,blocked:event.blockedURI}));")
  requests=[];failures=[];page.route('https://unexpected-script.invalid/**',lambda route:(requests.append(route.request.url),route.abort()));page.on('requestfailed',lambda request:failures.append((request.url,request.failure)))
  page.goto(BASE_URL+'/account')
  page.locator('#login-form').wait_for()
  page.evaluate("()=>{const injected=document.createElement('script');injected.textContent='window.untrustedInlineRan=true';document.body.append(injected);const foreign=document.createElement('script');foreign.src='https://unexpected-script.invalid/injected.js';document.body.append(foreign)}")
  page.wait_for_function("policyViolations.some(v=>v.blocked==='inline')&&policyViolations.some(v=>v.blocked.includes('unexpected-script.invalid'))")
  assert page.evaluate("typeof untrustedInlineRan==='undefined'")
  assert not requests;assert any('unexpected-script.invalid' in url and 'CSP' in (failure or '').upper() for url,failure in failures)
  # A normal reviewed script ran and event listeners remain functional.
  assert page.evaluate("Boolean(window.OlLocale&&document.querySelector('[data-site-language]'))")
  page.locator('[data-site-language]').select_option('en')
  page.wait_for_function("document.documentElement.lang==='en'")
  browser.close()
 print('OK: inline/foreign script injection blocked by actual CSP; no foreign request; first-party language controls keep working')
if __name__=='__main__':run()
