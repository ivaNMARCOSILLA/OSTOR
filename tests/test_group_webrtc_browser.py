"""Actual local WebRTC encoding/decoding of seven synthetic cameras and audio.
No real devices, external ICE servers, production rooms or paid Egress calls.
"""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context
from test_stream_continuity_browser import SDK

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required']);ctx=browser.new_context();login_context(ctx);page=ctx.new_page();page.add_init_script(SDK)
  channel={'id':'b'*32,'title':'WebRTC siete fuentes','username':'prueba','category':'musica','bio':''}
  page.route('**/api/streamers',lambda r:r.fulfill(json={'video_ready':True,'streamer_active':True,'mine':None,'channels':[channel],'setup_checks':None}))
  page.route('**/api/streamers/*/token',lambda r:r.fulfill(json={'url':'wss://fixture.invalid','token':'fixture'}))
  page.route('**/api/streamers/*/access',lambda r:r.fulfill(json={'allowed':True,'ended':False,'listed':True}))
  page.route('**/api/streamers/*/comments*',lambda r:r.fulfill(json={'comments':[],'cursor':'','can_post':True,'reactions':[],'session_start':'webrtc'}))
  page.route('**/api/streamers/*/view',lambda r:r.fulfill(json={'recorded':False}))
  page.goto(BASE_URL+'/live');page.get_by_role('button',name='Ver vídeo en directo de WebRTC siete fuentes').click();page.locator('#live-stage').wait_for(state='visible')
  page.evaluate("""async()=>{
   const sender=new RTCPeerConnection({iceServers:[]}),receiver=new RTCPeerConnection({iceServers:[]});window.localRTC={sender,receiver,timers:[]};
   sender.onicecandidate=e=>{if(e.candidate)receiver.addIceCandidate(e.candidate).catch(error=>console.error(error))};receiver.onicecandidate=e=>{if(e.candidate)sender.addIceCandidate(e.candidate).catch(error=>console.error(error))};
   receiver.ontrack=e=>{const track=e.track;const element=document.createElement(track.kind);element.muted=true;element.srcObject=new MediaStream([track]);element.className='rtc-received';fakeRooms.at(-1).events.track({sid:track.id,kind:track.kind,source:track.kind==='video'?'camera':'microphone',attach:()=>element});element.play();};
   for(let i=0;i<7;i++){const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;const context=canvas.getContext('2d');let frame=0;localRTC.timers.push(setInterval(()=>{context.fillStyle=['#183c39','#392443','#36401b'][i%3];context.fillRect(0,0,320,180);context.fillStyle='#f5d397';context.fillRect((frame++*5)%280,50,40,40);context.fillText('Fuente '+i,10,20)},100));sender.addTrack(canvas.captureStream(10).getVideoTracks()[0]);}
   const audio=new AudioContext(),oscillator=audio.createOscillator(),destination=audio.createMediaStreamDestination();oscillator.frequency.value=440;oscillator.connect(destination);oscillator.start();await audio.resume();localRTC.audio=audio;localRTC.oscillator=oscillator;sender.addTrack(destination.stream.getAudioTracks()[0]);
   await sender.setLocalDescription(await sender.createOffer());await receiver.setRemoteDescription(sender.localDescription);await receiver.setLocalDescription(await receiver.createAnswer());await sender.setRemoteDescription(receiver.localDescription);
  }""")
  try:page.wait_for_function("document.querySelectorAll('video.rtc-received').length===7&&[...document.querySelectorAll('video.rtc-received')].every(v=>v.videoWidth>0&&v.currentTime>1)",timeout=20000)
  except Exception:
   state=page.evaluate("()=>({sender:localRTC.sender.connectionState,receiver:localRTC.receiver.connectionState,candidates:Boolean(localRTC.sender.localDescription?.sdp.includes('a=candidate:'))})")
   if not state['candidates']:
    print('SKIP: this execution environment supplied no local ICE candidates; real WebRTC transmission remains unverified',flush=True);browser.close();return
   raise
  def stats():return page.evaluate("async()=>{const stats=[...(await localRTC.receiver.getStats()).values()].filter(s=>s.type==='inbound-rtp');return {videos:stats.filter(s=>s.kind==='video').map(s=>s.framesDecoded||0),audio:stats.filter(s=>s.kind==='audio').reduce((n,s)=>n+(s.packetsReceived||0),0)}}")
  before=stats();page.wait_for_timeout(3200);after=stats()
  assert len(after['videos'])==7 and all(b>a for a,b in zip(before['videos'],after['videos'])),(before,after)
  assert after['audio']>before['audio']>0,(before,after)
  assert page.locator('#live-media.group-stage video').count()==7
  page.evaluate("()=>{for(const timer of localRTC.timers)clearInterval(timer);localRTC.oscillator.stop();localRTC.audio.close();localRTC.sender.close();localRTC.receiver.close()}");browser.close()
 print('OK: real local WebRTC transmitted and decoded seven moving video sources and audio; every inbound frame/packet counter advanced')
if __name__=='__main__':run()
