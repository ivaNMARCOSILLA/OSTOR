"""The storefront is public; all listening and personal actions require unlock."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page();errors=[];requests=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.url))
        records=[{'id':'archive_test','title':'Demo preview','channel':'Artist','source':'ARCHIVE','locked':True}]
        page.route('**/api/search?*',lambda route:route.fulfill(json=records))
        page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
        page.locator('.track-card').wait_for()
        assert page.locator('#preview-banner').is_visible()
        assert page.locator('#mas-musica .music-web-card').count() == 7
        page.locator('#search-input').fill('Björk & jazz')
        for selector, host, parameter in [('#soundcloud-search','soundcloud.com','q'),('#youtube-search','www.youtube.com','search_query')]:
            from urllib.parse import urlparse,parse_qs
            link=urlparse(page.locator(selector).get_attribute('href'))
            assert link.hostname == host and parse_qs(link.query)[parameter] == ['Björk & jazz']
        assert not any('soundcloud.com' in url or 'youtube.com' in url for url in requests)
        assert page.locator('iframe').count() == 0
        assert page.locator('#spotify-premium a').get_attribute('href') == 'https://www.spotify.com/es/premium/'
        assert 'no incluye Spotify Premium' in page.locator('#spotify-premium').inner_text()
        assert page.locator('#spotify-premium a[href*="paypal"]').count() == 0
        page.locator('.cover-button').click();page.locator('#unlock-dialog').wait_for(state='visible')
        assert '14 días' in page.locator('#unlock-dialog').inner_text()
        assert page.locator('audio').count()==0
        assert not any('/api/resolve/' in url or '/api/play/' in url for url in requests)
        page.locator('#unlock-close').click()
        page.locator('.save-button').click();assert page.locator('#unlock-dialog').is_visible()
        assert page.evaluate("localStorage.getItem('maggy_member_visitor_electronicama_v7_favorites')") is None
        page.locator('#unlock-close').click()
        page.locator('#channel-name').fill('Try without payment');page.locator('#channel-form button').click()
        assert page.locator('#unlock-dialog').is_visible()
        assert page.locator('.channel-card').count()==0
        page.locator('#unlock-close').click()
        for width in [1440,390,320]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path='docs/maggy-preview.png',full_page=True)
        assert not errors,errors
        browser.close()
    print('OK: public catalogue visible; playback/favorites/channels open payment dialog; no audio or resolution before paying; mobile layout')


if __name__=='__main__':run()
