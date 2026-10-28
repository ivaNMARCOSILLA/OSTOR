"""The long platform name and infinity stay within their visible header bounds."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=b.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  for path in ['/','/account','/live']:
   page.goto(BASE_URL+path);page.wait_for_timeout(500)
   for width in [320,360,390,430,768,1024,1440]:
    page.set_viewport_size({'width':width,'height':900})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(path,width)
    for logo in page.locator('.brand,.mobile-brand,.logo').all():
     if not logo.is_visible():continue
     box=logo.bounding_box();assert box['x']>=-1 and box['x']+box['width']<=width+1,(path,width,box)
     assert logo.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1'),(path,width,'wordmark overflow')
     for symbol in logo.locator('.brand-infinity').all():
      sb=symbol.bounding_box();assert sb['x']>=box['x'] and sb['x']+sb['width']<=box['x']+box['width']+1,(path,width,'infinity overflow')
    page.evaluate('scrollTo(500,0)');assert page.evaluate('scrollX')==0,(path,width,'horizontal pan')
   if path=='/':page.set_viewport_size({'width':390,'height':900});page.screenshot(path='/tmp/electronicama-wordmark-mobile.png')
  assert not errors,errors
  b.close()
 print('OK: bounded wordmark and infinity, no lateral pan on home/account/live at seven widths')
if __name__=='__main__':run()
