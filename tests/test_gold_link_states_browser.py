"""Gold links retain dark rendered text after visiting, hover, focus and press."""
import io
from PIL import Image
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.goto(BASE_URL+'/live')
  link=page.locator('.premiere-studio-actions a.button').first
  page.locator('.premiere-studio-actions').evaluate("e=>{e.style.setProperty('display','flex','important');e.closest('.intro').style.setProperty('display','block','important')}")
  link.click();page.evaluate('scrollTo(0,0)')
  for state in ['visited','hover','focus','pressed']:
   if state=='hover':link.hover()
   elif state=='focus':link.focus()
   elif state=='pressed':link.hover();page.mouse.down()
   try:
    assert link.evaluate("e=>getComputedStyle(e).webkitTextFillColor")=='rgb(16, 16, 16)'
    area=link.evaluate("e=>{const r=document.createRange();r.selectNode(e.firstChild);const b=r.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width,height:b.height}}")
    image=Image.open(io.BytesIO(page.screenshot(clip=area))).convert('RGB')
    assert sum(max(pixel)<80 for pixel in image.getdata())>30,(state,'rendered text is not dark enough')
   finally:
    if state=='pressed':page.mouse.up()
  page.screenshot(path='/tmp/gold-link-visited-fixed.png');browser.close()
 print('OK: actual rendered dark text on gold after visiting, hovering, focusing and pressing')
if __name__=='__main__':run()
