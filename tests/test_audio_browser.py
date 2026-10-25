"""Audio playback, legacy provider filtering, local library, and responsive UI."""
import io
import json
import wave
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL,login_context


def run():
    valid=[{'id':'archive_test','title':'Orbital test','channel':'Pilot','source':'ARCHIVE','stream_url':'https://test.invalid/music.wav'}, {'id':'audius_test','title':'Aurora test','channel':'Pilot','source':'AUDIUS','stream_url':'https://test.invalid/music.wav'}]
    removed=[{'id':'youtube_abcdefghijk','title':'Removed video','source':'YOUTUBE','video_id':'abcdefghijk'},{'id':'jamendo_123','title':'Removed track','source':'JAMENDO','stream_url':'https://test.invalid/retired.mp3'}]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000});user=login_context(context)
        page=context.new_page();errors=[];requests=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:requests.append(request.url))
        prefix='maggy_member_'+user['id']+'_'
        page.add_init_script("""const entries = %s;
            for (const [key,value] of entries) if (localStorage.getItem(key)===null) localStorage.setItem(key,JSON.stringify(value));
        """ % json.dumps([[prefix+'electronicama_v7_favorites',removed],[prefix+'maggy_channels_v1',[{'name':'Legacy','tracks':removed}]]]))

        audio=io.BytesIO()
        with wave.open(audio,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x00\x00'*80000)
        page.route('https://test.invalid/music.wav',lambda route:route.fulfill(body=audio.getvalue(),content_type='audio/wav',headers={'Access-Control-Allow-Origin':'*'}))
        def serve_audio(route):
            # Exercise the automatic alternate connection, then real native decoding.
            if 'retry=1' not in route.request.url:
                route.fulfill(status=503,body='Temporary provider outage')
            else:
                route.fulfill(body=audio.getvalue(),content_type='audio/wav')
        page.route('**/api/play/*',serve_audio)
        mix=[{'id':'commons_123','title':'Libre one','channel':'Composer','source':'COMMONS','license':'CC BY 4.0','attribution':'Composer','page_url':'https://commons.wikimedia.org/?curid=123'}, {'id':'commons_456','title':'Libre two','channel':'Composer','source':'COMMONS','license':'Public domain','attribution':'Composer'}]
        page.route('**/api/search?*',lambda route:route.fulfill(json=mix if 'source=MIX' in route.request.url else valid+removed))
        page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
        page.locator('.track-card').first.wait_for()
        assert page.locator('.track-card').count()==2
        assert page.locator('iframe').count()==0
        assert page.locator('.channel-card button').first.is_disabled()
        page.locator('[data-source="AUDIUS"]').click();assert page.locator('.track-card').count()==1
        page.locator('[data-source="ALL"]').click()
        page.locator('.track-card .save-button').first.click()
        page.locator('#profile-name').fill('Pilot');page.locator('#profile-form button').click()
        page.locator('#channel-name').fill('My orbit');page.locator('#channel-form button').click()
        assert page.locator('.channel-card').count()==2
        page.locator('.channel-card').last.locator('button').first.click()
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0")
        assert any('/api/play/archive_test?retry=1' in url for url in requests)
        assert not any('/api/resolve/' in url for url in requests)
        page.evaluate("document.querySelector('audio').dataset.reused = 'yes'")
        page.locator('.channel-card').last.locator('button').first.click()
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0")
        assert page.locator('audio').get_attribute('data-reused') == 'yes'

        page.set_viewport_size({'width':390,'height':844})
        page.locator('#player-expand').click()
        assert page.locator('#player-expand').get_attribute('aria-expanded')=='true'
        assert page.locator('#player-extra').is_visible()
        assert page.locator('#toggle-play').bounding_box()['height']>=60
        page.locator('#sleep-timer').select_option('15')
        assert '15 min' in page.locator('#sleep-status').inner_text()
        page.locator('#sleep-timer').select_option('0')
        page.locator('#seek-back').click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        page.screenshot(path='/tmp/maggy-iphone-player.png')
        page.locator('#player-expand').click()
        page.locator('#toggle-play').click();page.wait_for_function("document.querySelector('audio')?.paused")
        page.set_viewport_size({'width':1440,'height':1000})
        page.locator('[data-view="history"]').first.click();assert page.locator('.track-card').count()==1
        page.locator('[data-view="favorites"]').first.click();assert page.locator('.track-card').count()==1
        page.reload();page.locator('.track-card').first.wait_for()
        assert page.locator('#profile-name').input_value()=='Pilot'
        assert page.locator('.channel-card').count()==2
        page.locator('[data-source="MIX"]').click()
        page.wait_for_function("document.querySelectorAll('#track-grid .track-credit').length === 2")
        assert page.locator('#track-grid').get_attribute('class').endswith('mix-list')
        assert page.locator('.track-card .source-tag').all_text_contents()==['MEZCLA · COMMONS','MEZCLA · COMMONS']
        page.locator('#play-mix').click()
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0")
        assert page.locator('#player-title').inner_text()=='Libre one'
        page.evaluate("document.querySelector('audio').currentTime = 9.9")
        page.wait_for_function("document.querySelector('#player-title').textContent === 'Libre two'")
        page.wait_for_function("document.querySelector('audio')?.currentTime > 0")
        assert page.locator('video,iframe').count()==0
        assert page.locator('#track-grid img[alt="Logo de Maggy"]').count()==2
        page.locator('#player-close').click()
        for width in [1440,768,390,320]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
        page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path='docs/maggy-desktop.png',full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path='docs/maggy-mobile.png',full_page=True)
        assert not any('youtube' in url.lower() or 'jamendo' in url.lower() or 'retired.mp3' in url for url in requests)
        assert not errors,errors
        browser.close()
    print('OK: Archive/Audius audio, controls, favorites, channels, legacy entries hidden, no retired-provider requests, 4 screen widths')


if __name__=='__main__':run()
