"""The mobile edition has reachable app navigation without changing desktop layout."""
from playwright.sync_api import sync_playwright, expect
from browser_support import BASE_URL


DESTINATIONS=['/#inicio','/#library','/live#live-catalogue','/#hologramas','/account']


def assert_dock(page, width, height):
    dock=page.locator('#mobile-dock')
    expect(dock).to_be_visible()
    assert dock.locator('a').evaluate_all("els=>els.map(el=>el.getAttribute('href'))")==DESTINATIONS
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
    issues=dock.evaluate('''nav=>{
      const issues=[],box=nav.getBoundingClientRect();
      if(box.left<0||box.right>innerWidth+1||box.top<0||box.bottom>innerHeight+1)issues.push('dock escapes viewport');
      for(const link of nav.querySelectorAll('a')){
        const r=link.getBoundingClientRect(),top=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
        if(r.width<44||r.height<44)issues.push('small touch target: '+link.textContent);
        if(!top||!link.contains(top))issues.push('covered link: '+link.textContent);
        if(link.scrollWidth>link.clientWidth+1)issues.push('clipped label: '+link.textContent);
      }
      return issues;
    }''')
    assert not issues,(width,height,issues)
    return dock


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':393,'height':852},is_mobile=True,has_touch=True)
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/search?*',lambda route:route.fulfill(json=[{
            'id':'archive_mobile_example','source':'ARCHIVE','title':'Una canción para escuchar en el móvil',
            'channel':'Artista de prueba','thumbnail':''
        }]))
        page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
        page.locator('#track-grid .track-card').wait_for()
        expect(page.locator('.mobile-quick-search')).to_be_visible()
        page.locator('.mobile-quick-search').click()
        expect(page.locator('#search-input')).to_be_focused()
        expect(page.locator('#mobile-dock a[href="/#library"]')).to_have_attribute('aria-current','page')

        # The drawer floats above content, and its last settings remain reachable
        # in both a phone portrait viewport and a short horizontal viewport.
        for width,height in [(320,740),(393,852),(430,932),(768,1024),(800,430)]:
            page.set_viewport_size({'width':width,'height':height})
            page.evaluate('scrollTo(0,0)')
            dock=assert_dock(page,width,height)
            menu=page.locator('#mobile-menu');drawer=page.locator('#mobile-nav')
            hero_before=page.locator('#hero').bounding_box()['y']
            menu.click();expect(drawer).to_be_visible()
            assert abs(page.locator('#hero').bounding_box()['y']-hero_before)<=1,(width,'menu displaces content')
            assert drawer.locator('[data-site-language]').count()==1
            drawer_box=drawer.bounding_box();dock_box=dock.bounding_box()
            assert drawer_box['y']>=0 and drawer_box['y']+drawer_box['height']<=dock_box['y']+1,(width,drawer_box,dock_box)
            drawer.locator('#cookie-settings').scroll_into_view_if_needed()
            expect(drawer.locator('#cookie-settings')).to_be_in_viewport()
            page.keyboard.press('Escape');expect(drawer).to_be_hidden()
            expect(menu).to_be_focused()

        page.set_viewport_size({'width':393,'height':852})
        page.evaluate('scrollTo(0,0)');page.locator('#mobile-menu').click()
        page.locator('#mobile-nav [data-site-language]').select_option('fr')
        expect(page.locator('html')).to_have_attribute('lang','fr')
        page.locator('#mobile-nav [data-site-language]').select_option('auto')
        expect(page.locator('html')).to_have_attribute('lang','es')
        page.keyboard.press('Escape')

        # Translated labels must also fit the narrowest supported phone.
        page.set_viewport_size({'width':320,'height':740})
        for language in ['fr','de','it','pt','ca','en','es','auto']:
            page.locator('#mobile-menu').click()
            page.locator('#mobile-nav [data-site-language]').select_option(language)
            expect(page.locator('html')).to_have_attribute('lang','es' if language=='auto' else language)
            page.keyboard.press('Escape')
            assert_dock(page,320,740)
        page.set_viewport_size({'width':393,'height':852})

        # Layout-only player fixture: playback and real video have their own
        # suites; here a visible player may never cover the mobile navigation.
        for mode in ['compact','expanded']:
            page.locator('#player').evaluate('(el,mode)=>{el.classList.remove("hidden","compact","expanded");el.classList.add(mode)}',mode)
            dock=assert_dock(page,393,852)
            player=page.locator('#player').bounding_box();dock_box=dock.bounding_box()
            assert player['y']+player['height']<=dock_box['y']+1,(mode,player,dock_box)
        page.locator('#player').evaluate('el=>{el.classList.remove("expanded","compact");el.classList.add("hidden")}')

        # All mobile destinations are real links; accounts and live discovery
        # share the same navigation, while desktop keeps the wide interface.
        page.locator('#mobile-dock a[href="/#library"]').click()
        expect(page.locator('#search-form')).to_be_in_viewport()
        page.locator('#mobile-dock a[href="/account"]').click()
        page.wait_for_url(BASE_URL+'/account')
        assert_dock(page,393,852)
        page.locator('#mobile-dock a[href="/live#live-catalogue"]').click()
        page.wait_for_url(BASE_URL+'/live#live-catalogue')
        assert_dock(page,393,852)
        # A viewing stage deliberately gives the video the full screen space.
        page.locator('#live-stage').evaluate('el=>el.classList.remove("hidden")')
        expect(page.locator('#mobile-dock')).to_be_hidden()
        page.locator('#live-stage').evaluate('el=>el.classList.add("hidden")')
        expect(page.locator('#mobile-dock')).to_be_visible()
        page.locator('#mobile-dock a[href="/#inicio"]').click()
        page.wait_for_url(BASE_URL+'/#inicio')
        expect(page.locator('#hero')).to_be_in_viewport()

        # End-of-page links are not hidden under the fixed app navigation.
        for path in ['/','/account','/live']:
            page.goto(BASE_URL+path);assert_dock(page,393,852)
            page.evaluate('scrollTo(0,document.documentElement.scrollHeight)')
            last=page.locator('footer a,footer button').last
            if last.count() and last.is_visible():
                assert last.bounding_box()['y']+last.bounding_box()['height']<=page.locator('#mobile-dock').bounding_box()['y']+1,path
            for width in [1024,1440]:
                page.set_viewport_size({'width':width,'height':1000})
                expect(page.locator('#mobile-dock')).to_be_hidden()
                if path=='/':
                    expect(page.locator('.sidebar')).to_be_visible()
                    expect(page.locator('.mobile-quick-search')).to_be_hidden()
            page.set_viewport_size({'width':393,'height':852})
        page.goto(BASE_URL+'/');page.screenshot(path='/tmp/electronicama-mobile-edition.png',full_page=False)
        assert not errors,errors
        browser.close()
    print('OK: dedicated mobile navigation, compact search, floating drawer, locale controls, player separation, real destinations and desktop preservation')


if __name__=='__main__':run()
