"""The registration notice follows server state and never confirms a payment itself."""
import base64
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import wave

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    popup=page.locator('#visitor-consent-panel')
    if popup.count() and popup.is_visible():
        popup.get_by_role('button',name='Solo necesarias',exact=True).click()


def tone():
    stream=BytesIO()
    with wave.open(stream,'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000)
        audio.writeframes(b'\0\0'*16000)
    return 'data:audio/wav;base64,'+base64.b64encode(stream.getvalue()).decode()


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
        context=browser.new_context(viewport={'width':390,'height':1000})
        base=context.request.get(BASE_URL+'/api/account/me').json()
        csrf=base['csrf']
        user={'id':'a'*32,'username':'fee-participant','nickname':'Participante de prueba','role':'member',
              'active':True,'complimentary':True,'full_service':False,'welcome_used':False,
              'founder_number':None,'founder_active':False,'access_until':None,'streamer_active':False}
        now=datetime.now(timezone.utc)
        state={'identity':'guest','fee':{'enabled':True,'required':True,'exempt':False,'paid':False,
                'in_grace':True,'grace_seconds':300,'grace_duration_seconds':300,
                'deadline':(now+timedelta(minutes=5)).isoformat(),'server_now':now.isoformat(),
                'price_cents':100,'currency':'eur','payment_available':True},
                'checkout_mode':'valid','reconcile_paid':False,'missing':False}
        fee_reads=[];checkout_posts=[];reconcile_posts=[];errors=[]

        def account_payload():
            payload=deepcopy(base)
            payload['user']=None if state['identity']=='guest' else deepcopy(user)
            if state['identity']=='admin':payload['user']['role']='admin'
            payload['registration_fee']=deepcopy(state['fee'])
            return payload

        def account(route):
            route.fulfill(json=account_payload())

        def fee(route):
            assert route.request.method=='GET'
            fee_reads.append(route.request.url)
            if state['missing']:route.fulfill(status=404,json={'error':'Endpoint anterior no disponible'});return
            data=deepcopy(state['fee'])
            if state['identity'] in {'guest','admin'}:
                data.update(required=False,exempt=True,in_grace=False,grace_seconds=0)
            route.fulfill(json=data)

        def checkout(route):
            assert route.request.method=='POST'
            assert route.request.headers.get('x-csrf-token')==csrf
            assert route.request.post_data_json=={'fee_terms':True}
            checkout_posts.append(route.request.post_data_json)
            if state['checkout_mode']=='error':route.fulfill(status=502,json={'error':'No se ha podido abrir Stripe. Inténtalo de nuevo.'});return
            target='https://checkout.stripe.com/c/pay/registration-fixture'
            if state['checkout_mode']=='unsafe':target='https://checkout.stripe.com.evil.example/c/pay/no'
            route.fulfill(json={'url':target})

        def reconcile(route):
            assert route.request.method=='POST'
            assert route.request.headers.get('x-csrf-token')==csrf
            assert route.request.post_data_json=={}
            reconcile_posts.append(route.request.post_data_json)
            if state['reconcile_paid']:state['fee'].update(paid=True,required=False,in_grace=False,grace_seconds=0)
            route.fulfill(json=deepcopy(state['fee']))

        context.route('**/api/account/me',account)
        context.route('**/api/account/registration-fee',fee)
        context.route('**/api/account/registration-fee/checkout',checkout)
        context.route('**/api/account/registration-fee/reconcile',reconcile)
        context.route('**/api/fee-browser-consumption',lambda route:route.fulfill(status=402,json={'code':'registration_fee_required','error':'Confirma el alta'}))
        context.route('**/api/search?*',lambda route:route.fulfill(json=[]))
        context.route('https://checkout.stripe.com/**',lambda route:route.fulfill(content_type='text/html',body='<html><body><h1>Checkout de alta de prueba</h1></body></html>'))

        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))

        def open_page(path='/'):
            page.goto(BASE_URL+path);close_preferences(page)
            page.wait_for_function('!!window.OlRegistrationFee')
            page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')

        open_page()
        assert not page.locator('#registration-payment:visible').count()
        assert not checkout_posts and not reconcile_posts
        state['identity']='admin';open_page()
        assert not page.locator('#registration-payment:visible').count()
        assert not page.evaluate('window.OlRegistrationFee.blocked')

        state['identity']='member';open_page()
        panel=page.locator('#registration-payment')
        expect(panel).to_be_visible()
        expect(panel).to_have_class(re.compile(r'.*\bregistration-payment--grace\b.*'))
        expect(page.locator('#registration-fee-copy')).to_contain_text('5 minutos')
        assert not page.evaluate('window.OlRegistrationFee.blocked')
        assert page.locator('#registration-fee-form').is_hidden()
        assert not checkout_posts

        # Expiry on the local clock requests authoritative state; it does not
        # declare a payment overdue while the server still grants grace.
        state['fee']['grace_seconds']=1
        page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')
        page.evaluate('''async source=>{
            const audio=document.createElement('audio');audio.id='fee-native-audio';
            audio.src=source;audio.loop=true;document.body.append(audio);await audio.play();
        }''',tone())
        expect(page.locator('#fee-native-audio')).to_have_js_property('paused',False)
        state['fee']['grace_seconds']=0
        expect(page.locator('#registration-fee-countdown')).to_have_text('Comprobando el estado del alta…')
        assert not page.evaluate('window.OlRegistrationFee.blocked')
        expect(page.locator('#fee-native-audio')).to_have_js_property('paused',False)

        state['fee']['in_grace']=False
        assert page.evaluate("async()=>{const r=await fetch('/api/fee-browser-consumption');return r.status}")==402
        expect(panel).to_have_class(re.compile(r'.*\bregistration-payment--due\b.*'))
        expect(page.locator('#fee-native-audio')).to_have_js_property('paused',True)
        assert page.evaluate('window.OlRegistrationFee.blocked')
        # Complimentary friends are not silently treated as exempt.
        assert user['complimentary'] is True
        expect(page.locator('#registration-fee-submit')).to_be_enabled()
        for href in ['/account#profile-settings','/legal/aviso-legal.html','/legal/privacidad.html']:
            expect(panel.locator('a[href="'+href+'"]')).to_be_visible()
        expect(page.locator('#registration-fee-logout')).to_be_enabled()

        page.locator('#registration-fee-submit').click()
        assert not checkout_posts, 'no checkout may start without explicit consent'
        page.locator('#registration-fee-terms').check()
        state['checkout_mode']='unsafe'
        page.locator('#registration-fee-submit').click()
        expect(page.locator('#registration-fee-status')).to_contain_text('no pertenece')
        assert page.url.startswith(BASE_URL)
        before=len(checkout_posts)
        state['checkout_mode']='error'
        page.locator('#registration-fee-submit').click()
        expect(page.locator('#registration-fee-status')).to_contain_text('No se ha podido abrir Stripe')
        page.wait_for_timeout(500)
        assert len(checkout_posts)==before+1, 'checkout failures must not automatically retry'

        state['checkout_mode']='valid'
        page.locator('#registration-fee-submit').click()
        expect(page).to_have_url('https://checkout.stripe.com/c/pay/registration-fixture')
        expect(page.get_by_role('heading',name='Checkout de alta de prueba')).to_be_visible()
        assert state['fee']['paid'] is False

        before=len(checkout_posts)
        open_page('/account?registration_fee=processing#registration-payment')
        expect(page.locator('#registration-payment')).to_be_visible()
        expect(page.locator('#registration-fee-return')).to_contain_text('Volver de Stripe no confirma el pago')
        assert page.evaluate('window.OlRegistrationFee.blocked')
        assert len(checkout_posts)==before, 'the Stripe return URL must not initiate another checkout'

        state['fee']['payment_available']=False
        page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')
        expect(page.locator('#registration-fee-submit')).to_be_disabled()
        expect(page.locator('#registration-fee-status')).to_contain_text('todavía no está disponible')
        for width in [320,390,768,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
            page.locator('#registration-fee-refresh').click()
            expect(page.locator('#registration-fee-logout')).to_be_enabled()
            if width in [390,1440]:page.locator('#registration-payment').screenshot(path=f'/tmp/registration-fee-{width}.png')

        # 'Already paid' only reconciles an existing payment and then reads the
        # persisted state. It never creates a new checkout or trusts a URL flag.
        page.locator('#registration-fee-reconcile').click()
        expect(page.locator('#registration-fee-status')).to_contain_text('Todavía no consta una confirmación')
        assert reconcile_posts==[{}] and len(checkout_posts)==before
        assert page.evaluate('window.OlRegistrationFee.blocked')
        state['reconcile_paid']=True
        page.locator('#registration-fee-reconcile').click()
        expect(page.locator('#registration-payment')).to_be_hidden()
        assert not page.evaluate('window.OlRegistrationFee.blocked')
        assert len(checkout_posts)==before

        # Mode-off, a missing older endpoint and an exempt account never create
        # a phantom paywall or a client-side "paid" record.
        state['fee'].update(paid=False,required=True,in_grace=False,enabled=False)
        page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')
        expect(page.locator('#registration-payment')).to_be_hidden()
        state['fee']['enabled']=True;state['missing']=True
        page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')
        expect(page.locator('#registration-payment')).to_be_hidden()
        state['missing']=False;state['fee']['exempt']=True
        page.evaluate('async()=>{await window.OlRegistrationFee.refresh()}')
        expect(page.locator('#registration-payment')).to_be_hidden()
        assert not errors,errors
        browser.close()
    print('OK: server-authoritative registration grace and expiry, guest/staff exemptions, paused media, explicit1€ Stripe checkout, safe return, reconciliation without new purchases and four widths')


if __name__=='__main__':
    run()
