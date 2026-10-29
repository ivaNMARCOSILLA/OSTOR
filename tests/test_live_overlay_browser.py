"""Actual moving browser video fills the player; overlay chat stays below 75%."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.add_init_script(SDK)
  channel={'id':'a'*32,'title':'Pantalla original','username':'Creador','category':'musica','bio':'Prueba de proporciones'}
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':None,'channels':[channel],'setup_checks':None}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True}))
  page.route('**/api/streamers/*/comments*',lambda r:r.fulfill(json={'comments':[{'id':str(i),'username':'Participante','body':'Comentario de prueba '+str(i),'kind':'comment'} for i in range(60)],'cursor':'test-cursor','can_post':True}))
  page.route('**/api/streamers/*/view',lambda r:r.fulfill(json={'recorded':False}))
  page.goto(BASE_URL+'/live');page.get_by_role('button',name='Ver vídeo en directo de Pantalla original').click();page.locator('#live-stage').wait_for(state='visible')
  page.evaluate("""()=>{const c=document.createElement('canvas');c.width=640;c.height=360;const x=c.getContext('2d');let n=0;setInterval(()=>{x.fillStyle='#173d43';x.fillRect(0,0,640,360);x.fillStyle='#f5d397';x.fillRect((n++*4)%600,120,40,40)},100);const v=document.createElement('video');v.muted=true;v.srcObject=c.captureStream(10);v.id='overlay-real-video';fakeRooms.at(-1).events.track({sid:'moving',kind:'video',source:'camera',attach:()=>v});v.play()}""")
  page.wait_for_function("document.querySelector('#overlay-real-video').currentTime>.2")
  page.locator('#live-comments p').nth(59).wait_for()
  for width,height in [(1920,1080),(1440,900),(390,844),(320,740)]:
   page.set_viewport_size({'width':width,'height':height})
   for layout in ['auto','screen']:
    page.locator('#live-media').evaluate('(e,l)=>e.dataset.layout=l',layout)
    assert page.evaluate("()=>{const m=document.querySelector('#live-media').getBoundingClientRect(),v=document.querySelector('#overlay-real-video').getBoundingClientRect();return v.width>=m.width*.99&&v.height>=m.height*.99}"),(width,layout)
   bounds=page.evaluate("()=>{const p=document.querySelector('#live-player').getBoundingClientRect(),c=document.querySelector('#community-panel').getBoundingClientRect();return {ratio:c.height/p.height,inside:c.left>=p.left&&c.right<=p.right+1,top:c.top-p.top,quarter:p.height*.25}}")
   assert bounds['ratio']<=.75 and bounds['inside'] and bounds['top']>=bounds['quarter']-2,bounds
   assert page.locator('#live-comments').evaluate('e=>e.scrollHeight>e.clientHeight')
   page.locator('#live-comments').evaluate('e=>e.scrollTop=0');page.wait_for_timeout(1100);assert page.locator('#live-comments').evaluate('e=>e.scrollTop')==0
   if width in [1440,390]:page.screenshot(path=f'/tmp/ol-overlay-{width}.png')
  page.set_viewport_size({'width':1440,'height':900});page.evaluate("document.querySelector('#live-player').requestFullscreen=undefined")
  page.locator('#fullscreen-live').click();assert page.locator('#live-player #community-panel').is_visible();page.locator('#fullscreen-live').click()
  browser.close()
 print('OK: full-size moving camera including stale screen layout, overlay chat at most 75%, scroll preserved, four widths and fullscreen')
if __name__=='__main__':run()
