"""Manual thirty-minute local soak: roles, gold contrast, cross-device updates and video."""
import time
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from registration_support import registration_data
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);admin=browser.new_context();login_context(admin)
  free=browser.new_context();csrf=free.request.get(BASE_URL+'/api/account/me').json()['csrf']
  result=free.request.post(BASE_URL+'/api/account/register',data=registration_data(free,{'username':'review-viewer','password':'review-password-123'}),headers={'X-CSRF-Token':csrf});assert result.status==201
  anonymous=browser.new_context();state={'title':'Seguimiento inicial'}
  csrf=admin.request.get(BASE_URL+'/api/account/me').json()['csrf'];admin.request.post(BASE_URL+'/api/streamers/me',data={'title':state['title']},headers={'X-CSRF-Token':csrf})
  channel=admin.request.get(BASE_URL+'/api/streamers').json()['mine'];page=free.new_page();page.add_init_script(SDK)
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':False,'mine':None,'channels':[dict(channel,title=state['title'])],'setup_checks':None}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True}))
  page.route('**/api/streamers/*/comments*',lambda r:r.fulfill(json={'comments':[],'cursor':'','can_post':True}))
  page.route('**/api/streamers/*/view',lambda r:r.fulfill(json={'recorded':False}))
  page.goto(BASE_URL+'/live');page.get_by_role('button',name='Ver vídeo en directo de Seguimiento inicial').click();page.locator('#live-stage').wait_for(state='visible')
  page.evaluate("""()=>{const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;const ctx=canvas.getContext('2d');window.reviewFrames=0;setInterval(()=>{ctx.fillStyle=reviewFrames++%2?'#274':'#247';ctx.fillRect(0,0,320,180)},100);const v=document.createElement('video');v.id='review-moving-video';v.muted=true;v.srcObject=canvas.captureStream(10);fakeRooms.at(-1).events.track({sid:'review-video',kind:'video',source:'camera',attach:()=>v});v.play();}""")
  home=admin.new_page();home.route('**/api/search?*',lambda r:r.fulfill(json=[]));home.goto(BASE_URL+'/')
  start=time.monotonic();last_video_time=0;round_number=0
  while True:
   elapsed=time.monotonic()-start
   for ctx in [free,anonymous]:
    token=ctx.request.get(BASE_URL+'/api/account/me').json()['csrf']
    response=ctx.request.post(BASE_URL+'/api/streamers/admin/check-video',data={},headers={'X-CSRF-Token':token})
    assert response.status in [401,403],response.status
    assert 'checks' not in response.json()
    for path in ['/api/admin/launch-readiness','/api/admin/maintenance-report']:
     response=ctx.request.get(BASE_URL+path);assert response.status in [401,403],(path,response.status)
   assert page.locator('#video-setup').is_hidden()
   assert page.locator('#live-stage').is_visible();assert page.evaluate('fakeRooms.length===1&&fakeRooms[0].disconnects===0')
   video=page.locator('#review-moving-video');assert video.evaluate('v=>!v.controls&&v.playsInline')
   current=video.evaluate('v=>v.currentTime')
   if round_number:assert current>last_video_time,(current,last_video_time)
   last_video_time=current
   width=[320,390,768,1440][round_number%4];home.set_viewport_size({'width':width,'height':900});page.set_viewport_size({'width':width,'height':900})
   assert home.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
   button=home.locator('#planes a[href="/account#pricing"]');style=button.evaluate("e=>{const s=getComputedStyle(e);return {text:e.textContent,color:s.color,fill:s.webkitTextFillColor,bg:s.backgroundColor,animation:s.animationName,opacity:s.opacity}}")
   assert style['text']=='Acceso' and style['color']=='rgb(16, 16, 16)' and style['fill']=='rgb(16, 16, 16)' and style['animation']=='none' and style['opacity']=='1',style
   if elapsed>=1800:
    print(f'OK: {elapsed:.1f} seconds, {round_number+1} rounds, moving video, role denials, gold labels, responsive layouts and live sync',flush=True);break
   state['title']='Cambio remoto '+str(round_number+1)
   csrf=admin.request.get(BASE_URL+'/api/account/me').json()['csrf'];response=admin.request.post(BASE_URL+'/api/streamers/me',data={'title':state['title']},headers={'X-CSRF-Token':csrf});assert response.status==200
   page.wait_for_function('(title)=>document.querySelector("#stage-title").textContent===title',arg=state['title'],timeout=12000)
   print(f'ROUND {round_number+1}: {elapsed:.1f}s, width {width}, video {current:.1f}s, admin-only checks rejected, gold label fixed, remote edit received',flush=True)
   round_number+=1;target=min(start+round_number*60,start+1800)
   while time.monotonic()<target:page.wait_for_timeout(min(1000,max(1,(target-time.monotonic())*1000)))
  browser.close()
if __name__=='__main__':run()
