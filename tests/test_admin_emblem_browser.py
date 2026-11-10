"""Public emblems update by deployment version without losing forms or media."""
from pathlib import Path
import time
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


SVG='''<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><circle cx="10" cy="10" r="8" fill="#e2c389"/></svg>'''
HTML='''<!doctype html><html><head>
<meta name="electronicama-version" content="9.29.5">
<link id="icon" rel="icon" href="/assets/favicon.svg?keep=icon">
</head><body>
<form><input id="draft" value="Mi borrador"><input id="password" type="password" value="private-browser-fixture"></form>
<img id="poster-a" width="32" height="48" src="/assets/electronicama-social.png?v=9.29.5&amp;keep=poster#art">
<img id="poster-b" width="32" height="48" src="/assets/electronicama-social.png?v=9.29.5&amp;keep=poster#art">
<img id="badge" width="20" height="20" src="/assets/founder-badge.svg?keep=badge">
<img id="broken" width="20" height="20" src="/assets/broken-emblem.svg?v=9.29.5">
<img id="private" width="20" height="20" src="/api/emblem-fixture.svg?token=private">
<img id="external" width="20" height="20" src="https://outside.example/assets/emblem.svg">
<img id="data" width="20" height="20" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='20' height='20'%3E%3C/svg%3E">
<audio id="audio" preload="none" src="/assets/audio-fixture.wav?keep=sound"></audio>
<video id="video" preload="none" src="/assets/video-fixture.webm?keep=video"></video>
<div style="height:12000px"></div><img id="lazy" loading="lazy" width="20" height="20" src="/assets/lazy-emblem.svg?keep=lazy">
</body></html>'''


