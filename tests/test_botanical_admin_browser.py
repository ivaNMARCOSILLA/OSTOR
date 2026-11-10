"""Botanical administration stays usable and separate from ordinary account access."""
import secrets

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context


WIDTHS = [320, 390, 768, 1440]


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel = page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button', name='Solo necesarias', exact=True).click()


def check_leaves(page):
    strips = page.locator('.botanical-interface:not(.botanical-interface-inline)')
    expect(strips.first).to_be_visible()
    art = strips.first.locator('img').first
    expect(art).to_be_visible()
    expect(art).to_have_js_property('complete', True)
    assert art.evaluate("image=>image.naturalWidth>0")
    assert strips.first.evaluate("node=>getComputedStyle(node).pointerEvents==='none'")
    assert strips.first.get_attribute('aria-hidden') == 'true'
    assert strips.first.locator('a,button,input,[tabindex]').count() == 0
    assert page.locator('#granel-poster,.search-granel-banner').count() == 0
    assert '72 horas son de granel' not in page.locator('body').inner_text().lower()


def check_width(page, width):
    page.set_viewport_size({'width': width, 'height': 1000})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'), (page.url, width)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        guest_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        page = guest_context.new_page()
        errors = []
        obsolete_requests = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: obsolete_requests.append(request.url)
                if 'granel-72-horas' in request.url else None)
        page.route('**/api/search?*', lambda route: route.fulfill(json=[]))
        for path in ['/', '/account', '/live']:
            page.goto(BASE_URL + path)
            close_preferences(page)
            check_leaves(page)
            for width in WIDTHS:
                check_width(page, width)
            if path == '/account':
                expect(page.locator('#admin-panel')).to_be_hidden()
                assert guest_context.request.get(BASE_URL + '/api/admin/members').status == 403

        for path, expected_type in [('/assets/botanical-leaf.svg', 'image/svg+xml'),
                                     ('/assets/botanical-leaves.css', 'text/css')]:
            response = guest_context.request.get(BASE_URL + path)
            assert response.status == 200
            assert expected_type in response.headers.get('content-type', ''), response.headers

        # A member can choose the same public nickname as the new presentation,
        # but the server role and administrative visibility must remain member-only.
        page.goto(BASE_URL + '/account')
        close_preferences(page)
        username = 'leaf-member-' + secrets.token_hex(4)
        page.locator('#register-form [name=username]').fill(username)
        page.locator('#register-form [name=password]').fill('botanical-member-password-123')
        page.locator('#register-form [name=nickname]').fill('Fruto del padre')
        page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
        page.locator('#registration-human-answer').fill('OL234')
        page.locator('#registration-submit').click()
        expect(page.locator('#member-panel')).to_be_visible()
        expect(page.locator('#member-title')).to_contain_text('Fruto del padre')
        expect(page.locator('#admin-panel')).to_be_hidden()
        member = guest_context.request.get(BASE_URL + '/api/account/me').json()['user']
        assert member['role'] == 'member'
        assert member['username'] == username
        assert guest_context.request.get(BASE_URL + '/api/admin/members').status == 403
        check_leaves(page)

        admin_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        admin = login_context(admin_context)
        admin_page = admin_context.new_page()
        admin_posts = []
        admin_page.on('pageerror', lambda error: errors.append(str(error)))
        admin_page.on('request', lambda request: admin_posts.append(request.url)
                      if request.method == 'POST' and '/api/admin/' in request.url else None)
        admin_page.goto(BASE_URL + '/account')
        close_preferences(admin_page)
        expect(admin_page.locator('#admin-panel')).to_be_visible()
        expect(admin_page.locator('#admin-persona-title')).to_have_text('Fruto del padre')
        expect(admin_page.locator('#admin-session-identity')).to_contain_text('@' + admin['username'])
        expect(admin_page.locator('#admin-rosas-flores-memory')).to_contain_text('Rosas y Flores · Admin')
        expect(admin_page.locator('#admin-ivanix-memory')).to_contain_text('IVANIX')
        assert admin_page.locator('#admin-ivanix-memory input,#admin-ivanix-memory button,#admin-ivanix-memory form').count() == 0
        assert admin_context.request.get(BASE_URL + '/api/admin/members').status == 200
        check_leaves(admin_page)
        for width in WIDTHS:
            check_width(admin_page, width)
            # These are ordinary Playwright clicks: an ornament covering the
            # actual refresh button would fail the actionability check.
            refresh = admin_page.locator('#admin-refresh-now')
            expect(refresh).to_be_enabled()
            refresh.click()
            expect(refresh).to_be_enabled()
            expect(admin_page.locator('#admin-session-identity')).to_contain_text('@' + admin['username'])
            if width in [390, 1440]:
                admin_page.locator('.admin-botanical-hero').scroll_into_view_if_needed()
                admin_page.screenshot(path=f'/tmp/electronicama-leaf-admin-{width}.png')
        # The refreshed presentation must not clear a profile edit or overwrite
        # the authenticated account with the commemorative name.
        admin_page.locator('#profile-settings>summary').click()
        nickname = admin_page.locator('#profile-form [name=nickname]')
        nickname.fill('Borrador de perfil que debe conservarse')
        admin_page.locator('#admin-refresh-now').click()
        expect(admin_page.locator('#admin-refresh-now')).to_be_enabled()
        expect(nickname).to_have_value('Borrador de perfil que debe conservarse')
        account = admin_context.request.get(BASE_URL + '/api/account/me').json()['user']
        assert account['id'] == admin['id'] and account['username'] == admin['username']
        assert account['role'] == 'admin'
        assert not admin_posts, admin_posts
        assert not obsolete_requests, obsolete_requests
        assert not errors, errors
        browser.close()
    print('OK: poster removal, leaves on all three pages, separate admin/memorial identity, guest/member protection, draft preservation and usable controls at four widths')


if __name__ == '__main__':
    run()
