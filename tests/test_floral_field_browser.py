"""A thousand SVG flowers stay behind real controls without changing page layout."""
from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context


PAGES = ['/', '/account', '/live', '/legal/aviso-legal.html',
         '/legal/privacidad.html', '/legal/cookies.html']
WIDTHS = [320, 390, 768, 1440]
FLOWERS = '#floral-field use.floral-field-flower'


def settle(page):
    page.evaluate('() => new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel = page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button', name='Solo necesarias', exact=True).click()


def wait_field(page):
    expect(page.locator(FLOWERS)).to_have_count(1000)
    page.wait_for_function('''() => {
        const field=document.querySelector('#floral-field');
        const box=field.getBoundingClientRect(),view=field.viewBox.baseVal;
        return box.width>0 && box.height>0 && Math.abs(box.width-view.width)<1.5
            && Math.abs(box.height-view.height)<1.5;
    }''')
    settle(page)


def check_field(page, width):
    page.set_viewport_size({'width': width, 'height': 1000})
    wait_field(page)
    field = page.locator('#floral-field')
    expect(field).to_have_attribute('aria-hidden', 'true')
    expect(field).to_have_attribute('role', 'presentation')
    expect(field).to_have_attribute('focusable', 'false')
    expect(field).to_have_attribute('tabindex', '-1')
    assert field.evaluate("node=>getComputedStyle(node).pointerEvents==='none'")
    assert field.locator('image,script,foreignObject,a,input,button').count() == 0
    assert field.evaluate('''node=>[...node.querySelectorAll('use')].every(flower=>{
        const reference=flower.getAttribute('href');
        return reference?.startsWith('#') && !!node.querySelector(reference);
    })'''), 'every flower must reuse a local drawing, without an image request'
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'), (page.url, width)
    assert page.evaluate('''() => [...document.querySelectorAll('#floral-field use.floral-field-flower')]
        .every((flower,index)=>flower===window.fieldNodesBeforeResize[index])'''), 'resize replaced flowers'
    # Hiding an absolute decoration must not shorten the page or shift content.
    before = page.evaluate('document.documentElement.scrollHeight')
    field.evaluate("node=>node.style.display='none'")
    settle(page)
    without = page.evaluate('document.documentElement.scrollHeight')
    field.evaluate("node=>node.style.removeProperty('display')")
    wait_field(page)
    restored = page.evaluate('document.documentElement.scrollHeight')
    assert max(before, without, restored)-min(before, without, restored) <= 2, (page.url, width, before, without, restored)
    if width <= 768:
        dock = page.locator('#mobile-dock')
        expect(dock).to_be_visible()
        assert dock.evaluate('''node=>{
            const r=node.getBoundingClientRect();
            return r.left>=-1 && r.right<=innerWidth+1 && r.bottom<=innerHeight+1 && r.top>=0;
        }'''), 'the decorative layer moved fixed mobile navigation'


def remember_field(page):
    wait_field(page)
    page.evaluate("window.fieldNodesBeforeResize=[...document.querySelectorAll('#floral-field use.floral-field-flower')]")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 390, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.route('**/api/search?*', lambda route: route.fulfill(json=[]))
        for path in PAGES:
            page.goto(BASE_URL + path)
            close_preferences(page)
            # Live presence and status polls intentionally keep the network busy.
            # Wait for the actual artwork and font layout instead.
            page.evaluate('async()=>{await document.fonts.ready}')
            remember_field(page)
            for width in WIDTHS:
                check_field(page, width)

        # Real clicks exercise the foreground; no force or event dispatch can
        # conceal a decoration intercepting the user's pointer.
        page.set_viewport_size({'width': 390, 'height': 1000})
        page.goto(BASE_URL + '/')
        close_preferences(page)
        page.locator('#search-input').fill('margaritas libres')
        page.locator('#search-form button[type=submit]').click()
        expect(page.locator('#search-input')).to_have_value('margaritas libres')
        page.locator('#mobile-dock a[href="/account"]').click()
        expect(page).to_have_url(BASE_URL + '/account')
        page.locator('#register-form [name=username]').click()
        expect(page.locator('#register-form [name=username]')).to_be_focused()
        page.locator('#login-form [name=username]').click()
        expect(page.locator('#login-form [name=username]')).to_be_focused()

        # System accessibility modes hide the decoration while keeping its
        # original nodes ready when the user returns to the normal palette.
        remember_field(page)
        page.emulate_media(forced_colors='active')
        expect(page.locator('#floral-field')).to_be_hidden()
        page.emulate_media(forced_colors='none')
        check_field(page, 390)

        admin_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        login_context(admin_context)
        admin_page = admin_context.new_page()
        admin_posts = []
        admin_page.on('pageerror', lambda error: errors.append(str(error)))
        admin_page.on('request', lambda request: admin_posts.append(request.url)
                      if request.method == 'POST' and '/api/admin/' in request.url else None)
        admin_page.goto(BASE_URL + '/account')
        close_preferences(admin_page)
        expect(admin_page.locator('#admin-panel')).to_be_visible()
        remember_field(admin_page)
        for width in WIDTHS:
            check_field(admin_page, width)
            refresh = admin_page.locator('#admin-refresh-now')
            expect(refresh).to_be_enabled()
            refresh.click()
            expect(refresh).to_be_enabled()
            wait_field(admin_page)
            assert admin_page.evaluate('''() => [...document.querySelectorAll('#floral-field use.floral-field-flower')]
                .every((flower,index)=>flower===window.fieldNodesBeforeResize[index])'''), 'administration refresh replaced flowers'
        assert not admin_posts, admin_posts
        assert not errors, errors
        browser.close()
    print('OK: exactly1000 reused SVG flowers on six pages, stable nodes, correct constrained legal sizing, no layout growth, reachable search/forms/admin controls and fixed mobile dock at four widths')


if __name__ == '__main__':
    run()
