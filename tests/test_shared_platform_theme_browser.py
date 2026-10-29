"""Shared skin, removed wallpaper and readable hero across pages."""
import re
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def luminance(rgb):
 values=[c/255 for c in rgb];values=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
 return sum(a*b for a,b in zip(values,[.2126,.7152,.0722]))
def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();login_context(ctx);page=ctx.new_page();page.route('**/api/search?*',lambda r:r.fulfill(json=[]))
  for path in ['/','/account','/live','/legal/aviso-legal.html','/legal/privacidad.html','/legal/cookies.html']:
   page.goto(BASE_URL+path)
   assert page.locator('body').evaluate("e=>e.classList.contains('electronicama-theme')")
   assert 'jungle' not in page.locator('body').evaluate('e=>getComputedStyle(e).backgroundImage')
   assert page.locator('#fondos-ol,a[href*=fondos-ol]').count()==0
   for width in [1440,390,320]:
    page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),(path,width)
  page.goto(BASE_URL+'/');styles=page.evaluate("()=>({fg:getComputedStyle(document.querySelector('#hero h1')).color,bg:getComputedStyle(document.querySelector('#hero')).backgroundImage})")
  fg=list(map(int,re.findall(r'\d+',styles['fg'])[:3]));stops=re.findall(r'rgb\((\d+), (\d+), (\d+)\)',styles['bg']);assert stops
  for stop in stops:
   values=sorted([luminance(fg),luminance([int(x) for x in stop])]);assert (values[1]+.05)/(values[0]+.05)>=4.5,styles
  page.screenshot(path='/tmp/electronicama-shared-theme-mobile.png',full_page=True);b.close()
 print('OK: shared style on six pages, no foliage or wallpaper UI, three widths, hero contrast above 4.5 across gradient stops')
if __name__=='__main__':run()
