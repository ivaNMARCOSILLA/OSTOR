"""Broadcast workspace and real ordinal postal stamp remain usable at mobile/desktop sizes."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.add_init_script(SDK);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  channel={'id':'d'*32,'title':'Canal del fundador','username':'Fundador','category':'musica','bio':'Música y comunidad','founder_number':7,'founder_signature':{'mode':'letra','letter':'E','caption':'Viu el moment'}}
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':None,'channels':[channel],'setup_checks':None}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True}))
  page.route('**/assets/community.js*',lambda r:r.fulfill(content_type='text/javascript',body='export class StreamCommunity {start(){} stop(){} syncMicrophone(){}}'))
  page.goto(BASE_URL+'/live');page.locator('.live-channel').wait_for()
  assert page.locator('#livis-channel-rail .rail-channel').count()==1
  assert page.locator('#mobile-live-chat').count()==0
  assert page.locator('#live-catalogue').evaluate("e=>e.compareDocumentPosition(document.querySelector('#founders'))&Node.DOCUMENT_POSITION_FOLLOWING")
  page.get_by_role('button',name='Ver vídeo en directo de Canal del fundador',exact=True).click();page.locator('#live-stage').wait_for(state='visible')
  stamp=page.locator('#live-founder-stamp .founder-postage-stamp')
  assert 'N.º 007' in stamp.inner_text();stamp.locator('summary').click()
  assert stamp.locator('.founder-personal-emblem').inner_text()=='E'
  assert 'Viu el moment' in stamp.inner_text();assert 'plaza oficial n.º 7' in stamp.inner_text()
  for width in [1920,1440,1100,768,390,320]:
   page.set_viewport_size({'width':width,'height':1000})
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   assert stamp.is_visible()
   assert page.locator('#fullscreen-live').is_visible()
   assert page.locator('#community-panel').is_visible()
   page.locator('#live-stage').evaluate("e=>e.dataset.publisher='true'")
   assert page.locator('#community-panel').is_visible()
   page.locator('#live-stage').evaluate("e=>e.dataset.publisher='false'")
   assert page.evaluate("()=>{const s=document.querySelector('#live-founder-stamp').getBoundingClientRect(),p=document.querySelector('#live-player').getBoundingClientRect();return s.left>=p.left&&s.right<=p.right+1&&s.top>=p.top;}"),width
   assert page.evaluate("document.querySelector('#live-founder-stamp').getBoundingClientRect().bottom<=document.querySelector('#fullscreen-live').getBoundingClientRect().top"),width
   assert page.evaluate("()=>{const c=document.querySelector('#community-panel').getBoundingClientRect(),p=document.querySelector('#live-player').getBoundingClientRect();return c.left>=p.left&&c.right<=p.right+1&&c.height<=p.height*.75+1}")
  page.set_viewport_size({'width':1440,'height':1000})
  page.evaluate("()=>{const m=document.querySelector('#live-media');m.dataset.layout='screen';const v=document.createElement('video');v.dataset.source='camera';v.dataset.layoutTest='1';m.append(v)}")
  assert page.evaluate("()=>{const m=document.querySelector('#live-media').getBoundingClientRect(),v=document.querySelector('[data-layout-test]').getBoundingClientRect();return v.width>=m.width*.95&&v.height>=m.height*.95}"),'camera must fill the player when no shared screen exists'
  page.evaluate("document.querySelectorAll('[data-layout-test]').forEach(e=>e.remove());document.querySelector('#live-media').dataset.layout='auto'")
  page.set_viewport_size({'width':390,'height':844})
  page.evaluate("()=>{const m=document.querySelector('#live-media');for(const source of ['camera','screen_share']){const v=document.createElement('video');v.dataset.source=source;v.dataset.layoutTest='1';m.append(v)}}")
  geometry=page.evaluate("()=>{const m=document.querySelector('#live-media'),screen=m.querySelector('[data-source=screen_share]').getBoundingClientRect(),camera=m.querySelector('[data-source=camera]').getBoundingClientRect();return {screen:screen.width,camera:camera.width,position:getComputedStyle(document.querySelector('#live-stage')).position}}")
  assert geometry['screen']>geometry['camera']*3 and geometry['position']=='fixed',geometry
  page.locator('#mobile-live-controls').click();assert page.locator('#mobile-live-controls').get_attribute('aria-expanded')=='true'
  page.locator('#mobile-live-controls').click();page.evaluate("document.querySelectorAll('[data-layout-test]').forEach(e=>e.remove())")
  page.screenshot(path='/tmp/electronicama-livis-workspace-mobile.png',full_page=True)
  page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path='/tmp/electronicama-livis-workspace-desktop.png',full_page=True)
  page.get_by_role('button',name='Salir del directo',exact=True).click();page.locator('#live-stage').wait_for(state='hidden')
  assert page.locator('#live-founder-stamp').locator('details').count()==0
  assert not errors,errors;browser.close()
 print('OK: compact catalogue before promotions, real channel rail, side chat, numbered postal stamp with personal letter/phrase, six widths, player controls retained')
if __name__=='__main__':run()
