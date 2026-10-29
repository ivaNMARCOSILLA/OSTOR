"""Real timers exercise transient presence/list/session failures without closing a simulated LiveKit room."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

SDK="""window.fakeRooms=[];window.LivekitClient={Track:{Source:{Camera:'camera',Microphone:'microphone',ScreenShare:'screen_share'}},RoomEvent:{TrackSubscribed:'track',TrackUnsubscribed:'untrack',Disconnected:'disconnected',ConnectionStateChanged:'state',ParticipantConnected:'joined',ParticipantDisconnected:'left',LocalTrackPublished:'local',LocalTrackUnpublished:'unlocal'},Room:class{constructor(){this.events={};this.remoteParticipants=new Map();this.disconnects=0;this.localParticipant={isCameraEnabled:true,isMicrophoneEnabled:true,trackPublications:new Map(),enableCameraAndMicrophone:async()=>{},isScreenShareEnabled:false,setScreenShareEnabled:async(enabled,options)=>{this.localParticipant.isScreenShareEnabled=enabled;this.screenOptions=options;},setCameraEnabled:async()=>{},setMicrophoneEnabled:async()=>{}};window.fakeRooms.push(this)}on(e,fn){this.events[e]=fn;return this}async connect(){this.state='connected'}async disconnect(){this.disconnects++;this.state='disconnected';this.events.disconnected?.()}async startAudio(){}}};"""

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);ctx=b.new_context();login_context(ctx)
  mine={'id':'a'*32,'title':'Mi prueba estable','username':'browser-admin','bio':'','category':'musica'};channel={'id':'b'*32,'title':'Otro directo','username':'otro','bio':'','live':True,'category':'musica'}
  page=ctx.new_page();page.clock.install();page.add_init_script(SDK);state={'beats':0,'listed':True,'deny':False,'session_failure':False};errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  account=ctx.request.get(BASE_URL+'/api/account/me').json()
  page.route('**/api/account/me',lambda r:r.fulfill(status=503,json={'error':'Temporal'}) if state['session_failure'] else r.fulfill(json=account))
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':mine,'channels':[channel] if state['listed'] else [],'setup_checks':None}))
  page.route('**/api/status',lambda r:r.fulfill(json={'live_premiere':False,'maintenance':{'scope':'off','message':''}}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'local-fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(status=403,json={'error':'Acceso retirado'}) if state['deny'] else r.fulfill(json={'allowed':True,'ended':False,'listed':state['listed']}))
  page.route('**/assets/community.js*',lambda r:r.fulfill(content_type='text/javascript',body='export class StreamCommunity {start(){} stop(){} syncMicrophone(){}}'))
  def presence(r):
   if not r.request.post_data_json.get('live'):r.fulfill(json={'ok':True});return
   state['beats']+=1
   if state['beats']==2:r.fulfill(status=503,json={'error':'Fallo temporal de verificación'})
   elif state['beats']==3:r.fulfill(status=409,json={'error':'Vídeo aún no verificado','code':'broadcast_unverified'})
   else:r.fulfill(json={'ok':True})
  layouts=[]
  page.route('**/api/streamers/me/layout',lambda r:(layouts.append(r.request.post_data_json),r.fulfill(json={'ok':True})))
  page.route('**/api/streamers/me/live',presence)
  page.goto(BASE_URL+'/live#stream-studio');page.locator('#start-camera').click();page.locator('#live-stage').wait_for()
  assert page.locator('#live-player #enable-sound').is_visible();assert page.locator('#live-player #fullscreen-live').is_visible();assert page.locator('#live-player #share-screen-live').is_visible()
  page.evaluate("document.querySelector('#live-player').requestFullscreen=async()=>{window.fullscreenTarget='live-player'}")
  page.locator('#fullscreen-live').click();assert page.evaluate('fullscreenTarget')=='live-player'
  page.evaluate("()=>{fakeRooms.at(-1).events.track({sid:'video-controls-test',kind:'video',source:'camera',attach:()=>{const v=document.createElement('video');v.controls=true;v.id='direct-video-test';return v}})}")
  video=page.locator('#direct-video-test');assert video.evaluate('e=>!e.controls&&e.playsInline&&e.disablePictureInPicture')
  assert video.get_attribute('controls') is None
  assert video.evaluate("e=>getComputedStyle(e).pointerEvents")=='none'
  page.evaluate("()=>{document.querySelector('#live-player').requestFullscreen=undefined;document.querySelector('#direct-video-test').webkitEnterFullscreen=()=>{throw Error('Native player must not be used')}}")
  page.locator('#fullscreen-live').click();assert page.locator('#live-player').evaluate("e=>e.classList.contains('ol-inline-fullscreen')")
  page.locator('#fullscreen-live').click();assert not page.locator('#live-player').evaluate("e=>e.classList.contains('ol-inline-fullscreen')")
  page.locator('#share-screen-live').evaluate('(button)=>button.disabled=false');page.locator('#share-screen-live').click()
  page.wait_for_function("fakeRooms.at(-1).screenOptions?.displaySurface==='monitor'")
  page.locator('#live-layout').select_option('screen');page.wait_for_function("document.querySelector('#live-media').dataset.layout==='screen'")
  assert layouts==[{'layout':'screen'}]
  page.evaluate("document.querySelector('#live-media').append(Object.assign(document.createElement('video'),{id:'stable-frame'}))")
  for delay in [25000,25000,25000]:
   page.clock.run_for(delay);page.wait_for_timeout(30)
   assert page.evaluate('fakeRooms.at(-1).disconnects')==0
   assert page.locator('#stable-frame').count()==1
  assert state['beats']>=4
  state['session_failure']=True;page.clock.run_for(65000);page.wait_for_timeout(30)
  assert page.evaluate('fakeRooms.at(-1).disconnects')==0
  state['session_failure']=False
  page.locator('#leave-room').click();page.wait_for_function('fakeRooms.at(-1).disconnects===1')
  page.locator('.live-channel button').first.click();page.locator('#live-stage').wait_for();state['listed']=False
  page.clock.run_for(31000);page.wait_for_timeout(30);assert page.evaluate('fakeRooms.at(-1).disconnects')==0
  state['deny']=True;page.clock.run_for(31000);page.wait_for_function('fakeRooms.at(-1).disconnects===1')
  assert not errors,errors;b.close()
 print('OK: 25/30/60-second transient failures preserve the room; explicit leave and revoked access still disconnect')
if __name__=='__main__':run()
