"""Thirty-minute reminders for both roles never interrupt media or room controls."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();login_context(ctx);page=ctx.new_page();page.clock.install();page.goto(BASE_URL+'/live');page.wait_for_function("document.querySelector('#live-break-snooze')!==null")
  page.evaluate("document.querySelector('#live-stage').classList.remove('hidden');window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:true,publisher:false}}))")
  page.clock.run_for(30*60000);page.locator('#live-break-reminder').wait_for(state='visible');assert 'en el directo' in page.locator('#live-break-copy').inner_text()
  page.locator('#live-break-snooze').click();assert page.locator('#live-break-reminder').is_hidden();page.clock.run_for(9*60000);assert page.locator('#live-break-reminder').is_hidden();page.clock.run_for(61100);page.locator('#live-break-reminder').wait_for(state='visible')
  page.evaluate("window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:false}}))");assert page.locator('#live-break-reminder').is_hidden()
  page.evaluate("document.querySelector('#live-stage').classList.remove('hidden');window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:true,publisher:true}}))")
  page.clock.run_for(30*60000+1100);assert 'emitiendo' in page.locator('#live-break-copy').inner_text();assert page.locator('#live-player #live-break-reminder').count()==1
  assert page.locator('#leave-room').is_visible();b.close()
 print('OK: viewer/publisher 30-minute reminders, ten-minute snooze, disconnect cleanup, player controls retained')
if __name__=='__main__':run()
