"""Free music works before registration; premium is exclusive to Ol Livis."""
import io,wave
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':1440,'height':1000});page=context.new_page();errors=[];requests=[]
  page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
  records=[{'id':'archive_test','title':'Música gratuita','channel':'Artist','source':'ARCHIVE','locked':False}]
  audio=io.BytesIO()
  with wave.open(audio,'wb') as stream:stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000);stream.writeframes(b'\0\0'*16000*4)
  page.route('**/api/search?*',lambda route:route.fulfill(json=records));page.route('**/api/play/archive_test*',lambda route:route.fulfill(body=audio.getvalue(),content_type='audio/wav'))
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('.track-card').first.wait_for()
  assert page.locator('#music-free-banner').is_visible();assert page.locator('#mas-musica .music-web-card').count()==7
  page.locator('.cover-button').click();page.wait_for_function("document.querySelector('#player-media audio')?.currentTime>0 || document.querySelector('#player audio')?.currentTime>0")
  assert not page.locator('#unlock-dialog').is_visible()
  page.locator('.save-button').first.click();assert page.locator('#favorites-count').inner_text()=='1'
  page.locator('[data-view=favorites]').first.click();assert page.locator('.track-card').count()==1
  assert not any('googletagmanager.com' in url or 'googlesyndication.com' in url for url in requests)
  for width in [1440,768,390,320]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path='docs/maggy-preview.png',full_page=True)
  assert not errors,errors;browser.close()
 print('OK: guests play and save music for free, no unlock dialog, no advertising tags, 4 widths')

if __name__=='__main__':run()
