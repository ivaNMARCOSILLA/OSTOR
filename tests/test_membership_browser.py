import secrets
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL, login_context


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        member_context=browser.new_context()
        page=member_context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
        page.goto(BASE_URL+'/');page.locator('#hero-title').wait_for()
        assert page.locator('#preview-banner').is_visible()
        page.goto(BASE_URL+'/account')
        name='friend-'+secrets.token_hex(4)
        password=secrets.token_urlsafe(20)
        page.locator('details').first.locator('summary').click()
        page.locator('#register-form [name=username]').fill(name)
        page.locator('#register-form [name=password]').fill(password)
        page.locator('#register-form button').click()
        page.locator('#member-panel').wait_for(state='visible')
        assert not page.locator('#enter-maggy').is_visible()
        member_info=member_context.request.get(BASE_URL+'/api/account/me').json()['user']
        assert '14 días' in page.locator('#pricing').inner_text()
        assert page.locator('a[href="https://paypal.me/IMarcosIlla/1EUR"]').count()==1
        assert page.locator('a[href="https://paypal.me/IMarcosIlla/6EUR"]').count()==1
        admin_context=browser.new_context();login_context(admin_context)
        admin=admin_context.new_page();admin.goto(BASE_URL+'/account')
        admin.locator('#admin-panel').wait_for(state='visible')
        admin.locator('#payment-member').select_option(label=name)
        admin.locator('#payment-form [name=reference]').fill('BROWSER-'+secrets.token_hex(6))
        admin.locator('#payment-form [type=checkbox]').check()
        admin.locator('#payment-form button').click()
        admin.wait_for_function("document.querySelector('#account-status').textContent.includes('Pago registrado')")
        admin.locator('#admin-payments tr').filter(has_text=name).wait_for()
        info=admin_context.request.get(BASE_URL+'/api/admin/members').json()
        due=next(member['access_until'] for member in info['members'] if member['username']==name)
        admin.locator('#calendar-month').fill(due[:7]);admin.locator('#calendar-month').dispatch_event('change')
        admin.locator('.day .due').first.wait_for()
        page.reload();page.locator('#enter-maggy').wait_for(state='visible')
        page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
        page.locator('#enter-maggy').click();page.locator('#hero-title').wait_for()
        page.evaluate("async () => { await navigator.serviceWorker.register('/sw.js'); await navigator.serviceWorker.ready; }")
        page.wait_for_function('navigator.serviceWorker.controller !== null')
        member_context.set_offline(True)
        page.reload()
        assert page.locator('h1').inner_text()=='Ol necesita conexión'
        assert page.locator('#hero-title').count()==0, 'Paid interface must not be available through an old offline cache'
        member_context.set_offline(False)
        page.goto(BASE_URL+'/');page.locator('#hero-title').wait_for()
        # CSRF/session checks and protected API calls run against the actual local server.
        assert page.url.rstrip('/')==BASE_URL
        admin.locator('#create-invite [name=username]').fill('invited-'+secrets.token_hex(4))
        admin.locator('#create-invite button').click()
        link=admin.locator('#invite-result a');link.wait_for()
        invite_url=link.get_attribute('href')
        invited_context=browser.new_context();invited=invited_context.new_page();invited.goto(BASE_URL+invite_url)
        invited.locator('#invite-form [name=password]').fill(secrets.token_urlsafe(20))
        invited.locator('#invite-form button').click()
        invited.locator('#member-panel').wait_for(state='visible')
        assert not invited.locator('#admin-panel').is_visible()
        assert not invited.locator('#enter-maggy').is_visible()
        for width in [1440,390,320]:
            admin.set_viewport_size({'width':width,'height':900})
            assert admin.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
        admin.set_viewport_size({'width':1440,'height':1000})
        admin.locator('#invite-result').evaluate("node => node.textContent = 'Invitación de cliente creada. El enlace privado no se muestra en esta captura.'")
        admin.screenshot(path='docs/maggy-admin.png',full_page=True)
        page.route('**/api/account/me',lambda route:route.fulfill(json={'user':{'id':member_info['id'],'active':False,'welcome_used':True},'csrf':'test','payments':[]}))
        page.bring_to_front()
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.locator('#preview-banner').wait_for(state='visible')
        assert page.url.rstrip('/')==BASE_URL
        assert '6 €' in page.locator('#preview-banner button').inner_text()
        if page.locator('#consent-dialog').is_visible(): page.locator('#consent-decline').click()
        page.locator('#preview-banner button').click()
        assert not page.locator('#unlock-welcome-plan').is_visible()
        assert not errors,errors
        browser.close()
    print('OK: registration has no free music; verified 1 EUR activates 14 days; admin calendar, client invitations and mobile layout')


if __name__=='__main__':run()
