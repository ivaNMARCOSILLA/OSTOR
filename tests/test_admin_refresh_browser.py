"""Admin refreshes retain drafts, table state and the stable account identity."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context


def update(page):
    page.evaluate("window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}))")


def wait_callback(page, predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'expected an intercepted request'
        page.wait_for_timeout(20)


def blur(page):
    page.evaluate('document.activeElement?.blur()')
    page.clock.run_for(30)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        admin=login_context(context)
        account=context.request.get(BASE_URL+'/api/account/me').json()
        version=context.request.get(BASE_URL+'/health').json()['version']
        account['profile']['nickname']='Nombre confirmado'
        account['user']['nickname']='Nombre confirmado'
        members=[{
            'id':f'{number+1:032x}','username':f'client-{number:03}',
            'nickname':'','legal_name':'','role':'member','community_role':'activo',
            'active':True,'account_activated':True,'archived':False,
            'access_until':None,'streamer_until':None,'complimentary':False,
        } for number in range(60)]
        target=members[30]
        target.update(founder_number=31,founder_active=True,live_annual=True,
            access_until='2099-01-01T00:00:00+00:00',
            last_payment={'plan':'annual','amount_cents':2500,
                'verified_at':'2026-10-29T12:00:00+00:00','reference':'ISOLATED-ANNUAL-031'})
        state={'hold_next':False,'notice':'Aviso inicial'}
        reads=[];held=[];admin_posts=[];renames=[];roles=[];errors=[];navigations=[]
        page=context.new_page()
        page.clock.install()
        page.clock.pause_at(datetime.now(timezone.utc)+timedelta(seconds=1))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
        page.on('request',lambda request:admin_posts.append(request.url)
            if request.method=='POST' and '/api/admin/' in request.url else None)
        page.route('**/api/account/me',lambda route:route.fulfill(json=deepcopy(account)))
        page.route('**/api/sync',lambda route:route.fulfill(json={'public':'fixed','account':'fixed'}))
        page.route('**/health',lambda route:route.fulfill(json={'status':'ok','version':version}))
        def directory(route):
            assert route.request.method=='GET'
            reads.append(route.request.url)
            payload={'members':deepcopy(members),'payments':[]}
            if state['hold_next']:
                state['hold_next']=False;held.append((route,payload));return
            route.fulfill(json=payload,headers={'Cache-Control':'no-store'})
        page.route('**/api/admin/members',directory)
        page.route('**/api/admin/members?*',directory)
        def rename(route):
            data=route.request.post_data_json;renames.append(data)
            assert data['member_id']==target['id']
            old=target['username'];target['username']=data['username']
            route.fulfill(json={'ok':True,'member_id':target['id'],
                'username':target['username'],'previous_username':old,'changed':old!=target['username']})
        page.route('**/api/admin/members/rename',rename)
        def approve_role(route):
            data=route.request.post_data_json;roles.append(data)
            assert data['member_id']==target['id']
            target['community_role']=data['community_role']
            route.fulfill(json={'ok':True})
        page.route('**/api/admin/community-role',approve_role)
        def notices(route):
            route.fulfill(json={'page':1,'pages':1,'total':1,'pending':0,
                'recipient':'admin@example.test','email_ready':False,
                'notifications':[{'id':'isolated-notice','title':state['notice'],
                    'detail':'Aviso de la base de pruebas','created_at':'2026-11-05T12:00:00+00:00','status':'sent'}]})
        page.route('**/api/admin/notifications?*',notices)
        page.goto(BASE_URL+'/account')
        popup=page.locator('#visitor-consent-panel')
        if popup.count() and popup.is_visible():
            popup.get_by_role('button',name='Solo necesarias',exact=True).click()
        expect(page.locator('#admin-refresh-now')).to_be_visible()
        expect(page.locator('#admin-refresh-status')).to_have_attribute('role','status')
        page.evaluate('async()=>{await window.OlAccountReady}')
        expect(page.locator('#admin-members tr')).to_have_count(25)
        assert not admin_posts,'opening and refreshing administration must not mutate accounts'

        # A timed refresh changes the data, not the current page or filters.
        page.locator('#admin-client-sort').select_option('name')
        page.locator('#admin-member-search').fill('client-')
        page.locator('#members-next').click()
        expect(page.locator('#member-page')).to_contain_text('Página 2')
        row=page.locator('#admin-members tr[data-member-id="'+target['id']+'"]')
        expect(row).to_be_visible()
        page.locator('#notification-history>summary').click()
        expect(page.locator('#admin-notifications')).to_contain_text('Aviso inicial')
        blur(page)
        before=len(reads);target['nickname']='Cambio automático';state['notice']='Aviso actualizado'
        page.clock.fast_forward(30100)
        expect(row).to_contain_text('Cambio automático')
        expect(page.locator('#admin-notifications')).to_contain_text('Aviso actualizado')
        assert len(reads)>before
        expect(page.locator('#member-page')).to_contain_text('Página 2')
        expect(page.locator('#admin-member-search')).to_have_value('client-')
        expect(page.locator('#admin-client-sort')).to_have_value('name')

        # A second revision arriving during a read must schedule a fresh read.
        target['nickname']='Respuesta anterior';state['hold_next']=True
        update(page);wait_callback(page,lambda:bool(held))
        before=len(reads);target['nickname']='Última revisión';update(page)
        request,payload=held.pop(0);request.fulfill(json=payload)
        expect(row).to_contain_text('Última revisión')
        assert len(reads)>before,'a revision received while busy must remain pending'

        # User-entered profile fields survive both focus and a later blur.
        page.locator('#profile-settings').evaluate('element=>element.open=true')
        draft=page.locator('#profile-form [name=nickname]')
        draft.fill('Mi borrador de apodo')
        account['profile']['nickname']='Nombre remoto'
        account['user']['nickname']='Nombre remoto'
        before=len(reads);target['nickname']='Cambio pendiente durante edición'
        update(page);page.clock.run_for(100)
        expect(draft).to_have_value('Mi borrador de apodo')
        assert len(reads)==before,'editing a form must defer the table refresh'
        blur(page)
        expect(row).to_contain_text('Cambio pendiente durante edición')
        expect(draft).to_have_value('Mi borrador de apodo')

        # A read started before editing must not replace an active rename form.
        state['hold_next']=True;update(page);wait_callback(page,lambda:bool(held))
        rename_details=row.locator('details[data-member-rename="'+target['id']+'"]')
        rename_details.locator('summary').click()
        rename_input=rename_details.locator('form.member-rename-form [name=username]')
        rename_input.fill('borrador-client-030')
        target['nickname']='Cambio tras empezar a escribir';update(page)
        request,payload=held.pop(0);request.fulfill(json=payload)
        page.clock.run_for(100)
        expect(rename_input).to_have_value('borrador-client-030')
        expect(rename_input).to_be_focused()
        assert not renames
        blur(page)
        expect(row).to_contain_text('Cambio tras empezar a escribir')
        expect(rename_input).to_have_value('borrador-client-030')
        expect(rename_details).to_have_attribute('open','')

        # The community role selector lives outside a form; its pending choice
        # must also survive a table rebuild until explicitly approved.
        role=row.locator('select[data-member-role="'+target['id']+'"]')
        role.select_option('docente');blur(page)
        target['nickname']='Cambio con rol pendiente';update(page)
        expect(row).to_contain_text('Cambio con rol pendiente')
        expect(role).to_have_value('docente')
        assert not roles
        row.get_by_role('button',name='Aprobar rol',exact=True).click()
        wait_callback(page,lambda:len(roles)==1)
        assert roles==[{'member_id':target['id'],'community_role':'docente'}]
        expect(role).to_have_value('docente')
        target['community_role']='voluntario';target['nickname']='Rol confirmado y después actualizado'
        blur(page);update(page)
        expect(row).to_contain_text('Rol confirmado y después actualizado')
        expect(role).to_have_value('voluntario')

        # Renaming changes the public login name, while the same account ID,
        # founder number and paid history stay attached to that account.
        payment=deepcopy(target['last_payment']);identity=target['id']
        rename_input.fill('renamed-client-030')
        rename_details.locator('form.member-rename-form button[type=submit]').click()
        wait_callback(page,lambda:len(renames)==1)
        assert renames==[{'member_id':identity,'username':'renamed-client-030'}]
        page.locator('#admin-member-search').fill('renamed-client-030')
        expect(page.locator('#admin-members tr')).to_have_count(1)
        expect(row).to_contain_text('renamed-client-030')
        expect(row.locator('td').nth(2)).to_contain_text('31')
        expect(row.locator('td').nth(5)).to_contain_text('25.00')
        assert target['id']==identity and target['founder_number']==31
        assert target['last_payment']==payment
        assert len(admin_posts)==2,'only explicit role approval and rename may write administrative data'

        # Hidden pages do no periodic admin reads. Return and lifecycle events
        # retrieve pending updates without a document navigation.
        blur(page);before=len(reads)
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true});document.dispatchEvent(new Event('visibilitychange'))")
        target['nickname']='Cambio mientras no se ve';update(page)
        page.clock.fast_forward(30100)
        assert len(reads)==before
        page.evaluate("delete document.hidden;document.dispatchEvent(new Event('visibilitychange'))")
        expect(row).to_contain_text('Cambio mientras no se ve')
        for event in ['focus','online','pageshow']:
            target['nickname']='Actualización por '+event
            page.evaluate('(name)=>window.dispatchEvent(new Event(name))',event)
            expect(row).to_contain_text('Actualización por '+event)
        blur(page);target['nickname']='Actualización manual'
        page.locator('#admin-refresh-now').click()
        expect(row).to_contain_text('Actualización manual')
        expect(page.locator('#admin-refresh-now')).to_be_enabled()
        for width in [320,390,1440]:
            page.set_viewport_size({'width':width,'height':900})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
            assert page.locator('#admin-refresh-now').bounding_box()['height']>=44,width
        assert len(navigations)==1,navigations
        assert not errors,errors
        assert admin['role']=='admin'
        browser.close()
    print('OK: automatic admin refresh, queued revisions, focused and dirty drafts, retained filters/pages/roles, stable-identity rename, open panels and lifecycle recovery')


if __name__=='__main__':run()
