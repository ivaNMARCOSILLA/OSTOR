"""Participant files are private, lazy, read-only and stable during account refreshes."""
from copy import deepcopy
import secrets
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel = page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button', name='Solo necesarias', exact=True).click()


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        guest_context = browser.new_context(viewport={'width':390, 'height':1000})
        guest = guest_context.new_page()
        guest_calls = []
        guest.on('request', lambda request: guest_calls.append(request.url)
                 if '/api/admin/participants' in request.url else None)
        guest.goto(BASE_URL+'/account')
        close_preferences(guest)
        expect(guest.locator('#participant-tracking')).to_be_hidden()
        assert not guest_calls, 'visitors must not request private participant records'
        assert guest_context.request.get(BASE_URL+'/api/admin/participants').status == 403

        # A matching nickname never makes a registered member an administrator.
        username = 'participant-member-'+secrets.token_hex(4)
        guest.locator('#register-form [name=username]').fill(username)
        guest.locator('#register-form [name=password]').fill('participant-browser-password-123')
        guest.locator('#register-form [name=nickname]').fill('Fruto del padre')
        guest.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
        guest.locator('#registration-human-answer').fill('OL234')
        guest.locator('#registration-submit').click()
        expect(guest.locator('#member-panel')).to_be_visible()
        expect(guest.locator('#participant-tracking')).to_be_hidden()
        assert guest.locator('#participant-tracking-content').inner_text() == ''
        assert guest_context.request.get(BASE_URL+'/api/admin/participants').status == 403
        assert not guest_calls

        context = browser.new_context(viewport={'width':1440, 'height':1000})
        login_context(context)
        page = context.new_page()
        errors = []
        posts = []
        list_reads = []
        detail_reads = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: posts.append(request.url)
                if request.method == 'POST' and '/api/admin/participants' in request.url else None)
        participants = [{
            'id':f'{number+1:032x}', 'username':f'client-{number:03}',
            'nickname':'', 'created_at':'2026-11-10T12:00:00+00:00',
            'registered_at':'2026-11-10T12:00:00+00:00',
            'account_activated':True, 'archived':number>=59, 'role':'member',
            'last_activity_at':None, 'access_active':False, 'streamer_active':False,
            'live_annual':False, 'access_until':None, 'founder_number':None,
        } for number in range(61)]
        target = participants[40]
        target['nickname'] = '<b>Artista libre</b>'
        target['live_annual'] = True
        target['access_active'] = target['streamer_active'] = True
        target['access_until'] = '2099-01-01T00:00:00+00:00'
        target['founder_number'] = 41
        detail = {
            'participant':dict(target, access={
                'active':True, 'streamer_active':True, 'live_annual':True,
                'full_service':False, 'complimentary':False,
                'access_until':target['access_until'], 'founder_active':True,
                'community_role':'activo',
            }),
            'activity':{'last_activity_at':None, 'verified_seconds':3660,
                        'last_verified_at':'2026-11-11T13:00:00+00:00', 'qualification_until':None},
            'founder_ownership':{'number':41, 'permanent':True, 'revoked':False},
            'channels':[{'id':'a'*32, 'title':'Canal de prueba', 'live':False,
                         'live_until':None, 'updated_at':'2026-11-11T13:00:00+00:00'}],
            'videos':{'counts':{'uploading':0, 'quarantined':2, 'published':3,
                                'rejected':0, 'failed':0, 'deleted':1},
                      'latest':[{'id':'b'*32, 'title':'<img src=x onerror="window.participantInjection=true">',
                                 'state':'quarantined', 'category':'music',
                                 'created_at':'2026-11-11T13:00:00+00:00',
                                 'updated_at':'2026-11-11T13:00:00+00:00', 'published_at':None}]},
            'payments':[{'id':'c'*32, 'plan':'annual', 'amount_cents':2500,
                         'starts_at':'2026-11-11T13:00:00+00:00',
                         'ends_at':'2099-01-01T00:00:00+00:00',
                         'verified_at':'2026-11-11T13:00:00+00:00'}],
            'timeline':[{'kind':'registered', 'label':'Registro de la cuenta',
                         'at':'2026-11-10T12:00:00+00:00', 'detail':'Registro confirmado'}],
        }

        def tracking(route):
            assert route.request.method == 'GET', 'the tracking panel must remain read-only'
            parsed = urlsplit(route.request.url)
            if parsed.path == '/api/admin/participants':
                query = parse_qs(parsed.query)
                list_reads.append(query)
                q = query.get('q', [''])[0].lower()
                archived = query.get('archived', ['0'])[0] == '1'
                rows = [item for item in participants
                        if (archived or not item['archived'])
                        and (not q or q in item['username'].lower() or q in item['nickname'].lower())]
                pages = max(1, (len(rows)+24)//25)
                current = min(pages, max(1, int(query.get('page', ['1'])[0])))
                route.fulfill(json={'participants':deepcopy(rows[(current-1)*25:current*25]),
                                    'page':current, 'pages':pages, 'total':len(rows), 'page_size':25})
            else:
                ident = parsed.path.rsplit('/', 1)[-1]
                detail_reads.append(ident)
                assert ident == target['id']
                route.fulfill(json=deepcopy(detail))

        page.route('**/api/admin/participants**', tracking)
        page.goto(BASE_URL+'/account')
        close_preferences(page)
        panel = page.locator('#participant-tracking')
        expect(panel).to_be_visible()
        expect(page.locator('#admin-members tr').first).to_be_visible()
        assert not list_reads and not detail_reads, 'private records should load only when opened'
        panel.locator('summary').first.click()
        expect(page.locator('#participant-list .participant-choice')).to_have_count(25)
        expect(page.locator('#participant-status')).to_contain_text('59 cuentas')
        page.locator('#participant-next').click()
        expect(page.locator('#participant-page')).to_have_text('Página 2 de 3')
        expect(page.locator('#participant-list .participant-choice')).to_have_count(25)
        page.locator('#participant-search').fill('client-040')
        expect(page.locator('#participant-list .participant-choice')).to_have_count(1)
        page.locator('#participant-show-archived').check()
        page.wait_for_function("document.querySelector('#participant-list .participant-choice')?.textContent.includes('client-040')")
        page.locator('[data-participant-id="'+target['id']+'"]').click()
        expect(page.locator('#participant-detail-title')).to_contain_text('@client-040')
        expect(page.locator('#participant-detail')).to_contain_text('<b>Artista libre</b>')
        expect(page.locator('#participant-detail')).to_contain_text('1 h 1 min')
        expect(page.locator('#participant-detail')).to_contain_text('N.º 41 · pertenencia permanente')
        expect(page.locator('#participant-detail')).to_contain_text('En cuarentena')
        expect(page.locator('#participant-detail')).to_contain_text('Registro confirmado')
        assert page.locator('#participant-detail').get_by_text('No disponible', exact=True).count() >= 1
        assert page.locator('#participant-detail img,#participant-detail b').count() == 0
        assert page.evaluate('window.participantInjection') is None
        assert list_reads[-1].get('q') == ['client-040']
        assert list_reads[-1].get('archived') == ['1']

        # Routine account refreshes keep both the user's search and the open file.
        previous_reads = len(list_reads)
        previous_details = len(detail_reads)
        page.evaluate("window.participantHeadingBeforeRefresh=document.querySelector('#participant-detail-title')")
        page.evaluate("window.dispatchEvent(new Event('ol:account-refreshed'))")
        page.wait_for_timeout(350)
        expect(page.locator('#participant-search')).to_have_value('client-040')
        expect(page.locator('#participant-show-archived')).to_be_checked()
        assert page.evaluate("document.querySelector('#participant-detail-title')===window.participantHeadingBeforeRefresh")
        assert len(list_reads) == previous_reads and len(detail_reads) == previous_details

        for width in [320, 390, 768, 1440]:
            page.set_viewport_size({'width':width, 'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'), width
            page.locator('#participant-refresh').click()
            expect(page.locator('#participant-detail-title')).to_contain_text('@client-040')
            expect(page.locator('#participant-search')).to_have_value('client-040')
            if width in [390, 1440]:
                panel.screenshot(path=f'/tmp/electronicama-participants-{width}.png')

        # A session losing administrator access clears its private DOM immediately.
        csrf = context.request.get(BASE_URL+'/api/account/me').json()['csrf']
        assert context.request.post(BASE_URL+'/api/account/logout', data={},
                                    headers={'X-CSRF-Token':csrf}).status == 200
        page.evaluate("window.dispatchEvent(new Event('ol:account-refreshed'))")
        expect(panel).to_be_hidden()
        expect(page.locator('#participant-tracking-content')).to_have_text('')
        assert not posts, posts
        assert not errors, errors
        browser.close()
    print('OK: lazy admin-only participant records, real guest/member denial, server pagination, selected detail and unknown activity, escaped content, stable refresh and four widths')


if __name__ == '__main__':
    run()
