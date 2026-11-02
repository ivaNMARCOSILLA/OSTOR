from playwright.sync_api import sync_playwright
from browser_support import BASE_URL


def assert_mobile_header(page, width):
  """Visible controls and every label must fit without colliding or wrapping vertically."""
  issues=page.locator('.topbar').evaluate('''header=>{
   const issues=[],bounds=header.getBoundingClientRect();
   const controls=[...header.querySelectorAll('#mobile-menu,.mobile-quick-search,.header-account,.site-language select')].filter(el=>el.getClientRects().length);
   for(const el of controls){
    const box=el.getBoundingClientRect(),name=el.id||el.className;
    if(box.left<bounds.left-1||box.right>bounds.right+1||box.top<bounds.top-1||box.bottom>bounds.bottom+1)issues.push(name+' escapes header');
    if(el.scrollWidth>el.clientWidth+1)issues.push(name+' clips its content');
   }
   for(let i=0;i<controls.length;i++)for(let j=i+1;j<controls.length;j++){
    const a=controls[i].getBoundingClientRect(),b=controls[j].getBoundingClientRect();
    if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1&&Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)issues.push('header controls overlap');
   }
   const label=header.querySelector('#mobile-menu-label');
   if(label.getClientRects().length&&getComputedStyle(label).display!=='none'){
    const box=label.getBoundingClientRect(),line=parseFloat(getComputedStyle(label).lineHeight);
    if(box.height>line*1.5)issues.push('menu label wraps into multiple lines');
   }
   const word=header.querySelector('.brand-word'),symbol=header.querySelector('.brand-infinity');
   if(word.getBoundingClientRect().bottom>symbol.getBoundingClientRect().bottom+8||symbol.getBoundingClientRect().bottom>word.getBoundingClientRect().bottom+8)issues.push('wordmark splits across lines');
   return issues;
  }''')
  assert not issues,(width,issues)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width


def assert_dark_menu(page, width):
  # The outer background is exposed in padding and between sections. Checking
  # only the individual dark buttons missed the white frame shown on iPhone.
  palette=page.locator('#mobile-nav').evaluate('''nav=>{
   const rgb=value=>(value.match(/[\\d.]+/g)||[]).slice(0,3).map(Number);
   const luminance=channels=>channels.map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
   const background=luminance(rgb(getComputedStyle(nav).backgroundColor));
   const lowContrast=[...nav.querySelectorAll('a,button,.menu-group-title')].filter(el=>el.getClientRects().length).filter(el=>{
    const style=getComputedStyle(el),text=luminance(rgb(style.color));let base=el,paint;
    while(base){paint=getComputedStyle(base).backgroundColor;if(!paint.endsWith(', 0)')&&paint!=='transparent')break;base=base.parentElement;}
    const surface=luminance(rgb(paint));return (Math.max(text,surface)+.05)/(Math.min(text,surface)+.05)<4.5;
   }).map(el=>el.textContent.trim());
   return {background,lowContrast};
  }''')
  assert palette['background']<.08,(width,'mobile-menu gutters are not dark',palette)
  assert not palette['lowContrast'],(width,'unreadable menu text',palette)


def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
  page=context.new_page();errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/search?*',lambda r:r.fulfill(json=[]))
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
  menu=page.locator('#mobile-menu');nav=page.locator('#mobile-nav')
  menu.click();assert menu.get_attribute('aria-expanded')=='true'
  assert nav.locator('.menu-group-title').all_text_contents()==['Música','Ol Live','Tu espacio']
  assert nav.locator('a[href="/account"]').count()==1
  assert nav.locator('a[href="/live#live-catalogue"]').count()==1
  assert nav.locator('a[href="/live#creator-panel"]').count()==1
  # Open navigation stays usable even over the playing bar, without stopping audio.
  page.evaluate("document.querySelector('#player').classList.remove('hidden')")
  nav.locator('a[href="#ol-collection"]').click()
  assert nav.is_hidden() and page.locator('#ol-collection').get_attribute('open') is not None
  page.evaluate('scrollTo(0,0)');menu.click();page.keyboard.press('Escape')
  assert nav.is_hidden() and menu.evaluate('e=>e===document.activeElement')
  menu.click();nav.locator('[data-view="favorites"]').click()
  assert nav.is_hidden();assert page.locator('#main-nav [data-view="favorites"]').get_attribute('aria-pressed')=='true'
  page.evaluate('scrollTo(0,0)');menu.click();nav.locator('#cookie-settings').click()
  assert page.locator('#consent-dialog').is_visible() and nav.is_hidden()
  page.locator('#consent-decline').click()
  page.evaluate('scrollTo(0,0)');menu.click();page.locator('.mobile-quick-search').click()
  assert nav.is_hidden()
  page.evaluate("document.querySelector('#player').classList.add('hidden')")
  for width in [320,360,390,393,430,600,768,900]:
   height=430 if width==900 else 844
   page.set_viewport_size({'width':width,'height':height})
   for language in ['de','fr','auto']:
    if width<=800:menu.click()
    page.locator('[data-site-language]').select_option(language)
    page.wait_for_function('wanted=>document.documentElement.lang===wanted',arg='es' if language=='auto' else language)
    if width<=800:page.keyboard.press('Escape')
    page.evaluate('scrollTo(0,0)');assert_mobile_header(page,width);menu.click()
    assert_mobile_header(page,width);assert_dark_menu(page,width)
    box=nav.bounding_box();assert box['y']>=page.locator('.topbar').bounding_box()['height']-1,(width,box)
    assert box['y']+box['height']<=height+1,(width,'menu escapes viewport',box)
    for item in nav.locator('a,button').all():
     item_box=item.bounding_box();assert item_box['height']>=44 and item_box['width']>100
    # A short landscape viewport must still scroll down to the final setting.
    nav.locator('#cookie-settings').scroll_into_view_if_needed()
    assert nav.locator('#cookie-settings').evaluate('(el)=>{const box=el.getBoundingClientRect();return box.top>=0&&box.bottom<=innerHeight+1;}')
    if width==393 and language=='auto':
     nav.evaluate('el=>el.scrollTop=0');page.screenshot(path='/tmp/ol-home-menu-mobile.png')
    page.keyboard.press('Escape');assert nav.is_hidden()
  page.set_viewport_size({'width':1440,'height':1000});assert menu.is_hidden()
  assert page.locator('#main-nav .menu-group-title').all_text_contents()==['Música','Ol Live','Tu espacio']
  page.locator('#main-nav [data-cookie-preferences]').click();assert page.locator('#consent-dialog').is_visible()
  assert not errors,errors;browser.close()
 print('OK: dark readable mobile menu, header bounds, three languages, eight mobile widths, landscape scrolling, desktop navigation and working destinations')

if __name__=='__main__':run()
