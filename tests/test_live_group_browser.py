"""Seven moving video sources, screen hierarchy, unobscured controls and guest flow.
The browser media is real canvas capture; LiveKit signalling is a local fixture.
"""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

VIDEOS="""(count)=>{window.groupTracks=window.groupTracks||[];for(let i=0;i<count;i++){const c=document.createElement('canvas');c.width=640;c.height=360;const x=c.getContext('2d');let n=0;const timer=setInterval(()=>{x.fillStyle=['#173d43','#491a4b','#193c18','#482519'][i%4];x.fillRect(0,0,640,360);x.fillStyle='#f5d397';x.fillRect((n++*4)%600,120,40,40);x.fillText('Cámara '+i,20,30)},100);const v=document.createElement('video');v.id='group-video-'+i;v.muted=true;v.srcObject=c.captureStream(10);const track={sid:'group-'+i,kind:'video',source:'camera',attach:()=>v,detach:()=>[v]};groupTracks.push(track);fakeRooms.at(-1).events.track(track);v.play();}}"""

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=browser.new_context();login_context(ctx)
  channel={'id':'a'*32,'title':'Siete creadores','username':'host','category':'musica','bio':''};requests=[];errors=[]
  def prepare(page,host):
   page.add_init_script(SDK);page.on('pageerror',lambda e:errors.append(str(e)))
   page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':channel if host else None,'channels':[channel],'setup_checks':None,'recording_enabled':True}))
   page.route('**/api/status',lambda r:r.fulfill(json={'live_premiere':False,'maintenance':{'scope':'off','message':''}}))
   def token(r):requests.append(('token',r.request.post_data_json));r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture','session_start':'one'})
   page.route('**/api/streamers/*/token',token)
   page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True,'guest_allowed':not host,'session_start':'one'}))
   page.route('**/api/streamers/*/comments*',lambda r:r.fulfill(json={'comments':[{'id':str(i),'username':'Persona','body':'Comentario '+str(i),'kind':'comment'} for i in range(60)],'cursor':'test-cursor','can_post':True,'session_start':'one'}))
   def presence(r):requests.append(('presence',r.request.post_data_json));r.fulfill(json={'ok':True})
   page.route('**/api/streamers/me/live',presence)
   page.route('**/api/streamers/me/layout',lambda r:r.fulfill(json={'ok':True}))
   def invite(r):requests.append(('invite',r.request.post_data_json));r.fulfill(json={'ok':True})
   page.route('**/api/streamers/me/guests',lambda r:r.fulfill(json={'guests':[],'count':0,'limit':7}) if r.request.method=='GET' else invite(r))
   def thumbnail(r):requests.append(('thumbnail',r.request.post_data_json));r.fulfill(json={'ok':True})
   page.route('**/api/streamers/me/thumbnail',thumbnail)
   page.route('**/api/streamers/*/view',lambda r:r.fulfill(json={'recorded':False}))
  page=ctx.new_page();prepare(page,True);page.goto(BASE_URL+'/live#stream-studio');page.locator('#recording-accept').check();page.locator('#start-camera').click();page.locator('#live-stage').wait_for(state='visible');page.locator('#live-comments p').nth(59).wait_for()
  page.evaluate(VIDEOS,7);page.wait_for_function("[...document.querySelectorAll('#live-media video')].every(v=>v.currentTime>.2)")
  page.wait_for_timeout(1200);assert any(kind=='thumbnail' and data['session_start']=='one' and data['image'].startswith('data:image/jpeg;base64,') for kind,data in requests),'published frames must produce a preview'
  for width,height in [(1440,1000),(768,1000),(390,844),(320,740),(844,390)]:
   page.set_viewport_size({'width':width,'height':height})
   assert page.evaluate("()=>{const m=document.querySelector('#live-media').getBoundingClientRect(),vs=[...document.querySelectorAll('#live-media video')].map(v=>v.getBoundingClientRect());return vs.length===7&&vs.every(v=>v.width>30&&v.height>25&&v.left>=m.left-1&&v.right<=m.right+1&&v.top>=m.top-1&&v.bottom<=m.bottom+1)&&vs.every((a,i)=>vs.every((b,j)=>i===j||Math.min(a.right,b.right)-Math.max(a.left,b.left)<1||Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)<1))}"),(width,height,'overlapping cameras')
   page.locator('#mobile-live-controls').click();assert page.locator('#community-panel').is_visible()
   for selector in ['#toggle-camera','#share-screen-live','#copy-channel-live','#live-layout','#invite-guests']:
    el=page.locator(selector);el.scroll_into_view_if_needed()
    assert el.evaluate("e=>{const b=e.getBoundingClientRect(),hit=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2);return hit===e||e.contains(hit)}"),(width,height,selector,'control obscured')
   assert page.locator('#live-comments').evaluate('e=>e.clientHeight>=48'),(width,height,'chat collapsed')
   page.screenshot(path=f'/tmp/ol-controls-{width}.png')
   page.locator('#mobile-live-controls').click(timeout=4000)
   assert page.locator('#mobile-live-controls').get_attribute('aria-expanded')=='false'
   if width in [1440,390]:page.screenshot(path=f'/tmp/ol-seven-{width}.png')
  page.set_viewport_size({'width':390,'height':844})
  page.evaluate("()=>{const v=document.createElement('video');v.id='shared-screen-test';v.dataset.source='screen_share';document.querySelector('#live-media').append(v)}")
  assert page.evaluate("()=>{const s=document.querySelector('#shared-screen-test').getBoundingClientRect(),c=document.querySelector('#group-video-0').getBoundingClientRect();return s.width>c.width*3&&s.height>c.height*3}"),'screen must be principal'
  page.evaluate("()=>{const video=document.createElement('video');video.id='second-shared-screen';video.dataset.source='screen_share';document.querySelector('#live-media').append(video)}")
  page.locator('#live-screen-source').select_option(index=1);assert not page.locator('#shared-screen-test').is_visible();assert page.locator('#second-shared-screen').is_visible()
  page.evaluate("()=>{fakeRooms.at(-1).events.untrack(groupTracks[6]);document.querySelector('#shared-screen-test').remove();document.querySelector('#second-shared-screen').remove()}")
  assert page.locator('#live-media video').count()==6
  page.locator('#mobile-live-controls').click();page.locator('#live-guest-username').fill('invitado');page.locator('#invite-guests').click();assert ('invite',{'username':'invitado'}) in requests
  page.locator('#mobile-live-controls').click();page.evaluate("document.querySelector('#live-player').requestFullscreen=undefined");page.locator('#fullscreen-live').click();assert page.locator('#mobile-live-controls').is_visible();assert page.locator('#leave-room').is_visible();page.locator('#fullscreen-live').click()
  guest=ctx.new_page();prepare(guest,False);guest.on('dialog',lambda d:d.accept());guest.goto(BASE_URL+'/live');guest.get_by_role('button',name='Ver vídeo en directo de Siete creadores').click();guest.locator('#join-guest').wait_for(state='visible');beats=len([r for r in requests if r[0]=='presence']);guest.locator('#join-guest').click();guest.wait_for_function("document.querySelector('#live-stage').dataset.publisher==='true'")
  assert any(kind=='token' and data.get('guest') and data.get('recording_notice_accepted') for kind,data in requests)
  assert len([r for r in requests if r[0]=='presence'])==beats,'guest must not heartbeat its own channel'
  guest.locator('#mobile-live-controls').click();assert not guest.locator('#invite-guests').is_visible();assert guest.locator('#live-layout').is_disabled();guest.locator('#mobile-live-controls').click();guest.locator('#leave-room').click()
  assert len([r for r in requests if r[0]=='presence'])==beats,'guest exit must not end own or host broadcast'
  assert not errors,errors;browser.close()
 print('OK: seven moving cameras, five viewport sizes, screen principal, controls clickable over chat, full-screen essentials, guest consent/exit')
if __name__=='__main__':run()