def callbacks(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'expected fixture request was not intercepted'
        page.wait_for_timeout(20)


def run():
    png=(Path(__file__).resolve().parents[1]/'assets/electronicama-social.png').read_bytes()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':900,'height':700});errors=[];navigations=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
        state={'version':'9.29.5','broken':False,'hold_health':False,'hold_badge':False}
        asset_requests=[];health_requests=[];held_health=[];held_badge=[]
        page.route('**/admin-emblem-harness',lambda route:route.fulfill(content_type='text/html',body=HTML))
        def health(route):
            health_requests.append(route.request.url)
            if state['hold_health']:
                state['hold_health']=False;held_health.append(route);return
            route.fulfill(json={'version':state['version']},headers={'Cache-Control':'no-store'})
        def assets(route):
            parsed=urlparse(route.request.url)
            if parsed.path.endswith('.js'):
                route.continue_();return
            asset_requests.append(route.request.url)
            version=parse_qs(parsed.query).get('v',[''])[0]
            if parsed.path=='/assets/founder-badge.svg' and state['hold_badge'] and version==state['version']:
                state['hold_badge']=False;held_badge.append(route);return
            if parsed.path=='/assets/broken-emblem.svg' and state['broken'] and version=='9.29.7':
                route.fulfill(status=404,body='not available');return
            if parsed.path.endswith('.png'):
                route.fulfill(content_type='image/png',body=png,headers={'Cache-Control':'public,max-age=3600'})
            else:
                route.fulfill(content_type='image/svg+xml',body=SVG,headers={'Cache-Control':'public,max-age=3600'})
        page.route('**/health',health)
        page.route('**/assets/**',assets)
        page.route('**/api/emblem-fixture.svg?*',lambda route:route.fulfill(content_type='image/svg+xml',body=SVG))
        page.route('https://outside.example/assets/emblem.svg',lambda route:route.fulfill(content_type='image/svg+xml',body=SVG))
        page.goto(BASE_URL+'/admin-emblem-harness')
        page.wait_for_function("[...document.querySelectorAll('img:not([loading=lazy])')].every(image=>image.complete&&image.naturalWidth>0)")
        page.wait_for_load_state('networkidle')
        page.evaluate('''async()=>{
            const {refreshAdminEmblems}=await import('/assets/admin-emblems.js');
            window.refreshAdminEmblems=refreshAdminEmblems;window.probeCount=0;
            const OriginalImage=window.Image;
            window.Image=new Proxy(OriginalImage,{construct(target,args){window.probeCount++;return Reflect.construct(target,args);}});
        }''')
        untouched=page.evaluate("Object.fromEntries(['private','external','data','audio','video'].map(id=>[id,document.getElementById(id).getAttribute('src')]))")
        original_assets=len(asset_requests)
        assert page.evaluate('refreshAdminEmblems()')=={'version':'9.29.5','changed':0,'failed':0}
        assert len(asset_requests)==original_assets,'an unchanged deployment must not fetch images again'
        assert page.evaluate('probeCount')==0

        # A manual refresh queued behind a health request must survive, and two
        # normal callers share the in-flight job rather than issuing two reads.
        state['hold_health']=True;before=len(health_requests)
        page.evaluate('''()=>{
            window.pendingRefresh=refreshAdminEmblems();
            window.sharedRefresh=pendingRefresh===refreshAdminEmblems();
            refreshAdminEmblems({force:true});
            pendingRefresh.then(value=>window.pendingResult=value);
        }''')
        callbacks(page,lambda:bool(held_health))
        held_health.pop().fulfill(json={'version':state['version']})
        page.wait_for_function('window.pendingResult!==undefined')
        assert page.evaluate('sharedRefresh')
        assert len(health_requests)==before+2
        assert page.evaluate('pendingResult.failed')==0
        first_token=page.locator('#poster-a').evaluate("e=>new URL(e.src).searchParams.get('refresh')")
        assert first_token
        # A component can recreate the poster even before the next deployment.
        # It must inherit the manual refresh revision on the following cycle.
        page.locator('#poster-a').evaluate("e=>{const next=e.cloneNode();next.setAttribute('src','/assets/electronicama-social.png?v=9.29.5&keep=poster#art');e.replaceWith(next)}")
        before_probes=page.evaluate('probeCount')
        assert page.evaluate('refreshAdminEmblems()')=={'version':'9.29.5','changed':1,'failed':0}
        assert page.locator('#poster-a').evaluate("e=>new URL(e.src).searchParams.get('refresh')")==first_token
        assert page.evaluate('probeCount')-before_probes==1

        # One decoded image updates both poster nodes. The distant lazy emblem
        # gets a new URL without a forced preload or a forced scroll.
        state['version']='9.29.6';before_probes=page.evaluate('probeCount')
        result=page.evaluate('refreshAdminEmblems()')
        assert result['version']=='9.29.6' and result['failed']==0 and result['changed']==6
        assert page.evaluate('probeCount')-before_probes==4,'duplicate posters must share a single preload'
        for selector in ['#poster-a','#poster-b','#badge','#broken','#lazy']:
            assert page.locator(selector).evaluate("e=>new URL(e.src).searchParams.get('v')")=='9.29.6'
        assert page.locator('#poster-a').evaluate("e=>new URL(e.src).searchParams.get('keep')")=='poster'
        assert page.locator('#poster-a').evaluate('e=>new URL(e.src).hash')=='#art'
        assert page.locator('#icon').evaluate("e=>new URL(e.href).searchParams.get('keep')")=='icon'
        assert page.locator('#icon').evaluate("e=>new URL(e.href).searchParams.get('v')")=='9.29.6'
        assert not any('/lazy-emblem.svg' in url for url in asset_requests),'a distant lazy image must not be preloaded'
        before=len(asset_requests);before_probes=page.evaluate('probeCount')
        assert page.evaluate('refreshAdminEmblems()')=={'version':'9.29.6','changed':0,'failed':0}
        assert len(asset_requests)==before and page.evaluate('probeCount')==before_probes
        page.locator('#draft').fill('Mi borrador sigue aquí')
        page.locator('#password').fill('unsaved-fixture-only')
        result=page.evaluate('refreshAdminEmblems({force:true})')
        assert result['failed']==0 and result['changed']==6
        assert page.locator('#poster-a').evaluate("e=>new URL(e.src).searchParams.get('refresh')")!=first_token

        # A missing replacement preserves the displayed image and retries only
        # that failed resource when the same deployment becomes available.
        old_broken=page.locator('#broken').get_attribute('src')
        state.update(version='9.29.7',broken=True)
        result=page.evaluate('refreshAdminEmblems()')
        assert result['failed']==1 and result['changed']==5
        expect(page.locator('#broken')).to_have_attribute('src',old_broken)
        assert page.locator('#broken').evaluate('e=>e.complete&&e.naturalWidth>0')
        correct_poster=page.locator('#poster-a').get_attribute('src');before=len(asset_requests)
        state['broken']=False;result=page.evaluate('refreshAdminEmblems()')
        assert result=={'version':'9.29.7','changed':1,'failed':0}
        assert page.locator('#poster-a').get_attribute('src')==correct_poster
        assert asset_requests[before:] and all('/broken-emblem.svg' in url for url in asset_requests[before:])

        # An older preload may not overwrite a component's newer source.
        state.update(version='9.29.8',hold_badge=True)
        page.evaluate('void refreshAdminEmblems().then(value=>window.raceResult=value)')
        callbacks(page,lambda:bool(held_badge))
        page.locator('#badge').evaluate("e=>e.setAttribute('src','/assets/manual-replacement.svg?v=manual')")
        held_badge.pop().fulfill(content_type='image/svg+xml',body=SVG)
        page.wait_for_function('window.raceResult!==undefined')
        expect(page.locator('#badge')).to_have_attribute('src','/assets/manual-replacement.svg?v=manual')

        # A disconnected node is a different race: account refresh can replace
        # an entire badge while its old image is preloading. The next cycle of
        # the SAME deployment must update the replacement without reloading
        # already-correct images or advancing the immutable page baseline.
        page.locator('#badge').evaluate("e=>e.setAttribute('src','/assets/founder-badge.svg?v=9.29.5&keep=badge')")
        state.update(version='9.29.9',hold_badge=True)
        page.evaluate('void refreshAdminEmblems().then(value=>window.replacedResult=value)')
        callbacks(page,lambda:bool(held_badge))
        page.locator('#badge').evaluate("e=>{const next=e.cloneNode();next.setAttribute('src','/assets/founder-badge.svg?v=9.29.5&keep=badge');e.replaceWith(next)}")
        held_badge.pop().fulfill(content_type='image/svg+xml',body=SVG)
        page.wait_for_function('window.replacedResult!==undefined')
        expect(page.locator('#badge')).to_have_attribute('src','/assets/founder-badge.svg?v=9.29.5&keep=badge')
        correct_poster=page.locator('#poster-a').get_attribute('src');before_probes=page.evaluate('probeCount')
        assert page.evaluate('refreshAdminEmblems()')=={'version':'9.29.9','changed':1,'failed':0}
        assert page.locator('#badge').evaluate("e=>new URL(e.src).searchParams.get('v')")=='9.29.9'
        assert page.locator('#poster-a').get_attribute('src')==correct_poster
        assert page.evaluate('probeCount')-before_probes==1
        before_probes=page.evaluate('probeCount')
        assert page.evaluate('refreshAdminEmblems()')=={'version':'9.29.9','changed':0,'failed':0}
        assert page.evaluate('probeCount')==before_probes

        # The deadline includes reading JSON after headers arrive. This fixture
        # returns a real Response whose body deliberately never finishes.
        page.clock.install()
        page.evaluate('''()=>{
            window.originalFetch=window.fetch;
            window.fetch=(url,options)=>url==='/health'?Promise.resolve(new Response(new ReadableStream({start(controller){
                window.healthBodyController=controller;controller.enqueue(new TextEncoder().encode('{"version":'));
            }}),{headers:{'Content-Type':'application/json'}})):originalFetch(url,options);
            window.timeoutResult=null;
            void refreshAdminEmblems().then(value=>window.timeoutResult=value,error=>window.timeoutResult={error:error.message});
        }''')
        page.clock.fast_forward(8500)
        page.wait_for_function('Boolean(window.timeoutResult?.error)')
        assert 'demasiado' in page.evaluate('timeoutResult.error')
        page.evaluate('window.fetch=originalFetch;healthBodyController.close()')
        result=page.evaluate('refreshAdminEmblems()')
        assert result['version']==state['version'] and result['failed']==0
        assert page.evaluate("Object.fromEntries(['private','external','data','audio','video'].map(id=>[id,document.getElementById(id).getAttribute('src')]))")==untouched
        expect(page.locator('#draft')).to_have_value('Mi borrador sigue aquí')
        expect(page.locator('#password')).to_have_value('unsaved-fixture-only')
        assert len(navigations)==1,navigations
        assert not errors,errors
        browser.close()
    print('OK: deployment and manual emblem refresh, deduplicated preloads, lazy images, retry without losing old art, stale source protection, body timeout recovery, untouched forms/media and no page reload')


if __name__=='__main__':run()
