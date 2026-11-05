"""Public rendering survives crawler-blocked private APIs on mobile and desktop.

This models the resource restrictions reported by Search Console; it does not
assert that Google will index a page or display a particular search thumbnail.
"""
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


PUBLIC_READS={'/api/locale','/api/status','/api/search'}
TRACKS={
    'ARCHIVE':{'id':'archive_google_render','source':'ARCHIVE',
        'title':'Música pública de Archive','channel':'Artista de prueba','thumbnail':''},
    'AUDIUS':{'id':'audius_google_render','source':'AUDIUS',
        'title':'Música pública de Audius','channel':'Artista de prueba','thumbnail':''},
}


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        for width in [390,1440]:
            context=browser.new_context(viewport={'width':width,'height':900})
            page=context.new_page();blocked=[];allowed=[];script_responses=[];errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            def response_seen(response):
                if urlsplit(response.url).path=='/assets/mobile-shell.js':
                    script_responses.append((response.status,response.headers.get('content-type','')))
            page.on('response',response_seen)
            def resource(route):
                request=route.request;url=urlsplit(request.url)
                if request.method!='GET' or url.path not in PUBLIC_READS:
                    blocked.append(url.path);route.abort('blockedbyclient');return
                allowed.append(url.path)
                if url.path=='/api/search':
                    query=parse_qs(url.query);source=query.get('source',[''])[0]
                    tracks=[TRACKS[source]] if source in TRACKS and query.get('page',['1'])==['1'] else []
                    route.fulfill(json=tracks);return
                route.continue_()
            page.route('**/api/**',resource)
            page.goto(BASE_URL+'/')
            if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()

            # An unavailable account request must resolve to a free visitor,
            # rather than stopping the catalogue behind an account lookup.
            page.evaluate('async()=>{await window.MaggySession.ready}')
            assert page.evaluate('window.MaggySession.authenticated===false')
            assert '/api/account/me' in blocked
            expect(page.locator('.header-account')).to_have_text('Granel · entrar')
            for track in TRACKS.values():
                expect(page.locator('#track-grid .track-title').filter(has_text=track['title'])).to_be_visible()
            assert '/api/search' in allowed
            assert '/api/locale' in allowed
            assert '/api/status' in allowed

            # The reported script is served as JavaScript and really runs.
            assert script_responses and all(code==200 and 'javascript' in mime for code,mime in script_responses),script_responses
            expect(page.locator('#mobile-dock a')).to_have_count(5)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
            if width==390:
                expect(page.locator('#mobile-dock')).to_be_visible()
                page.locator('#mobile-menu').click()
                expect(page.locator('#mobile-nav')).to_be_visible()
                page.keyboard.press('Escape')
                expect(page.locator('#mobile-nav')).to_be_hidden()
                page.locator('.mobile-quick-search').click()
                expect(page.locator('#search-input')).to_be_focused()
            else:
                expect(page.locator('#mobile-dock')).to_be_hidden()
                expect(page.locator('#main-nav')).to_be_visible()
                page.locator('#main-nav [data-view="favorites"]').click()
                expect(page.locator('#section-title')).to_contain_text('favoritos')
                page.locator('#main-nav [data-view="discover"]').click()

            # Its real raster source remains reachable and decodes even while
            # private and unrelated dynamic resources cannot be fetched.
            photo=page.locator('#electronicama-image img')
            photo.scroll_into_view_if_needed();photo.evaluate('(image)=>image.decode()')
            assert photo.evaluate('(image)=>image.naturalWidth===1536&&image.naturalHeight===1024')
            assert not errors,errors
            context.close()
        browser.close()
    print('OK: crawler resource rules retain visitor fallback, public catalogue and brand image; mobile shell loads as JavaScript with working mobile/desktop navigation')


if __name__=='__main__':run()
