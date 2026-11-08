"""Editorial music memories search real providers without inventing playback history."""
import time
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error, expect, sync_playwright

from browser_support import BASE_URL


FEATURE_QUERY='Andy & Lucas Son de amores'


def wait_callback(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'Expected the selected artist search'
        page.wait_for_timeout(20)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':900})
        page=context.new_page();queries=[];playback=[];errors=[];held=[]
        state={'youtube':'error','hold_query':None}
        page.on('pageerror',lambda error:errors.append(str(error)))
        def request_seen(request):
            url=urlsplit(request.url)
            if url.path.startswith('/api/play/') or 'youtube.com/iframe_api' in request.url or 'youtube-nocookie.com/embed/' in request.url:
                playback.append(request.url)
        page.on('request',request_seen)
        def search(route):
            url=urlsplit(route.request.url);params=parse_qs(url.query)
            query=params.get('q',[''])[0];source=params.get('source',[''])[0]
            number=int(params.get('page',['1'])[0]);queries.append((query,source,route.request.url))
            if source=='YOUTUBE':
                if query==state['hold_query']:
                    state['hold_query']=None;held.append(route);return
                if state['youtube']=='error':
                    route.fulfill(status=503,json={'error':'YouTube no está disponible temporalmente.'});return
                if state['youtube']=='empty':route.fulfill(json=[]);return
                route.fulfill(json=[{'id':'youtube_abcdefghijk','video_id':'abcdefghijk',
                    'source':'YOUTUBE','title':query+' · Resultado de prueba',
                    'channel':'Canal de prueba','thumbnail':''}]);return
            if source=='MIX':
                route.fulfill(json=[{'id':'commons_memory','source':'COMMONS',
                    'title':'Grabación libre de prueba','channel':'Archivo de prueba'}] if number==1 else []);return
            route.fulfill(json=[{'id':source.lower()+'_memory','source':source,
                'title':'Selección inicial de prueba','channel':'Archivo de prueba'}] if number==1 else [])
        page.route('**/api/search?*',search)
        page.goto(BASE_URL+'/')
        page.locator('#consent-decline').click()
        expect(page.locator('#track-grid .track-card').first).to_be_visible()
        expect(page.locator('#search-input')).to_have_value('pop español')

        memory=page.locator('#music-memory')
        expect(memory).to_be_visible()
        expect(memory.locator('.music-memory-era')).to_have_count(5)
        expect(memory.locator('.music-memory-timeline button[data-query]')).to_have_count(10)
        assert page.evaluate("document.querySelector('#library').compareDocumentPosition(document.querySelector('#music-memory'))&Node.DOCUMENT_POSITION_FOLLOWING")
        assert page.evaluate("document.querySelector('#music-memory').compareDocumentPosition(document.querySelector('#momentos'))&Node.DOCUMENT_POSITION_FOLLOWING")
        for artist in memory.locator('.music-memory-timeline button[data-query]').all():
            expect(artist).to_have_attribute('data-search-source','YOUTUBE')
            expect(artist.locator('[translate="no"]')).to_have_count(1)
        fallback=page.locator('#youtube-search-fallback')
        expect(fallback).to_be_hidden()
        for width in [320,390,768,1440]:
            page.set_viewport_size({'width':width,'height':900})
            memory.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
            for control in memory.locator('button[data-query]').all():
                box=control.bounding_box()
                assert box and box['height']>=43.5,(width,box)
                assert box['x']>=-1 and box['x']+box['width']<=width+1,(width,box)
            if width==390:memory.screenshot(path='/tmp/music-memory-mobile.png',style='.topbar,#mobile-dock{visibility:hidden!important}')
            if width==1440:memory.screenshot(path='/tmp/music-memory-desktop.png',style='.topbar,#mobile-dock{visibility:hidden!important}')

        # An artist is an explicit YouTube search, even after listening sources
        # were switched to Mezcla. The ampersand must survive URL encoding.
        page.locator('#source-filters [data-source="MIX"]').click()
        expect(page.locator('#mix-intro')).to_be_visible()
        memory.locator('.music-memory-feature button[data-query]').click()
        expect(page.locator('#search-input')).to_have_value(FEATURE_QUERY)
        expect(page.locator('#source-filters [data-source="YOUTUBE"]')).to_have_attribute('aria-pressed','true')
        expect(fallback).to_be_visible()
        featured=next(url for query,source,url in reversed(queries) if query==FEATURE_QUERY and source=='YOUTUBE')
        assert '%26' in featured,featured
        target=urlsplit(fallback.get_attribute('href'))
        assert target.scheme=='https' and target.netloc=='www.youtube.com' and target.path=='/results',target
        assert parse_qs(target.query)['search_query']==[FEATURE_QUERY]
        assert fallback.get_attribute('target')=='_blank'
        assert {'noopener','noreferrer'}<=set(fallback.get_attribute('rel').split())
        assert not playback,'Choosing an artist must not start a player or contact the iframe provider'

        # Successful and empty provider responses give different, honest paths.
        state['youtube']='success'
        memory.locator('[data-query="Alejandro Sanz"]').click()
        expect(page.locator('#track-grid')).to_contain_text('Alejandro Sanz · Resultado de prueba')
        expect(fallback).to_be_hidden()
        state['youtube']='empty'
        memory.locator('[data-query="Amaral"]').click()
        expect(fallback).to_be_visible()
        assert parse_qs(urlsplit(fallback.get_attribute('href')).query)['search_query']==['Amaral']
        page.locator('#source-filters [data-source="MIX"]').click()
        expect(page.locator('#mix-intro')).to_be_visible();expect(fallback).to_be_hidden()
        state['youtube']='success'
        memory.locator('[data-query="Mecano"]').click()
        expect(page.locator('#track-grid')).to_contain_text('Mecano · Resultado de prueba')
        expect(fallback).to_be_hidden()

        # A late failed request cannot resurrect an old artist's external link.
        state['hold_query']=FEATURE_QUERY
        memory.locator('.music-memory-feature button[data-query]').click()
        wait_callback(page,lambda:bool(held))
        memory.locator('[data-query="Mecano"]').click()
        expect(page.locator('#track-grid')).to_contain_text('Mecano · Resultado de prueba')
        for route in held:
            try:route.fulfill(status=503,json={'error':'Respuesta antigua de prueba.'})
            except Error:pass  # Chromium may already have cancelled this request.
        page.wait_for_timeout(50)
        expect(page.locator('#search-input')).to_have_value('Mecano');expect(fallback).to_be_hidden()

        # Existing style shortcuts retain the chosen source. Searches alone
        # must never populate the personal history with editorial suggestions.
        page.locator('#quick-style-picker summary').click()
        page.locator('#quick-searches [data-query="techno"]').click()
        expect(page.locator('#track-grid')).to_contain_text('techno · Resultado de prueba')
        assert any(query=='techno' and source=='YOUTUBE' for query,source,_ in queries)
        page.locator('#main-nav [data-view="history"]').click()
        expect(page.locator('#track-grid .empty-state')).to_contain_text('TODAVÍA NO HAY HISTORIAL')
        assert not playback,'Artist and style searches must require a separate playback gesture'
        assert not errors,errors
        context.close();browser.close()
    print('OK: nostalgic music choices, encoded artist queries, source changes, provider failure/empty recovery, stale responses, no autoplay or invented history, and four responsive widths')


if __name__=='__main__':run()
