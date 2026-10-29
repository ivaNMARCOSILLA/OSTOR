"""Official player boundary mocked locally: no real API key, quota or YouTube tracking."""
import io,wave
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL
FAKE_API='''window.YT={Player:class{constructor(mount,config){this.config=config;this.position=30;this.state=2;this.iframe=document.createElement('iframe');this.iframe.src='https://www.youtube-nocookie.com/embed/'+config.videoId;this.iframe.title='YouTube video player';mount.replaceWith(this.iframe);window.testYouTube=this;setTimeout(()=>config.events.onReady(),0);}playVideo(){this.state=1;this.config.events.onStateChange({data:1});}pauseVideo(){this.state=2;this.config.events.onStateChange({data:2});}getPlayerState(){return this.state;}getCurrentTime(){return this.position;}getDuration(){return 200;}seekTo(value){this.position=value;}destroy(){this.destroyed=true;this.iframe.remove();}}};window.onYouTubeIframeAPIReady();'''

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);context=browser.new_context(viewport={'width':390,'height':900})
  video=[{'id':'youtube_abcdefghijk','video_id':'abcdefghijk','source':'YOUTUBE','title':'Piano video','channel':'Artist'},{'id':'youtube_1234567890a','video_id':'1234567890a','source':'YOUTUBE','title':'Second video'}]
  audio=[{'id':'archive_test','source':'ARCHIVE','title':'Native audio','channel':'Artist'}]
  context.route('**/api/search?*',lambda r:r.fulfill(json=video if 'source=YOUTUBE' in r.request.url else audio))
  context.route('https://www.youtube.com/iframe_api',lambda r:r.fulfill(body=FAKE_API,content_type='application/javascript'))
  context.route('https://www.youtube-nocookie.com/**',lambda r:r.fulfill(body='<html><body>Local provider fixture</body></html>',content_type='text/html'))
  wav=io.BytesIO()
  with wave.open(wav,'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\x00\x00'*80000)
  context.route('**/api/play/*',lambda r:r.fulfill(body=wav.getvalue(),content_type='audio/wav'))
  context.add_init_script("""window.olHidden=false;Object.defineProperty(document,'hidden',{get:()=>window.olHidden,configurable:true});window.deviceMedia={handlers:{},setActionHandler(name,fn){this.handlers[name]=fn;},setPositionState(value){this.position=value;}};Object.defineProperty(navigator,'mediaSession',{value:window.deviceMedia,configurable:true});""")
  page=context.new_page();errors=[];seen=[];page.on('pageerror',lambda error:errors.append(str(error)));page.on('request',lambda r:seen.append(r.url))
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('.track-card').first.wait_for()
  assert not any('youtube.com/iframe_api' in url for url in seen)
  page.locator('[data-source="YOUTUBE"]').click();page.wait_for_function("document.querySelector('.track-title')?.textContent==='Piano video'")
  page.locator('.cover-button').first.click();page.wait_for_function("document.querySelector('#player-message').textContent==='Reproduciendo en YouTube'")
  assert page.locator('#player-media iframe').is_visible();assert page.locator('#player-media iframe').bounding_box()['height']>=200
  assert page.locator('audio').count()==0
  assert page.evaluate('deviceMedia.metadata.title')=='Piano video'
  page.evaluate("window.olHidden=true;document.dispatchEvent(new Event('visibilitychange'))")
  assert page.evaluate('testYouTube.getPlayerState()')==1
  page.evaluate('deviceMedia.handlers.pause()');assert page.evaluate('testYouTube.getPlayerState()')==2
  page.evaluate('deviceMedia.handlers.play()');assert page.evaluate('testYouTube.getPlayerState()')==1
  page.evaluate('deviceMedia.handlers.play()');assert page.evaluate('testYouTube.getPlayerState()')==1
  page.evaluate('deviceMedia.handlers.nexttrack()');page.wait_for_function("document.querySelector('#player-title').textContent==='Second video'&&window.testYouTube.getPlayerState()===1")
  page.evaluate('deviceMedia.handlers.previoustrack()');page.wait_for_function("document.querySelector('#player-title').textContent==='Piano video'&&window.testYouTube.getPlayerState()===1")
  assert 'electronicama no envía una orden de pausa' in page.locator('#youtube-playback-trace').text_content()
  page.evaluate("window.olHidden=false;document.dispatchEvent(new Event('visibilitychange'))")
  page.locator('.youtube-diagnostics summary').click()
  with page.expect_download() as report:page.locator('.youtube-diagnostics button').click()
  assert report.value.suggested_filename=='ol-youtube-reproduccion.txt'
  page.evaluate('for(let i=0;i<45;i++)document.dispatchEvent(new Event("visibilitychange"))')
  assert len(page.locator('#youtube-playback-trace').inner_text().splitlines())<=40

  page.locator('#player-expand').click();page.locator('#sleep-timer').select_option('15')
  page.evaluate("const previousNow=Date.now;Date.now=()=>previousNow()+901000;document.dispatchEvent(new Event('visibilitychange'));Date.now=previousNow")
  assert page.evaluate('testYouTube.getPlayerState()')==2
  assert page.locator('#toggle-play').inner_text()=='▶'
  page.evaluate('deviceMedia.handlers.play()');assert page.evaluate('testYouTube.getPlayerState()')==1
  page.locator('#toggle-play').click();assert 'pausa' in page.locator('#player-message').inner_text()
  page.locator('#toggle-play').click();page.locator('#seek-forward').evaluate('(e)=>e.click()');assert page.evaluate('testYouTube.position')==45
  page.evaluate('testYouTube.config.events.onError({data:101})');assert 'no permite' in page.locator('#player-message').inner_text()
  assert page.locator('.youtube-source-link').get_attribute('href')=='https://www.youtube.com/watch?v=abcdefghijk'
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
  page.locator('#next-track').click();page.wait_for_function("document.querySelector('#player-title').textContent==='Second video'")
  page.locator('[data-source="ALL"]').click();page.wait_for_function("document.querySelector('.track-title')?.textContent==='Native audio'");page.locator('.cover-button').first.click()
  page.wait_for_function("document.querySelector('audio')?.currentTime>0");assert page.locator('iframe').count()==0;assert page.evaluate('testYouTube.destroyed')
  page.locator('#player-close').click();assert page.locator('#player').is_hidden()
  # A delayed provider script must not replace newer native playback.
  racing=context.new_page();pending=[];racing.route('https://www.youtube.com/iframe_api',lambda r:pending.append(r));racing.goto(BASE_URL+'/')
  if racing.locator('#consent-dialog').is_visible():racing.locator('#consent-decline').click()
  racing.locator('[data-source="YOUTUBE"]').click();racing.wait_for_function("document.querySelector('.track-title')?.textContent==='Piano video'");racing.locator('.cover-button').first.click();racing.wait_for_timeout(100)
  racing.locator('[data-source="ALL"]').click();racing.wait_for_function("document.querySelector('.track-title')?.textContent==='Native audio'");racing.locator('.cover-button').first.click();racing.wait_for_function("document.querySelector('audio')?.currentTime>0")
  for request in pending:request.fulfill(body=FAKE_API,content_type='application/javascript')
  racing.wait_for_timeout(100);assert racing.locator('iframe').count()==0;assert racing.locator('#player-title').inner_text()=='Native audio'
  stalled=context.new_page();stalled.clock.install();retry=[];held=[]
  def stalled_audio(route):
   if 'retry=1' in route.request.url:retry.append(route.request.url);route.fulfill(body=wav.getvalue(),content_type='audio/wav')
   else:held.append(route)
  stalled.route('**/api/play/*',stalled_audio);stalled.goto(BASE_URL+'/')
  if stalled.locator('#consent-dialog').is_visible():stalled.locator('#consent-decline').click()
  stalled.locator('.cover-button').first.click();stalled.clock.fast_forward(15001)
  stalled.wait_for_function("document.querySelector('audio')?.currentTime>0");assert len(retry)==1
  for request in held:request.abort()
  assert not errors,errors;browser.close()
 print('OK: YouTube search, official visible player, visibility without forced pause, multimedia controls and next while hidden, bounded diagnostics, native/video transitions, pause/seek/next, embed errors, late-load race, lazy provider loading and four widths')
if __name__=='__main__':run()
