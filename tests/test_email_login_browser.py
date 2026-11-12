"""Email codes gate actual sessions; the audit stays private and contains no codes."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import time

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL


WIDTHS = [320, 390, 768, 1440]


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    panel = page.locator('#visitor-consent-panel')
    if panel.count() and panel.is_visible():
        panel.get_by_role('button', name='Solo necesarias', exact=True).click()


def messages_for(email):
    path = Path(os.environ['OL_TEST_MAIL_CAPTURE_DIR']) / (hashlib.sha256(email.encode()).hexdigest() + '.jsonl')
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def latest_code(page, email, after=0):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        rows = messages_for(email)
        for row in reversed(rows[after:]):
            found = re.search(r'c[oó]digo[^\d]{0,80}(\d{6})\b', row.get('body', ''), re.I)
            if found:
                return found.group(1)
        page.wait_for_timeout(30)
    raise AssertionError('The isolated mail capture did not receive an access code')


def check_widths(page):
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'), width


def verify_code(page, code):
    page.locator('#login-email-code').fill(code)
    page.locator('#login-code-submit').click()


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        context = browser.new_context(viewport={'width': 390, 'height': 1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(BASE_URL + '/account?next=%2Fvideos%23video-upload')
        close_preferences(page)
        page.wait_for_function("document.querySelector('#register-form [name=email]').required")
        username = 'email-gate-' + secrets.token_hex(4)
        email = username + '@example.test'
        password = secrets.token_urlsafe(24)
        form = page.locator('#register-form')
        form.locator('[name=username]').fill(username)
        form.locator('[name=email]').fill(email)
        form.locator('[name=password]').fill(password)
        page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
        page.locator('#registration-human-answer').fill('OL234')
        page.locator('#registration-submit').click()
        expect(page.locator('#login-code-panel')).to_be_visible()
        assert context.request.get(BASE_URL + '/api/account/me').json()['user'] is None
        expect(page.locator('#register-form [name=password]')).to_have_value('')
        expect(page.locator('#login-code-resend')).to_be_disabled()
        check_widths(page)
        page.set_viewport_size({'width': 390, 'height': 1000})
        # The preview contains no secret: the input is empty before capture.
        page.locator('#login-code-panel').screenshot(path='/tmp/electronicama-email-code-mobile.png')
        first_code = latest_code(page, email)
        wrong = '000000' if first_code != '000000' else '111111'
        verify_code(page, wrong)
        expect(page.locator('#login-code-status')).to_contain_text('código', ignore_case=True)
        expect(page.locator('#login-code-panel')).to_be_visible()
        assert context.request.get(BASE_URL + '/api/account/me').json()['user'] is None
        verify_code(page, first_code)
        expect(page).to_have_url(BASE_URL + '/videos#video-upload')
        account = context.request.get(BASE_URL + '/api/account/me').json()
        assert account['user']['username'] == username
        assert account['profile']['email_verified'] is True
        assert context.request.get(BASE_URL + '/api/admin/login-audit').status == 403

        # A second entry asks for a fresh code even after this mailbox was verified.
        page.goto(BASE_URL + '/account')
        page.locator('#logout').click()
        expect(page.locator('#login-form')).to_be_visible()
        before = len(messages_for(email))
        page.locator('#login-form [name=username]').fill(username)
        page.locator('#login-form [name=password]').fill(password)
        page.locator('#login-form button[type=submit]').click()
        expect(page.locator('#login-code-panel')).to_be_visible()
        assert context.request.get(BASE_URL + '/api/account/me').json()['user'] is None
        expect(page.locator('#login-form [name=password]')).to_have_value('')
        second_code = latest_code(page, email, after=before)
        verify_code(page, second_code)
        expect(page.locator('#member-panel')).to_be_visible()
        expect(page.locator('#login-security-audit')).to_be_hidden()

        # The seeded administrator enrolls its first mailbox through the real
        # credential form, then opens a genuinely role-protected audit.
        admin_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        admin_page = admin_context.new_page()
        admin_page.on('pageerror', lambda error: errors.append(str(error)))
        admin_page.goto(BASE_URL + '/account')
        close_preferences(admin_page)
        admin_form = admin_page.locator('#login-form')
        admin_form.locator('[name=username]').fill(os.environ['MAGGY_TEST_USER'])
        admin_form.locator('[name=password]').fill(os.environ['MAGGY_TEST_PASSWORD'])
        admin_form.locator('button[type=submit]').click()
        expect(admin_page.locator('#login-verification-email-label')).to_be_visible()
        admin_email = 'admin-email-gate@example.test'
        admin_form.locator('[name=verification_email]').fill(admin_email)
        admin_form.locator('button[type=submit]').click()
        expect(admin_page.locator('#login-code-panel')).to_be_visible()
        assert admin_context.request.get(BASE_URL + '/api/account/me').json()['user'] is None
        verify_code(admin_page, latest_code(admin_page, admin_email))
        expect(admin_page.locator('#admin-panel')).to_be_visible()
        admin_page.locator('#login-security-audit>summary').click()
        expect(admin_page.locator('.login-audit-event').first).to_be_visible()
        audit = admin_context.request.get(BASE_URL + '/api/admin/login-audit').json()
        assert audit['email_code_required'] is True
        assert audit['total'] > 0
        assert all(not ({'code', 'password', 'token', 'raw_ip'} & set(event)) for event in audit['events'])
        check_widths(admin_page)
        assert not errors, errors
        browser.close()
    print('OK: code-gated registration and repeat login, wrong-code rejection, cleared credentials, verified mailbox, safe video return, first-mailbox enrollment, private audit and four widths')


if __name__ == '__main__':
    run()
