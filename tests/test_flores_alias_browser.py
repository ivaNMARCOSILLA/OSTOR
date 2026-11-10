"""Flores' fixed distinction stays separate from identity and follows her own live chat."""
from copy import deepcopy
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context
from test_stream_continuity_browser import SDK


HONOR={'title':'Triunfador'}
FLORES='a'*32
OTHER='b'*32


def expect_honor(container):
    expect(container.locator('.stream-honor')).to_have_count(1)
    expect(container.locator('.stream-honor-title')).to_have_text(HONOR['title'])
    expect(container.locator('.stream-honor-alias')).to_have_count(0)
    expect(container.locator('.stream-honor')).to_have_text(HONOR['title'])


def check_widths(page, selectors):
    for width in [320,390,1440]:
        page.set_viewport_size({'width':width,'height':900})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
        for selector in selectors:
            element=page.locator(selector)
            assert element.evaluate('e=>e.scrollWidth<=e.clientWidth+2'),(width,selector)
            assert element.evaluate('e=>{const r=e.getBoundingClientRect();return r.left>=-2&&r.right<=innerWidth+2}'),(width,selector)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844})
        admin=login_context(context)
        assert admin['role']=='admin'
        page=context.new_page();errors=[];alias_calls=[];token_calls=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script(SDK)
        alias_state={
            'stream_alias':deepcopy(HONOR),
            'account':{'username':'rosas','display_name':'Flores','archived':False},
            'channel':{'id':FLORES,'title':'Flores en directo','live':True},
        }
        def alias_details(route):
            alias_calls.append(route.request.method)
            assert route.request.method=='GET','viewing a fixed alias must not change any account'
            route.fulfill(json=alias_state)
        page.route('**/api/streamers/admin/flores-alias',alias_details)
        member={'id':'c'*32,'username':'rosas','nickname':'Flores','role':'member','active':True,'account_activated':True}
        page.route('**/api/admin/members',lambda route:route.fulfill(json={'members':[member],'payments':[]}))
        page.goto(BASE_URL+'/account')
        section=page.locator('#flores-stream-alias-admin')
        expect(section).to_be_visible()
        expect_honor(page.locator('#flores-stream-alias-badge'))
        expect(section.locator('h3')).to_have_text('Triunfador · Flores')
        expect(section).to_contain_text('Flores (@rosas)')
        expect(page.locator('#flores-stream-alias-status')).to_have_text('Flores está en directo.')
        expect(page.locator('#flores-stream-alias-link')).to_have_attribute('href','/live#canal-'+FLORES)
        assert page.locator('#flores-stream-alias-link').evaluate('e=>e.getBoundingClientRect().height>=44')
        assert section.evaluate("e=>e.parentElement.id==='admin-panel'&&e.tagName==='SECTION'")
        expect(page.locator('#admin-members tr td').first).to_have_text('rosas · Flores')
        expect(page.locator('#admin-members .stream-honor')).to_have_count(0)
        expect(page.locator('#member-title')).to_contain_text(admin['username'])
        check_widths(page,['#flores-stream-alias-admin','#flores-stream-alias-badge .stream-honor'])
        page.set_viewport_size({'width':390,'height':844})
        section.screenshot(path='/tmp/electronicama-flores-admin-mobile.png')

        # The dedicated section must not offer a live link to an archived or
        # absent account, even if a previous successful load had shown one.
        alias_state['account']['archived']=True
        page.reload()
        expect(page.locator('#flores-stream-alias-status')).to_have_text('La cuenta de Flores está dada de baja.')
        expect(page.locator('#flores-stream-alias-link')).to_be_hidden()
        alias_state['account']=None;alias_state['channel']=None
        page.reload()
        expect(page.locator('#flores-stream-alias-status')).to_have_text('La cuenta @rosas todavía no existe en este entorno.')
        expect(page.locator('#flores-stream-alias-link')).to_be_hidden()
        alias_state['account']={'username':'rosas','display_name':'Flores','archived':False}
        alias_state['channel']={'id':FLORES,'title':'Flores en directo','live':True}
        page.reload()
        expect(page.locator('#flores-stream-alias-link')).to_be_visible()

        channels=[
            {'id':FLORES,'title':'Flores en directo','username':'Flores','bio':'El canal de Flores','category':'entretenimiento','live':True,'stream_alias':deepcopy(HONOR)},
            {'id':OTHER,'title':'Directo de Lucía','username':'Lucía','bio':'Otro canal','category':'musica','live':True},
        ]
        page.route('**/api/status',lambda route:route.fulfill(json={'live_premiere':False,'maintenance':{'scope':'off','message':''}}))
        page.route('**/api/streamers',lambda route:route.fulfill(json={'video_ready':True,'streamer_active':False,'mine':None,'channels':channels,'setup_checks':None}))
        def token(route):
            payload=route.request.post_data_json
            token_calls.append(payload)
            assert payload['publish'] is False
            route.fulfill(json={'url':'wss://fixture.invalid','token':'local-fixture','session_start':'alias-emission'})
        page.route('**/api/streamers/*/token',token)
        page.route('**/api/streamers/*/access',lambda route:route.fulfill(json={'allowed':True,'ended':False,'listed':True,'guest_allowed':False,'session_start':'alias-emission'}))
        page.route('**/api/streamers/*/view',lambda route:route.fulfill(json={'ok':True}))
        def comments(route):
            assert route.request.method=='GET'
            parsed=urlparse(route.request.url);channel_id=parsed.path.split('/')[3]
            own_channel=channel_id==FLORES
            author={'id':'flores-message','username':'rosas','display_name':'Flores','body':'Hola desde mi canal' if own_channel else 'Hola desde otro canal','kind':'comment','likes':0,'liked':False}
            if own_channel:author['stream_alias']=deepcopy(HONOR)
            reader={'id':'reader-message','username':'lector','display_name':'Lector','body':'Un saludo a todos','kind':'comment','likes':0,'liked':False}
            rows=[author,reader]
            route.fulfill(json={
                'comments':[] if parse_qs(parsed.query).get('after') else rows,
                'reactions':[{'id':row['id'],'likes':0,'liked':False} for row in rows],
                'session_start':'alias-emission','cursor':'alias-cursor','can_post':True,
            })
        page.route('**/api/streamers/*/comments**',comments)

        # Follow the actual admin link and use the real catalogue, stage and
        # community modules; only video transport and remote data are fixtures.
        page.locator('#flores-stream-alias-link').click()
        expect(page).to_have_url(BASE_URL+'/live#canal-'+FLORES)
        flores=page.locator('#canal-'+FLORES);other=page.locator('#canal-'+OTHER)
        expect(flores).to_be_visible();expect_honor(flores)
        expect(flores.locator('h3')).to_have_text('Flores en directo')
        expect(flores.locator(':scope > p').first).to_have_text('Flores')
        expect(other.locator('.stream-honor')).to_have_count(0)
        page.locator('#channel-filter').fill('triunfador')
        expect(page.locator('.live-channel')).to_have_count(1)
        expect(page.locator('.live-channel')).to_have_attribute('id','canal-'+FLORES)
        page.locator('#channel-filter').fill('')
        check_widths(page,['#canal-'+FLORES,'#canal-'+FLORES+' .stream-honor'])
        page.get_by_role('button',name='Ver vídeo en directo de Flores en directo',exact=True).click()
        expect(page.locator('#live-stage')).to_be_visible()
        expect(page.locator('#stage-title')).to_have_text('Flores en directo')
        expect_honor(page.locator('#stage-stream-alias'))
        own_comment=page.locator('#live-comments p[data-message-id="flores-message"]')
        expect(own_comment.locator(':scope > strong')).to_have_text('Flores: ')
        expect_honor(own_comment)
        expect(page.locator('#live-comments p[data-message-id="reader-message"] .stream-honor')).to_have_count(0)
        check_widths(page,['#stage-stream-alias','#stage-stream-alias .stream-honor'])
        page.set_viewport_size({'width':390,'height':844})
        page.locator('#live-stage').screenshot(path='/tmp/electronicama-flores-live-mobile.png')

        page.locator('#leave-room').click()
        expect(page.locator('#stage-stream-alias')).to_be_hidden()
        expect(page.locator('#stage-stream-alias .stream-honor')).to_have_count(0)
        page.get_by_role('button',name='Ver vídeo en directo de Directo de Lucía',exact=True).click()
        expect(page.locator('#stage-title')).to_have_text('Directo de Lucía')
        expect(page.locator('#stage-stream-alias')).to_be_hidden()
        expect(page.locator('#live-comments p[data-message-id="flores-message"]')).to_contain_text('Hola desde otro canal')
        expect(page.locator('#live-comments .stream-honor')).to_have_count(0)
        expect(page.locator('#live-comments p[data-message-id="flores-message"] > strong')).to_have_text('Flores: ')
        assert len(token_calls)==2

        # The removed nickname cannot leak from cached payloads, and untrusted
        # titles cannot become executable markup through the shared component.
        escaped=page.evaluate("""async () => {
            const {streamHonor}=await import('/assets/stream-honor.js');
            const data={alias:'<img src=x onerror="window.aliasInjected=true">',title:'<script>window.aliasInjected=true</script>'};
            const badge=streamHonor(data);
            return {text:badge.textContent,elements:badge.querySelectorAll('img,script').length,
                injected:window.aliasInjected===true,invalid:streamHonor({title:7})===null,
                legacy:streamHonor({alias:'removed nickname',title:'Triunfador'}).textContent};
        }""")
        assert escaped=={'text':'<script>window.aliasInjected=true</script>','elements':0,'injected':False,'invalid':True,'legacy':'Triunfador'}
        page.locator('#leave-room').click()

        # A normal account does not request or expose the admin-only section.
        member_page=context.new_page();member_calls=[]
        member_page.on('pageerror',lambda error:errors.append(str(error)))
        def member_account(route):
            response=route.fetch();data=response.json();data['user']['role']='member'
            route.fulfill(response=response,json=data)
        member_page.route('**/api/account/me',member_account)
        member_page.route('**/api/streamers/admin/flores-alias',lambda route:(member_calls.append(route.request.url),route.fulfill(status=403,json={'error':'Administración requerida'})))
        member_page.goto(BASE_URL+'/account')
        expect(member_page.locator('#member-title')).to_contain_text(admin['username'])
        expect(member_page.locator('#flores-stream-alias-admin')).to_be_hidden()
        assert not member_calls
        assert alias_calls and all(method=='GET' for method in alias_calls)
        assert not errors,errors
        browser.close()
    print('OK: dedicated Flores admin section, preserved names, live link, own-channel catalogue/stage/chat distinction, channel switch, escaped text and 320/390/1440 layouts')


if __name__=='__main__':run()
