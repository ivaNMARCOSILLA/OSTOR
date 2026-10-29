"""Actual Three.js rendering and lifecycle; fake camera, no uploaded production data."""
import io,wave
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL
MESSAGE='AVUI TORNAREM AL CEL DEL MEU PARE I DE LA MEU DONA I QUI SAPIGA SER BO POT VENIR HI HAN MOLTS COSUS'

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--use-angle=swiftshader','--enable-unsafe-swiftshader','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
  context=browser.new_context(viewport={'width':390,'height':900},permissions=['camera']);page=context.new_page();errors=[];requests=[]
  page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda r:requests.append(r.url));page.route('**/api/search?*',lambda r:r.fulfill(json=[{'id':'archive_holo','source':'ARCHIVE','title':'Música con hologramas'}]))
  wav=io.BytesIO()
  with wave.open(wav,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x00'*960000)
  page.route('**/api/play/*',lambda r:r.fulfill(body=wav.getvalue(),content_type='audio/wav'))
  page.add_init_script("""window.holoStreams=[];const native=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);navigator.mediaDevices.getUserMedia=async options=>{window.holoRequest=options;const stream=await native(options);window.holoStreams.push(stream);return stream;};""")
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
  assert page.locator('#holograms-title').inner_text().startswith('Hologramas')
  assert page.locator('#holograms-title .holograms-label').inner_text()=='Geometría viva'
  assert page.locator('.hologram-message').inner_text()==MESSAGE
  assert 'memory' not in page.locator('#hologramas').inner_text().lower()
  assert not any('/vendor/three/' in url or '/vendor/hands/' in url for url in requests)
  assert page.evaluate('holoStreams.length')==0
  page.locator('.cover-button').first.click();page.wait_for_function("document.querySelector('audio')?.currentTime>0")
  page.locator('#player-compact').click()
  page.locator('#hologram-viewer>summary').click();page.wait_for_function("Number(document.querySelector('#holo-stage').dataset.frames)>1")
  assert page.locator('#holo-counter').inner_text()=='Figura 1 de 256'
  page.locator('#holo-next').click();assert 'Figura 2 ' in page.locator('#holo-counter').inner_text()
  page.locator('#holo-prev').click();page.locator('#holo-square').click();assert page.locator('#holo-name').inner_text()=='El cuadrado'
  page.locator('#holo-index').fill('5');page.locator('#holo-index').dispatch_event('input');assert 'Möbius' in page.locator('#holo-name').inner_text()
  page.locator('#holo-wire').click();assert page.locator('#holo-wire').get_attribute('aria-pressed')=='true'
  page.locator('#holo-globe').click();assert page.locator('#holo-name').inner_text()=='Globo terráqueo'
  obj=b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
  page.locator('#holo-file').set_input_files({'name':'figura.obj','mimeType':'text/plain','buffer':obj});page.wait_for_function("document.querySelector('#holo-name').textContent==='figura.obj'")
  page.locator('#holo-file').set_input_files({'name':'roto.stl','mimeType':'application/octet-stream','buffer':b'\xff'*100});page.wait_for_function("document.querySelector('#holo-status').textContent.includes('No se pudo abrir')")
  assert page.locator('#holo-name').inner_text()=='figura.obj'
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.set_viewport_size({'width':390,'height':900});page.locator('#hologramas').scroll_into_view_if_needed();page.screenshot(path='/tmp/ol-hologramas-mobile.png')
  assert page.evaluate('holoStreams.length')==0
  page.locator('#holo-camera').click();page.wait_for_function("document.querySelector('#holo-video').srcObject?.getVideoTracks()[0]?.readyState==='live'")
  assert page.evaluate('holoRequest.audio') is False
  page.locator('#holo-hands').click();page.wait_for_function("Number(document.querySelector('#holo-stage').dataset.handFrames)>0",timeout=60000)
  assert page.locator('#holo-hands').get_attribute('aria-pressed')=='true'
  page.locator('#holo-camera').click();assert page.evaluate("holoStreams.every(stream=>stream.getTracks().every(track=>track.readyState==='ended'))")
  # Close/reopen must reset state and camera rather than keep a hidden scene running.
  page.locator('#holo-camera').click();page.wait_for_function("document.querySelector('#holo-video').srcObject!==null")
  page.locator('#hologram-viewer>summary').click();page.wait_for_function("holoStreams.every(stream=>stream.getTracks().every(track=>track.readyState==='ended'))")
  page.locator('#hologram-viewer>summary').click();page.wait_for_function("document.querySelector('#holo-counter').textContent==='Figura 1 de 256'&&!document.querySelector('#holo-ui').hidden")
  page.emulate_media(reduced_motion='reduce');page.wait_for_function("document.querySelector('#holo-motion').getAttribute('aria-pressed')==='false'")
  page.locator('#holo-canvas').focus();page.keyboard.press('End');assert page.locator('#holo-name').inner_text()=='El cuadrado'
  page.keyboard.press('Escape');assert page.locator('#hologram-viewer').get_attribute('open') is None
  assert not page.locator('audio').evaluate('element=>element.paused')
  assert not errors,errors;browser.close()
 print('OK: lazy real WebGL, 256 controls, square/globe, bounded local OBJ/STL, real local hand model, explicit camera/no microphone, cleanup/reopen, reduced motion, keyboard, exact Catalan message, uninterrupted music and four widths')
if __name__=='__main__':run()
