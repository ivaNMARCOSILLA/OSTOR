"""The car-radio display follows playback without changing the audio output."""
from array import array
import io
import math
import wave
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL
from test_youtube_browser import FAKE_API


AUDIT='''
window.radioHidden=false;
Object.defineProperty(document,'hidden',{get:()=>window.radioHidden,configurable:true});
window.radioAudit={microphones:0,elementSources:0};
if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=()=>{window.radioAudit.microphones++;return Promise.reject(new Error('Microphone forbidden in this test'));};
for(const context of [window.AudioContext,window.webkitAudioContext])if(context?.prototype)
 context.prototype.createMediaElementSource=function(){window.radioAudit.elementSources++;throw new Error('Changing the audio output is forbidden');};
'''


def tone():
    """A modulated sine produces real energy and changing analyser levels."""
    sample_rate=8000
    frames=array('h',(int(14000*(.6+.35*math.sin(2*math.pi*1.7*i/sample_rate))*math.sin(2*math.pi*440*i/sample_rate))
                      for i in range(sample_rate*24)))
    target=io.BytesIO()
    with wave.open(target,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(sample_rate)
        output.writeframes(frames.tobytes())
    return target.getvalue()


def levels(page):
    return page.locator('#radio-visualizer .radio-visualizer-bar').evaluate_all(
        "bars=>bars.map(bar=>Number(bar.style.getPropertyValue('--radio-level')||0))")


def rest(page):
    page.wait_for_function("""()=>{
        const display=document.querySelector('#radio-visualizer');
        return display?.dataset.animate==='false'&&[...display.querySelectorAll('.radio-visualizer-bar')]
          .every(bar=>Number(bar.style.getPropertyValue('--radio-level')||0)===0);
    }""")


def hide(page,value):
    page.evaluate("value=>{window.radioHidden=value;document.dispatchEvent(new Event('visibilitychange'));}",value)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        context.add_init_script(AUDIT)
        audio=[{'id':'commons_radio_meter','source':'COMMONS','title':'Radio sine fixture','channel':'Test artist'}]
        videos=[{'id':'youtube_abcdefghijk','video_id':'abcdefghijk','source':'YOUTUBE',
                 'title':'Radio video fixture','channel':'Test artist'}]
        context.route('**/api/search?*',lambda route:route.fulfill(json=videos
            if parse_qs(urlsplit(route.request.url).query).get('source')==['YOUTUBE'] else audio))
        context.route('**/api/play/*',lambda route:route.fulfill(body=tone(),content_type='audio/wav'))
        context.route('https://www.youtube.com/iframe_api',lambda route:route.fulfill(body=FAKE_API,content_type='application/javascript'))
        context.route('https://www.youtube-nocookie.com/**',lambda route:route.fulfill(body='<html><body>Local video</body></html>',content_type='text/html'))
        page=context.new_page();errors=[];navigations=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
        page.goto(BASE_URL+'/')
        if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()
        page.locator('#track-grid .cover-button').first.click()
        page.wait_for_function("document.querySelector('audio')?.currentTime>0")
        display=page.locator('#radio-visualizer')
        expect(display).to_be_visible()
        expect(display.locator('.radio-visualizer-bar')).to_have_count(14)
        expect(display.locator('.radio-visualizer-bars')).to_have_attribute('aria-hidden','true')
        expect(display).to_have_attribute('data-state','playing')
        expect(display).to_have_attribute('data-mode','levels',timeout=8000)
        expect(display).to_have_attribute('data-animate','true')
        expect(display.locator('.radio-visualizer-status')).to_have_text('Nivel de audio')
        assert max(levels(page))>0,'A real sine wave should produce analyser energy'
        page.evaluate("window.radioAudio=document.querySelector('audio');window.radioSource=radioAudio.getAttribute('src')")
        before=page.evaluate('radioAudio.currentTime')
        for _ in range(4):
            page.evaluate("window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}))")
        page.wait_for_timeout(220)
        assert page.evaluate("radioAudio===document.querySelector('audio')&&radioAudio.getAttribute('src')===radioSource")
        assert page.evaluate('radioAudio.currentTime')>before
        assert len(navigations)==1,'Background updates must not reload the document'
        assert page.evaluate('radioAudit')=={'microphones':0,'elementSources':0}
        assert page.locator('audio').get_attribute('crossorigin') is None

        # Pauses, buffering and visibility changes stop only the visual work.
        page.locator('#toggle-play').click()
        page.wait_for_function('radioAudio.paused');rest(page)
        page.locator('#toggle-play').click()
        expect(display).to_have_attribute('data-state','playing')
        page.evaluate("radioAudio.dispatchEvent(new Event('waiting'))")
        rest(page)
        page.evaluate("radioAudio.dispatchEvent(new Event('playing'))")
        expect(display).to_have_attribute('data-animate','true')
        before=page.evaluate('radioAudio.currentTime')
        hide(page,True);rest(page)
        page.wait_for_timeout(160)
        assert page.evaluate('radioAudio.currentTime')>before
        hide(page,False)
        expect(display).to_have_attribute('data-state','playing')
        expect(display).to_have_attribute('data-animate','true')
        page.emulate_media(reduced_motion='reduce');rest(page)
        assert page.evaluate('!radioAudio.paused')
        page.emulate_media(reduced_motion='no-preference')
        expect(display).to_have_attribute('data-animate','true')

        for width in [320,390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
            box=display.bounding_box();player=page.locator('#player').bounding_box()
            assert box and player and box['width']>0,(width,box)
            assert box['x']>=player['x']-1 and box['x']+box['width']<=player['x']+player['width']+1,(width,box,player)
        page.screenshot(path='/tmp/electronicama-radio-display-desktop.png')
        page.locator('#player-close').click()
        expect(page.locator('#player')).to_be_hidden();rest(page)

        # Cross-origin video exposes playback state, never genuine audio levels.
        page.locator('#source-filters [data-source="YOUTUBE"]').click()
        expect(page.locator('#track-grid')).to_contain_text('Radio video fixture')
        page.locator('#track-grid .cover-button').first.click()
        page.wait_for_function('window.testYouTube?.getPlayerState()===1')
        expect(display).to_have_attribute('data-state','playing')
        expect(display).to_have_attribute('data-mode','playback')
        expect(display.locator('.radio-visualizer-status')).to_have_text('Indicador de reproducción')
        assert page.locator('#player-media iframe').is_visible()
        page.locator('#toggle-play').click();rest(page)
        assert page.evaluate('testYouTube.getPlayerState()')==2
        page.locator('#toggle-play').click()
        expect(display).to_have_attribute('data-state','playing')
        page.evaluate('testYouTube.config.events.onStateChange({data:3})');rest(page)
        page.evaluate('testYouTube.config.events.onStateChange({data:1})')
        expect(display).to_have_attribute('data-state','playing')
        page.evaluate('testYouTube.config.events.onError({data:101})');rest(page)
        assert page.evaluate('radioAudit')=={'microphones':0,'elementSources':0}
        page.locator('#player-close').click();rest(page)

        # Browsers lacking captureStream retain perfectly ordinary audio output.
        fallback=context.new_page()
        fallback.add_init_script("HTMLMediaElement.prototype.captureStream=undefined;HTMLMediaElement.prototype.mozCaptureStream=undefined;")
        fallback.on('pageerror',lambda error:errors.append(str(error)))
        fallback.goto(BASE_URL+'/')
        if fallback.locator('#consent-decline').is_visible():fallback.locator('#consent-decline').click()
        fallback.locator('#track-grid .cover-button').first.click()
        fallback.wait_for_function("document.querySelector('audio')?.currentTime>0")
        expect(fallback.locator('#radio-visualizer')).to_have_attribute('data-mode','playback')
        expect(fallback.locator('#radio-visualizer .radio-visualizer-status')).to_have_text('Indicador de reproducción')
        assert fallback.evaluate('radioAudit')=={'microphones':0,'elementSources':0}
        fallback.locator('#player-close').click();rest(fallback)
        assert not errors,errors
        context.close();browser.close()
    print('OK: real audio levels, honest video/unsupported-browser indicator, preserved playback and document, pause/buffering/hidden/reduced-motion rest, no microphone or audio rerouting, and four widths')


if __name__=='__main__':run()
