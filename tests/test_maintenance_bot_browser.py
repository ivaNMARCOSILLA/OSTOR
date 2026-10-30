"""Browser-clock checks of the honest admin-visible maintenance scheduler."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844});login_context(context)
  page=context.new_page();errors=[];reports=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('response',lambda r:reports.append(r.status) if r.url.endswith('/api/admin/maintenance-report') else None)
  page.clock.install();page.goto(BASE_URL+'/account')
  page.locator('#navigation-health-admin > summary').click()
  page.wait_for_function("document.querySelector('#maintenance-check-results').children.length>6&&!document.querySelector('#maintenance-check-now').disabled")
  assert page.locator('#maintenance-frequency').input_value()=='30'
  note=page.locator('#maintenance-bot-schedule');assert 'Próxima revisión:' in note.inner_text()
  assert 'No hay vigilancia permanente del servidor' in note.inner_text()
  initial=len(reports);page.clock.fast_forward(30*60000+100)
  page.wait_for_function("!document.querySelector('#maintenance-check-now').disabled")
  page.wait_for_timeout(200);assert len(reports)==initial+1,(initial,reports)
  page.locator('#maintenance-frequency').select_option('0')
  page.wait_for_function("!document.querySelector('#maintenance-check-now').disabled&&document.querySelector('#maintenance-bot-schedule').textContent.includes('Solo revisión manual')")
  manual=len(reports);page.clock.fast_forward(60*60000)
  page.wait_for_timeout(200);assert len(reports)==manual
  page.locator('#maintenance-frequency').select_option('15')
  page.wait_for_function("!document.querySelector('#maintenance-check-now').disabled&&document.querySelector('#maintenance-bot-schedule').textContent.includes('Próxima revisión:')")
  before_hidden=len(reports)
  page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true})")
  page.clock.fast_forward(20*60000);page.wait_for_timeout(200);assert len(reports)==before_hidden
  page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
  page.wait_for_function("!document.querySelector('#maintenance-check-now').disabled")
  page.wait_for_timeout(200);assert len(reports)==before_hidden+1
  assert 'automática al volver al panel' in page.locator('#maintenance-terminal').inner_text()
  assert not errors,errors
  browser.close()
 print('OK: 30-minute browser schedule, manual mode, suspended-tab catch-up, visible scope and timestamps; no permanent server monitor claimed')
if __name__=='__main__':run()
