"""Sparse floral accents preserve navigation, account states and live controls."""
import secrets

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context
from test_stream_continuity_browser import SDK


WIDTHS=[320,390,768,1440]
FLOWERS='.botanical-interface .botanical-flower'


def settle(page):
    # The ornament component coalesces account changes into the next frame.
    page.evaluate('() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel=page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button',name='Solo necesarias',exact=True).click()


def check_flowers(page, width):
    page.set_viewport_size({'width':width,'height':900})
    settle(page)
    flowers=page.locator(FLOWERS)
    expect(flowers.first).to_be_visible()
    count=flowers.count()
    assert 1<=count<=6,(page.url,width,count)
    expect(page.locator(FLOWERS+':visible')).to_have_count(count)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
    issues=page.evaluate('''() => {
        const groups=[...document.querySelectorAll('.botanical-interface')],issues=[];
        const interactive='a[href],button,input,select,textarea,[role="button"],[tabindex]:not([tabindex="-1"])';
        const targets=[...document.querySelectorAll(interactive)].filter(e=>e.getClientRects().length
            && !e.closest('[hidden],.hidden,[aria-hidden="true"]')
            && !e.closest('details:not([open])')
            && !e.closest('#mobile-dock,.topbar,.platform-header,.player'));
        for(const group of groups){
            const box=group.getBoundingClientRect(),style=getComputedStyle(group);
            if(group.getAttribute('aria-hidden')!=='true')issues.push('ornament announced to assistive technology');
            if(group.querySelector(interactive)||group.tabIndex>=0)issues.push('focusable decorative content');
            if(group.closest('a,button,form,#live-player,#live-comments,#mobile-nav,#mobile-dock,.player'))issues.push('ornament in an interactive workspace');
            if(style.position==='fixed'||style.position==='absolute')issues.push('ornament overlays normal flow');
            if(style.pointerEvents!=='none')issues.push('ornament captures pointer events');
            if(box.height>65)issues.push('oversized decorative strip');
            if(box.left<-2||box.right>innerWidth+2)issues.push('decorative strip outside viewport');
            for(const flower of group.querySelectorAll('.botanical-flower')){
                const r=flower.getBoundingClientRect();
                if(flower.tagName==='IMG'&&flower.getAttribute('alt')!=='')issues.push('decorative image has a name');
                if(flower.tabIndex>=0)issues.push('flower in tab order');
                if(r.left<box.left-2||r.right>box.right+2||r.top<box.top-2||r.bottom>box.bottom+2)issues.push('flower escapes reserved strip');
                for(const target of targets){
                    const t=target.getBoundingClientRect();
                    if(Math.min(r.right,t.right)-Math.max(r.left,t.left)>2
                        && Math.min(r.bottom,t.bottom)-Math.max(r.top,t.top)>2)
                        issues.push('flower overlaps control '+(target.id||target.tagName+'.'+target.className)+' in '+group.dataset.botanicalAnchor);
                }
            }
        }
        return issues;
    }''')
    assert not issues,(page.url,width,issues)


def assert_no_duplicates(page):
    count=page.locator(FLOWERS).count()
    page.evaluate('''() => {
        window.botanicalNodesBeforeRefresh=[...document.querySelectorAll('.botanical-interface .botanical-flower')];
        for(let i=0;i<5;i++){
            window.dispatchEvent(new Event('ol:account-refreshed'));
            window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}));
        }
    }''')
    settle(page)
    expect(page.locator(FLOWERS)).to_have_count(count)
    assert page.evaluate("[...document.querySelectorAll('.botanical-interface .botanical-flower')].every((flower,index)=>flower===window.botanicalNodesBeforeRefresh[index])"),'unchanged refresh replaced floral accents'


