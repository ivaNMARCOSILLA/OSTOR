"""Two-hour first reminders and four-hour postponement leave all media controls intact."""
from pathlib import Path
from playwright.sync_api import sync_playwright

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=b.new_page();page.clock.install()
  page.set_content('<section id="live-stage"><button id="leave-room">Salir</button><div id="live-player"><video id="test-media"></video><aside id="live-break-reminder" class="hidden"><p id="live-break-copy"></p><button id="live-break-snooze">Recordar en 4 horas</button><button id="live-break-dismiss">Cerrar</button></aside></div></section><style>.hidden{display:none}</style>')
  page.add_script_tag(content=(Path(__file__).resolve().parents[1]/'assets/live-breaks.js').read_text())
  page.evaluate("window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:true,publisher:false}}))")
  page.clock.run_for(119*60000);assert page.locator('#live-break-reminder').is_hidden()
  page.clock.run_for(90000);assert page.locator('#live-break-reminder').is_visible();assert 'en el directo' in page.locator('#live-break-copy').inner_text()
  page.locator('#live-break-snooze').click();page.clock.run_for(239*60000);assert page.locator('#live-break-reminder').is_hidden();page.clock.run_for(90000);assert page.locator('#live-break-reminder').is_visible()
  page.locator('#live-break-dismiss').click();page.clock.run_for(239*60000);assert page.locator('#live-break-reminder').is_hidden();page.clock.run_for(90000);assert page.locator('#live-break-reminder').is_visible()
  page.evaluate("window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:false}}))");assert page.locator('#live-break-reminder').is_hidden()
  page.evaluate("window.dispatchEvent(new CustomEvent('ol:live-session',{detail:{connected:true,publisher:true}}))")
  page.clock.run_for(120*60000+31000);assert 'emitiendo' in page.locator('#live-break-copy').inner_text()
  assert page.locator('#live-player #live-break-reminder').count()==1;assert page.locator('#leave-room').is_visible();assert page.locator('#test-media').count()==1;b.close()
 print('OK: two-hour first reminder, four-hour snooze and dismissal for viewer/publisher, no control interruption')
if __name__=='__main__':run()
