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
   for scheme in ['light','dark']:
    page.emulate_media(color_scheme=scheme)
    assert page.locator('body').evaluate('e=>getComputedStyle(e).backgroundColor')=='rgb(0, 0, 0)'
    assert page.locator('body').evaluate('e=>getComputedStyle(e).colorScheme')=='dark'
   assert 'jungle' not in page.locator('body').evaluate('e=>getComputedStyle(e).backgroundImage')
   assert page.locator('#fondos-ol,a[href*=fondos-ol]').count()==0
   for width in [1440,390,320]:
    page.set_viewport_size({'width':width,'height':1000});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),(path,width)
  page.goto(BASE_URL+'/');styles=page.evaluate("()=>({fg:getComputedStyle(document.querySelector('#hero h1')).color,bg:getComputedStyle(document.querySelector('#hero')).backgroundImage})")
  fg=list(map(int,re.findall(r'\d+',styles['fg'])[:3]));stops=re.findall(r'rgb\((\d+), (\d+), (\d+)\)',styles['bg']);assert stops or page.locator('#hero').evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(0, 0, 0)'
  for stop in stops:
   values=sorted([luminance(fg),luminance([int(x) for x in stop])]);assert (values[1]+.05)/(values[0]+.05)>=4.5,styles
  # Check actual computed foreground/background pairs for visible controls.
  for path in ['/','/account','/live']:
   page.goto(BASE_URL+path)
   pairs=page.locator('button,input,select,textarea').evaluate_all("els=>els.filter(e=>e.getClientRects().length).map(e=>{let s=getComputedStyle(e);return {fg:s.color,bg:s.backgroundColor,label:e.id||e.tagName}}).filter(s=>s.bg.startsWith('rgb('))")
   for pair in pairs:
    fg=[int(x) for x in re.findall(r'\d+',pair['fg'])[:3]];bg=[int(x) for x in re.findall(r'\d+',pair['bg'])[:3]]
    values=sorted([luminance(fg),luminance(bg)]);assert (values[1]+.05)/(values[0]+.05)>=4.5,(path,pair)
  for path in ['/','/account','/live','/legal/aviso-legal.html','/legal/privacidad.html','/legal/cookies.html']:
   page.goto(BASE_URL+path)
   issues=page.evaluate(r"""()=>{
    const rgb=s=>(s.match(/[\d.]+/g)||[]).map(Number),lum=c=>c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
    let out=[];for(const e of document.querySelectorAll('body *')){
     if(![...e.childNodes].some(n=>n.nodeType===3&&n.textContent.trim())||!e.getClientRects().length||e.closest('[hidden],.hidden'))continue;
     let s=getComputedStyle(e);if(s.visibility==='hidden'||s.opacity==='0')continue;
     let bg=[0,0,0],n=e,gradient=false;while(n){let st=getComputedStyle(n),c=rgb(st.backgroundColor);if(st.backgroundImage!=='none'){gradient=true;break}if(c.length===3||c[3]===1){bg=c;break}n=n.parentElement}if(gradient)continue;
     let fg=rgb(s.webkitTextFillColor||s.color);if(fg[3]===0)continue;let a=lum(fg),b=lum(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05),large=parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18.66&&parseInt(s.fontWeight)>=700);
     if(ratio<(large?3:4.5))out.push({tag:e.tagName,id:e.id,cls:e.className,text:e.textContent.trim().slice(0,65),fg:s.color,bg,ratio});
    }return out;
   }""")
   assert not issues,(path,issues)
  page.goto(BASE_URL+'/')
  hero=page.locator('#hero');assert hero.evaluate("e=>getComputedStyle(e).backgroundColor")=='rgb(0, 0, 0)'
  annual=page.locator('#planes a[href="/account#pricing"]')
  assert annual.inner_text()=='Acceso'
  assert annual.evaluate("e=>getComputedStyle(e).webkitTextFillColor")=='rgb(16, 16, 16)'
  fixed=annual.evaluate("e=>{let s=getComputedStyle(e);return [s.color,s.backgroundColor,s.opacity,s.animationName,s.backgroundImage]}")
  page.wait_for_timeout(500);assert fixed==annual.evaluate("e=>{let s=getComputedStyle(e);return [s.color,s.backgroundColor,s.opacity,s.animationName,s.backgroundImage]}")
  assert fixed[2:] == ['1','none','none'],fixed
  assert annual.evaluate("e=>getComputedStyle(e,'::before').content")=='none'
  first=hero.evaluate("e=>getComputedStyle(e).borderTopColor");page.wait_for_timeout(400);assert first!=hero.evaluate("e=>getComputedStyle(e).borderTopColor")
  page.emulate_media(reduced_motion='reduce');assert hero.evaluate("e=>getComputedStyle(e).animationName")=='none'
  page.screenshot(path='/tmp/electronicama-shared-theme-mobile.png',full_page=True);b.close()
 print('OK: shared style on six pages, no foliage or wallpaper UI, three widths, text contrast on solid surfaces, animated LED borders and reduced-motion support')
if __name__=='__main__':run()