def check_stage_controls(page, width):
    page.set_viewport_size({'width':width,'height':900})
    page.locator('#live-stage').scroll_into_view_if_needed()
    issues=page.locator('#live-stage>.heading').evaluate('''heading => {
        const issues=[],bounds=heading.getBoundingClientRect();
        const elements=[...heading.querySelectorAll('.live-stage-heading,#mobile-live-controls,#leave-room')].filter(e=>e.getClientRects().length);
        for(const element of elements){
            const box=element.getBoundingClientRect();
            if(box.left<bounds.left-1||box.right>bounds.right+1)issues.push('heading item escapes workspace');
            if(element.tagName==='BUTTON'&&box.height<44)issues.push('small live touch target');
        }
        for(let i=0;i<elements.length;i++)for(let j=i+1;j<elements.length;j++){
            const a=elements[i].getBoundingClientRect(),b=elements[j].getBoundingClientRect();
            if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>1
                && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>1)issues.push('live title and controls collide');
        }
        return issues;
    }''')
    assert not issues,(width,issues)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
    expect(page.locator('#live-stage .botanical-interface')).to_have_count(0)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':900})
        page=context.new_page();errors=[];queries=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        def search(route):
            queries.append(route.request.url)
            route.fulfill(json=[{'id':'archive_botanical_'+str(i),'source':'ARCHIVE','title':'Una canción para descubrir '+str(i),'channel':'Artista de prueba'} for i in range(3)])
        page.route('**/api/search?*',search)
        page.goto(BASE_URL+'/');close_preferences(page)
        page.locator('.track-card').first.wait_for()
        expect(page.locator('#hero-title')).to_contain_text('Flores')
        expect(page.locator('#hero-title')).to_contain_text('Flores Amapolda')
        expect(page.locator('#ol-intro-title')).to_contain_text('Flores')
        expect(page.locator('#ol-intro-title')).to_contain_text('Flores Amapolda')
        assert page.locator('#hero h1').evaluate("e=>getComputedStyle(e,'::after').backgroundImage")=='none'
        for width in WIDTHS:
            check_flowers(page,width)
            page.evaluate('scrollTo(0,0)')
            if width==390:page.screenshot(path='/tmp/electronicama-botanical-home-mobile.png')
            if width==1440:page.screenshot(path='/tmp/electronicama-botanical-home-desktop.png')
        assert_no_duplicates(page)

        # The literal entry wording is not translated into a different slogan.
        page.set_viewport_size({'width':1440,'height':900})
        page.locator('[data-site-language]').select_option('en')
        expect(page.locator('html')).to_have_attribute('lang','en')
        expect(page.locator('#hero-title')).to_contain_text('Flores')
        expect(page.locator('#hero-title')).to_contain_text('Flores Amapolda')
        expect(page.locator('#ol-intro-title')).to_contain_text('Flores Amapolda')
        page.locator('[data-site-language]').select_option('es')
        expect(page.locator('html')).to_have_attribute('lang','es')
        for view in ['favorites','history','discover']:
            page.locator('#main-nav [data-view="'+view+'"]').click()
            check_flowers(page,1440)

        page.set_viewport_size({'width':390,'height':900});page.evaluate('scrollTo(0,0)')
        page.locator('#mobile-menu').click()
        expect(page.locator('#mobile-nav')).to_be_visible()
        expect(page.locator('#mobile-nav .botanical-interface')).to_have_count(0)
        page.keyboard.press('Escape')
        page.locator('.mobile-quick-search').click()
        expect(page.locator('#search-input')).to_be_focused()
        page.locator('#search-input').fill('piano')
        page.locator('#search-button').click()
        page.wait_for_function("document.querySelector('#search-input').value==='piano'&&!document.querySelector('#search-button').disabled")
        assert any('q=piano' in query for query in queries)

        # Real registration exercises the transition from credentials to the
        # member workspace, rather than changing DOM visibility by hand.
        page.goto(BASE_URL+'/account');close_preferences(page)
        expect(page.locator('#credentials')).to_be_visible()
        for width in WIDTHS:check_flowers(page,width)
        username='botanical-'+secrets.token_hex(4)
        page.locator('#register-form [name=username]').fill(username)
        page.locator('#register-form [name=password]').fill('botanical-browser-password-123')
        page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
        page.locator('#registration-human-answer').fill('OL234')
        page.locator('#registration-submit').click()
        expect(page.locator('#member-panel')).to_be_visible()
        expect(page.locator('#credentials')).to_be_hidden()
        expect(page.locator('#member-title')).to_contain_text(username)
        for width in WIDTHS:check_flowers(page,width)
        assert_no_duplicates(page)

        admin_context=browser.new_context(viewport={'width':390,'height':900})
        login_context(admin_context)
        admin_page=admin_context.new_page();admin_page.on('pageerror',lambda error:errors.append(str(error)))
        admin_page.goto(BASE_URL+'/account');close_preferences(admin_page)
        expect(admin_page.locator('#admin-panel')).to_be_visible()
        for width in WIDTHS:check_flowers(admin_page,width)
        assert_no_duplicates(admin_page)

        # A long channel title must leave room for actual mobile actions. The
        # ornament groups stay out of both the video workspace and its controls.
        live=admin_context.new_page();live.on('pageerror',lambda error:errors.append(str(error)))
        live.add_init_script(SDK)
        channel={'id':'d'*32,'title':'Un directo con un título largo para comprobar los controles en el móvil','username':'artista','bio':'Música compartida','category':'musica','live':True}
        live.route('**/api/status',lambda route:route.fulfill(json={'live_premiere':False,'maintenance':{'scope':'off','message':''}}))
        live.route('**/api/streamers',lambda route:route.fulfill(json={'video_ready':True,'streamer_active':False,'mine':None,'channels':[channel],'setup_checks':None}))
        live.route('**/api/streamers/*/token',lambda route:route.fulfill(json={'url':'wss://fixture.invalid','token':'botanical-local-fixture','session_start':'botanical-live'}))
        live.route('**/api/streamers/*/access',lambda route:route.fulfill(json={'allowed':True,'ended':False,'listed':True,'guest_allowed':False,'session_start':'botanical-live'}))
        live.route('**/api/streamers/*/comments**',lambda route:route.fulfill(json={'comments':[],'reactions':[],'session_start':'botanical-live','cursor':'','can_post':True}))
        live.route('**/api/streamers/*/view',lambda route:route.fulfill(json={'ok':True}))
        live.goto(BASE_URL+'/live#live-catalogue');close_preferences(live)
        live.locator('.live-channel').wait_for()
        for width in WIDTHS:check_flowers(live,width)
        assert_no_duplicates(live)
        live.locator('.live-channel button').first.click()
        expect(live.locator('#live-stage')).to_be_visible()
        for width in WIDTHS:check_stage_controls(live,width)
        live.set_viewport_size({'width':390,'height':900})
        live.locator('#mobile-live-controls').click()
        expect(live.locator('#enable-sound')).to_be_visible()
        expect(live.locator('#fullscreen-live')).to_be_visible()
        live.locator('#leave-room').click()
        expect(live.locator('#live-stage')).to_be_hidden()
        check_flowers(live,390)
        assert not errors,errors
        browser.close()
    print('OK: literal Flores entry phrase, sparse stable floral accents, no covered controls, guest/member/admin states, working search/menu, live heading and 320/390/768/1440 layouts')


if __name__=='__main__':run()
