"""Pending video cannot be sold or request a camera; direct profiles escape input."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context

def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844});login_context(context)
        page=context.new_page();errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
        page.goto(BASE_URL+'/streamers');page.locator('#stream-unavailable').wait_for(state='visible')
        assert page.locator('#video-setup').is_visible()
        assert 'LIVEKIT_URL' in page.locator('#video-checks').inner_text()
        assert not page.locator('#start-camera').is_visible()
        assert page.locator('video').count()==0
        assert not any('livekit-client' in url for url in requests)
        page.locator('#channel-title').fill('My live channel')
        page.locator('#channel-bio').fill('<script>window.unwanted=true</script>')
        page.locator('#creator-paypal').fill('https://paypal.me/CreatorLink')
        page.locator('#owns-paypal').check();page.locator('#creator-form button').click()
        page.wait_for_function("document.querySelector('#stream-status').textContent==='Canal guardado.'")
        assert not page.evaluate('Boolean(window.unwanted)')
        page.goto(BASE_URL+'/account');page.locator('#member-panel').wait_for(state='visible')
        assert not page.locator('#pay-streamer').is_visible()
        assert page.locator('#pay-streamer').get_attribute('href') is None
        page.wait_for_function("document.querySelector('#streamer-plan-option').disabled === true")
        page.goto(BASE_URL+'/streamers');page.locator('#stream-unavailable').wait_for(state='visible')
        for width in [1440,768,390,320]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path='/tmp/maggy-streamers-preview.png',full_page=True)
        assert not errors,errors
        browser.close()
    print('OK: streamer preview; no video sale/camera before configuration; profile, PayPal declaration and 4 widths')

if __name__=='__main__':run()
