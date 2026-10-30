"""Live catalogue displays the real JPEG preview and refreshes it without F5."""
from io import BytesIO
from PIL import Image
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 output=BytesIO();Image.new('RGB',(320,180),(20,130,80)).save(output,format='JPEG');jpeg=output.getvalue()
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':844});login_context(context);page=context.new_page();page.clock.install();state={'ended':False};images=[]
  channel={'id':'a'*32,'title':'Mi pantalla compartida','username':'Creador','category':'musica','bio':'','thumbnail_url':'/api/streamers/'+'a'*32+'/thumbnail'}
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':None,'channels':[] if state['ended'] else [channel],'setup_checks':None}))
  def picture(route):images.append(route.request.url);route.fulfill(content_type='image/jpeg',body=jpeg)
  page.route('**/api/streamers/*/thumbnail*',picture)
  page.goto(BASE_URL+'/live');image=page.locator('img[data-live-thumbnail]');image.wait_for();page.wait_for_function("document.querySelector('img[data-live-thumbnail]').naturalWidth===320")
  assert image.get_attribute('alt')=='Vista previa de Mi pantalla compartida'
  assert image.evaluate("e=>getComputedStyle(e).opacity==='1'&&e.getBoundingClientRect().width>200")
  before=len(images);page.clock.fast_forward(21000);page.locator('#refresh-channels').click();page.wait_for_function("!document.querySelector('#refresh-channels').disabled");page.wait_for_timeout(100);assert len(images)>before
  page.screenshot(path='/tmp/ol-catalogue-preview.png',full_page=True)
  state['ended']=True;page.locator('#refresh-channels').click();page.locator('img[data-live-thumbnail]').wait_for(state='detached')
  browser.close()
 print('OK: full-size real JPEG preview, refresh without F5, ended-channel preview removed')
if __name__=='__main__':run()
