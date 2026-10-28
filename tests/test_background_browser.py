"""Cross-device UI and standard media session actions, with local audio only."""
import io,wave,json
from pathlib import Path
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':900})
  context.add_init_script("""window.olHidden=false;Object.defineProperty(document,'hidden',{get:()=>window.olHidden,configurable:true});window.deviceMedia={handlers:{},setActionHandler(name,fn){this.handlers[name]=fn;},setPositionState(value){this.position=value;}};Object.defineProperty(navigator,'mediaSession',{value:window.deviceMedia,configurable:true});""")
  tracks=[{'id':'archive_first','source':'ARCHIVE','title':'First audio','channel':'Artist'},{'id':'archive_second','source':'ARCHIVE','title':'Second audio','channel':'Artist'}]
  context.route('**/api/search?*',lambda r:r.fulfill(json=tracks))
  wav=io.BytesIO()
  with wave.open(wav,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x00'*240000)
  context.route('**/api/play/*',lambda r:r.fulfill(body=wav.getvalue(),content_type='audio/wav'))
  page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)));page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('.cover-button').first.click();page.wait_for_function("document.querySelector('audio')?.currentTime>0")
  assert page.evaluate('deviceMedia.metadata.title')=='First audio';assert page.evaluate('deviceMedia.metadata.artwork.length')==1
  page.evaluate('deviceMedia.handlers.play()');assert not page.locator('audio').evaluate('e=>e.paused')
  page.locator('#player-favorite').click();assert page.locator('#player-favorite').inner_text()=='★'
  page.locator('#player-compact').click();assert page.locator('#player').get_attribute('class').find('compact')>=0
  assert page.locator('#player-media').is_hidden();assert not page.locator('audio').evaluate('e=>e.paused')
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   assert page.locator('#toggle-play').is_visible() and page.locator('#player-home').is_visible()
  before=page.locator('audio').evaluate('e=>e.currentTime');page.locator('#player-home').click();assert page.locator('audio').evaluate('e=>e.currentTime')>=before
  page.evaluate('deviceMedia.handlers.pause()');assert page.locator('audio').evaluate('e=>e.paused')
  page.evaluate('deviceMedia.handlers.play()');page.wait_for_function("!document.querySelector('audio').paused")
  queue=[tracks[0],tracks[1]]
  page.evaluate('items=>window.dispatchEvent(new CustomEvent("maggy:play",{detail:items}))',queue)
  page.wait_for_function("document.querySelector('audio')?.currentTime>0")
  page.evaluate("window.olHidden=true;document.dispatchEvent(new Event('visibilitychange'))")
  assert not page.locator('audio').evaluate('e=>e.paused')
  page.evaluate('deviceMedia.handlers.nexttrack()');page.wait_for_function("document.querySelector('#player-title').textContent==='Second audio'")
  assert page.locator('iframe').count()==0
  page.evaluate('deviceMedia.handlers.stop()');assert page.locator('#player').is_hidden();assert page.evaluate('Object.values(deviceMedia.handlers).every(value=>value===null)')
  page.evaluate("window.olHidden=false;document.dispatchEvent(new Event('visibilitychange'))")
  # A direct PNG download is a real file, not an unsupported OS-settings command.
  link=page.locator('#fondos-ol a[download]');assert link.get_attribute('download')=='Ol-fondo-hojas.png'
  with page.expect_download() as downloaded:link.click()
  assert downloaded.value.suggested_filename in {'Ol-fondo-hojas.png','ol-wallpaper.png'}
  assert Path(downloaded.value.path()).read_bytes()[:8]==b'\x89PNG\r\n\x1a\n'
  assert page.request.get(BASE_URL+'/assets/ol-wallpaper.png').headers['content-type'].startswith('image/png')
  page.goto(BASE_URL+'/?view=favorites');page.wait_for_function("document.querySelector('#main-nav [data-view=favorites]').getAttribute('aria-pressed')==='true'")
  assert page.locator('.track-card').count()==1
  assert not errors,errors;browser.close()
 print('OK: wallpaper PNG download, compact audio without stopping, star/home, media play/pause/stop/next, background visibility, launcher shortcut and four widths')
if __name__=='__main__':run()
