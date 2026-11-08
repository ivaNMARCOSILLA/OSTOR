"""Catalogue updates keep existing covers, focus and the current playback queue."""
import io
from pathlib import Path
import time
from urllib.parse import parse_qs, urlsplit
import wave

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


FIRST={'id':'audius_stability_first','source':'AUDIUS','title':'Primera canción estable',
       'channel':'Artista inicial','thumbnail':'https://covers.example.test/first.png'}
SECOND={'id':'archive_stability_second','source':'ARCHIVE','title':'Segunda canción disponible',
        'channel':'Artista posterior','thumbnail':'https://covers.example.test/second.png'}


def wait_callback(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'Expected the held second provider request'
        page.wait_for_timeout(20)


def assert_kept(page,focused):
    assert page.evaluate("""focused=>{
        const saved=window.catalogueStability;
        return saved.card.isConnected&&saved.image.isConnected&&saved.play.isConnected&&saved.favorite.isConnected
            &&document.querySelector('#track-grid .track-card')===saved.card
            &&saved.card.querySelector('img')===saved.image
            &&saved.card.querySelector('.cover-button')===saved.play
            &&saved.card.querySelector('.save-button')===saved.favorite
            &&document.activeElement===saved[focused]
            &&saved.detached.length===0;
    }""",focused),'A catalogue refresh replaced the existing card, cover or focused control'


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        page=context.new_page();held=[];errors=[];cover_reads=[];play_reads=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        png=(Path(__file__).resolve().parents[1]/'assets/app-icon-192.png').read_bytes()
        def cover(route):
            cover_reads.append(route.request.url)
            route.fulfill(body=png,content_type='image/png')
        page.route('https://covers.example.test/**',cover)
        def search(route):
            query=parse_qs(urlsplit(route.request.url).query)
            source=query.get('source',[''])[0];number=query.get('page',['1'])[0]
            if number!='1':route.fulfill(json=[]);return
            if source=='AUDIUS':route.fulfill(json=[FIRST]);return
            if source=='ARCHIVE':held.append(route);return
            route.fulfill(json=[])
        page.route('**/api/search?*',search)
        pcm=io.BytesIO()
        with wave.open(pcm,'wb') as audio:
            audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000)
            audio.writeframes(b'\x00\x00'*8000*30)
        def play(route):
            play_reads.append(urlsplit(route.request.url).path)
            route.fulfill(body=pcm.getvalue(),content_type='audio/wav')
        page.route('**/api/play/*',play)
        page.goto(BASE_URL+'/')
        if page.locator('#consent-decline').is_visible():page.locator('#consent-decline').click()
        card=page.locator('#track-grid .track-card').first
        expect(card.locator('.track-title')).to_have_text(FIRST['title'])
        expect(page.locator('#track-grid .track-card')).to_have_count(1)
        wait_callback(page,lambda:bool(held))
        card.locator('img').evaluate('(image)=>image.decode()')
        page.locator('[data-site-language]').first.select_option('en')
        expect(page.locator('#section-subtitle')).to_contain_text('Timeless songs')
        card.locator('.cover-button').focus()
        page.evaluate("""()=>{
            const card=document.querySelector('#track-grid .track-card');
            const saved=window.catalogueStability={card,image:card.querySelector('img'),
                play:card.querySelector('.cover-button'),favorite:card.querySelector('.save-button'),detached:[]};
            saved.observer=new MutationObserver(records=>{
                for(const record of records)for(const removed of record.removedNodes){
                    if([saved.card,saved.image,saved.play,saved.favorite].some(node=>removed===node||removed.contains?.(node)))saved.detached.push(removed.nodeName);
                }
            });
            saved.observer.observe(document.querySelector('#track-grid'),{childList:true,subtree:true});
        }""")
        before_first_cover=cover_reads.count(FIRST['thumbnail'])
        assert before_first_cover==1,cover_reads
        held.pop(0).fulfill(json=[SECOND])
        expect(page.locator('#track-grid .track-card')).to_have_count(2)
        expect(page.locator('#search-button')).to_be_enabled()
        page.wait_for_timeout(50)
        assert_kept(page,'play')
        expect(page.locator('#section-subtitle')).to_contain_text('Timeless songs')

        # Account refresh notifications must not detach a correctly rendered
        # card or reload its cover when its data and order have not changed.
        page.evaluate("""()=>{for(let i=0;i<6;i++)window.dispatchEvent(new CustomEvent('maggy:access-changed',{detail:{active:true,premium:false}}));}""")
        page.wait_for_timeout(50)
        assert_kept(page,'play')
        assert cover_reads.count(FIRST['thumbnail'])==before_first_cover,cover_reads
        expect(page.locator('#section-subtitle')).to_contain_text('Timeless songs')

        # Favorite feedback updates the existing control and retains its focus.
        favorite=card.locator('.save-button')
        favorite.click();expect(favorite).to_have_class('save-button saved')
        assert_kept(page,'favorite')
        favorite.click();expect(favorite).to_have_class('save-button')
        assert_kept(page,'favorite')
        assert cover_reads.count(FIRST['thumbnail'])==before_first_cover,cover_reads
        assert not play_reads,'Rendering and favorites must not start playback'

        # The first card was created before the second provider returned. Its
        # click handler must still use the latest list as its playback queue.
        card.locator('.cover-button').click()
        expect(page.locator('#player-title')).to_have_text(FIRST['title'])
        expect(page.locator('#next-track')).to_be_enabled()
        page.wait_for_function("document.querySelector('audio')?.currentTime>0")
        page.locator('#next-track').click()
        expect(page.locator('#player-title')).to_have_text(SECOND['title'])
        page.wait_for_function("document.querySelector('audio')?.currentTime>0")
        assert '/api/play/'+FIRST['id'] in play_reads,play_reads
        assert '/api/play/'+SECOND['id'] in play_reads,play_reads
        assert page.evaluate('window.catalogueStability.detached.length')==0
        expect(page.locator('#section-subtitle')).to_contain_text('Timeless songs')
        assert not errors,errors
        page.locator('#player-close').click()
        context.close();browser.close()
    print('OK: provider append and account refresh preserve card/image/focus, favorites update in place, locale survives and the retained card plays the latest queue')


if __name__=='__main__':run()
