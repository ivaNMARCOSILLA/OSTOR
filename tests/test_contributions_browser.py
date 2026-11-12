"""Voluntary contributions require explicit consent and never initiate real payments."""
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel=page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button', name='Solo necesarias', exact=True).click()


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':1000})
        # The checkout API is intercepted, but its CSRF header comes from a real
        # anonymous application session. No card data or Stripe service is used.
        csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf']
        assert context.request.get(BASE_URL+'/api/account/me').json()['user'] is None
        page=context.new_page()
        page.add_init_script("window.contributionRestoredFromCache=false;window.addEventListener('pageshow',event=>{if(event.persisted)window.contributionRestoredFromCache=true;});")
        page.route('**/api/search?*', lambda route:route.fulfill(json=[]))
        state={'available':True,'mode':'valid'}
        posts=[]
        errors=[]
        page.on('pageerror', lambda error:errors.append(str(error)))

        def configuration(route):
            assert route.request.method == 'GET'
            route.fulfill(json={'available':state['available'],'currency':'eur',
                'min_amount_cents':100,'max_amount_cents':50000,'presets':[300,500,1000],
                'one_time':True,'grants_access':False})

        def checkout(route):
            assert route.request.method == 'POST'
            data=route.request.post_data_json
            assert route.request.headers.get('x-csrf-token') == csrf
            assert set(data) == {'amount_cents','contributions_terms'}
            assert isinstance(data['amount_cents'],int) and not isinstance(data['amount_cents'],bool)
            assert data['contributions_terms'] is True
            posts.append(data)
            if state['mode'] == 'unavailable':
                route.fulfill(status=503,json={'error':'Las aportaciones no están disponibles en este momento.'})
            elif state['mode'] == 'error':
                route.fulfill(status=502,json={'error':'El proveedor de pago no responde. Vuelve a intentarlo.'})
            elif state['mode'] == 'network':
                route.abort('failed')
            else:
                url=('https://checkout.stripe.com.evil.example/c/pay/unsafe'
                    if state['mode'] == 'unsafe' else
                    'https://checkout.stripe.com/c/pay/contribution-fixture-'+str(data['amount_cents']))
                route.fulfill(json={'url':url,'id':'cs_isolated_contribution','grants_access':False})

        page.route('**/api/contributions/config',configuration)
        page.route('**/api/contributions/checkout',checkout)
        page.route('https://checkout.stripe.com/**',lambda route:route.fulfill(
            content_type='text/html',body='<html><body><h1>Checkout de prueba</h1></body></html>'))

        def open_panel(query=''):
            before=len(posts)
            page.goto(BASE_URL+'/'+query+'#contributions')
            close_preferences(page)
            expect(page.locator('#contributions')).to_be_visible()
            if state['available']:
                expect(page.locator('#contribution-submit')).to_be_enabled()
            else:
                expect(page.locator('#contribution-submit')).to_be_disabled()
            assert len(posts) == before, 'loading the page must not create a checkout'

        open_panel()
        page.locator('#contribution-amount').fill('3')
        page.locator('#contribution-submit').click()
        expect(page.locator('#contribution-status')).to_contain_text('Confirma')
        assert not posts, 'unchecked consent must not start a checkout'

        for preset,raw,expected in [(300,None,300),(500,None,500),(1000,None,1000),
                                    (None,'12,34',1234),(None,'1.01',101)]:
            open_panel()
            if preset:
                button=page.locator('[data-contribution-cents="'+str(preset)+'"]')
                button.click()
                expect(button).to_have_attribute('aria-pressed','true')
            else:
                page.locator('#contribution-amount').fill(raw)
            page.locator('#contribution-terms').check()
            page.locator('#contribution-submit').click()
            expect(page).to_have_url('https://checkout.stripe.com/c/pay/contribution-fixture-'+str(expected))
            expect(page.get_by_role('heading',name='Checkout de prueba')).to_be_visible()
            assert posts[-1]['amount_cents'] == expected
            if preset == 300:
                before_back=len(posts)
                page.go_back()
                expect(page).to_have_url(BASE_URL+'/#contributions')
                expect(page.locator('#contribution-submit')).to_be_enabled()
                if page.evaluate('window.contributionRestoredFromCache'):
                    expect(page.locator('#contribution-amount')).to_have_value('3')
                    expect(page.locator('#contribution-terms')).not_to_be_checked()
                assert len(posts) == before_back, 'Back from Stripe must not create another checkout'

        open_panel()
        page.locator('#contribution-terms').check()
        before=len(posts)
        for invalid in ['', '0', '0,99', '500,01', '1,001', '1e2', '-3', '3 000']:
            page.locator('#contribution-amount').fill(invalid)
            page.locator('#contribution-submit').click()
            expect(page.locator('#contribution-status')).to_contain_text('Revisa la cantidad')
            assert len(posts) == before, invalid

        state['mode']='unsafe'
        page.locator('#contribution-amount').fill('5')
        page.locator('#contribution-submit').click()
        expect(page.locator('#contribution-status')).to_contain_text('no pertenece')
        assert urlsplit(page.url).netloc == urlsplit(BASE_URL).netloc
        expect(page.locator('#contribution-submit')).to_be_enabled()

        state['mode']='error'
        before=len(posts)
        page.locator('#contribution-submit').click()
        expect(page.locator('#contribution-status')).to_contain_text('no responde')
        expect(page.locator('#contribution-submit')).to_be_enabled()
        page.wait_for_timeout(800)
        assert len(posts) == before+1, 'payment failures must not automatically retry POST'

        state['mode']='network'
        before=len(posts)
        page.locator('#contribution-submit').click()
        expect(page.locator('#contribution-status')).to_contain_text('No se confirma ningún pago')
        expect(page.locator('#contribution-submit')).to_be_enabled()
        page.wait_for_timeout(800)
        assert len(posts) == before+1, 'network errors must not automatically retry POST'

        state['mode']='unavailable'
        page.locator('#contribution-submit').click()
        expect(page.locator('#contribution-status')).to_contain_text('no están disponibles')
        expect(page.locator('#contribution-submit')).to_be_disabled()
        expect(page.locator('#contribution-retry-config')).to_be_visible()

        state['available']=False
        open_panel()
        expect(page.locator('#contribution-status')).to_contain_text('no están disponibles')
        assert page.locator('[data-contribution-cents]:enabled').count() == 0
        page.locator('#contribution-amount').fill('7,50')
        before=len(posts)
        state['available']=True
        page.locator('#contribution-retry-config').click()
        expect(page.locator('#contribution-submit')).to_be_enabled()
        expect(page.locator('#contribution-amount')).to_have_value('7,50')
        assert len(posts) == before, 'availability retry must only fetch configuration'

        state['mode']='valid'
        open_panel('?contribution=processing')
        expect(page.locator('#contribution-return')).to_have_text('Has vuelto de Stripe. El pago se confirma en su justificante.')
        assert 'pago confirmado' not in page.locator('#contribution-return').inner_text().lower()
        open_panel('?contribution=cancelled')
        expect(page.locator('#contribution-return')).to_contain_text('Si realizaste un pago, comprueba su justificante')

        for width in [320,390,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            panel=page.locator('#contributions')
            panel.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
            assert page.locator('#contribution-submit').evaluate('node=>node.getBoundingClientRect().height>=44')
            page.locator('#contribution-amount').click()
            expect(page.locator('#contribution-amount')).to_be_focused()
            if width in [390,1440]:
                panel.screenshot(path=f'/tmp/electronicama-contributions-{width}.png')
        assert context.request.get(BASE_URL+'/api/account/me').json()['user'] is None
        assert not errors,errors
        browser.close()
    print('OK: guest contributions require consent, presets and exact decimal cents, no automatic payment/retry, unavailable state, safe Stripe destination and three widths')


if __name__ == '__main__':
    run()
