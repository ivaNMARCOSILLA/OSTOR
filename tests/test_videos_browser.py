"""Real upload bytes stay private until a moderator publishes the community video."""
import secrets
import re
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

from browser_support import BASE_URL, login_context


WIDTHS = [320, 390, 768, 1440]
R2_HOST = 'video-browser.r2.cloudflarestorage.com'


def close_preferences(page):
    if page.locator('#consent-decline').is_visible():
        page.locator('#consent-decline').click()
    popup = page.locator('#visitor-consent-panel')
    if popup.count() and popup.is_visible():
        popup.get_by_role('button', name='Solo necesarias', exact=True).click()


def install_r2_routes(context, failures):
    def route_storage(route):
        request = route.request
        origin = request.headers.get('origin', BASE_URL)
        cors = {'Access-Control-Allow-Origin': origin,
                'Access-Control-Allow-Methods': 'GET,HEAD,PUT,OPTIONS',
                'Access-Control-Allow-Headers': 'content-type,range',
                'Access-Control-Expose-Headers': 'ETag,Content-Range,Accept-Ranges'}
        if request.method == 'OPTIONS':
            route.fulfill(status=204, headers=cors)
            return
        if request.method == 'PUT' and failures.get('enabled'):
            failures['attempts'] = failures.get('attempts', 0) + 1
            route.fulfill(status=503, headers=cors, body='Isolated interrupted upload')
            return
        path = urlsplit(request.url).path
        headers = {key: value for key, value in request.headers.items()
                   if key.lower() in {'content-type', 'range'}}
        response = context.request.fetch(BASE_URL + '/__video_fixture__' + path,
                                         method=request.method,
                                         headers=headers,
                                         data=request.post_data_buffer if request.method == 'PUT' else None,
                                         fail_on_status_code=False)
        result_headers = {key: value for key, value in response.headers.items()
                          if key.lower() not in {'connection', 'transfer-encoding', 'content-encoding'}}
        route.fulfill(status=response.status, headers=result_headers | cors, body=response.body())
    context.route('https://' + R2_HOST + '/**', route_storage)
    # Playwright does not re-route later URLs in a browser redirect chain.
    # Follow the real authorized media redirect using the isolated R2 transport;
    # application authorization and the issued private ticket are still checked.
    def route_media(route):
        headers = {key: value for key, value in route.request.headers.items()
                   if key.lower() == 'range'}
        response = context.request.get(route.request.url, headers=headers,
                                       max_redirects=0, fail_on_status_code=False)
        if response.status in {301, 302, 303, 307, 308}:
            target = urlsplit(response.headers['location'])
            assert target.scheme == 'https' and target.hostname == R2_HOST
            response = context.request.get(BASE_URL + '/__video_fixture__' + target.path,
                                           headers=headers, fail_on_status_code=False)
        output = {key: value for key, value in response.headers.items()
                  if key.lower() not in {'connection', 'transfer-encoding', 'content-encoding'}}
        route.fulfill(status=response.status, headers=output, body=response.body())
    context.route(re.compile(re.escape(BASE_URL) + r'/api/(?:admin/)?videos/[a-f0-9]{32}/(?:play|preview)(?:\?.*)?$'), route_media)



def register(page, prefix):
    username = prefix + '-' + secrets.token_hex(4)
    page.goto(BASE_URL + '/account')
    close_preferences(page)
    page.locator('#register-form [name=username]').fill(username)
    page.locator('#register-form [name=password]').fill('video-browser-password-123')
    page.wait_for_function("document.querySelector('#registration-human-id').value.length===32")
    page.locator('#registration-human-answer').fill('OL234')
    page.locator('#registration-submit').click()
    expect(page.locator('#member-panel')).to_be_visible()
    assert page.context.request.get(BASE_URL + '/api/account/me').json()['user']['role'] == 'member'
    return username


def genuine_webm(page):
    # Native MediaRecorder produces a playable file. A fake extension or a
    # fabricated header would not test either the upload sniffing or playback.
    payload = page.evaluate('''async()=>{
        const canvas=document.createElement('canvas');canvas.width=96;canvas.height=64;
        const drawing=canvas.getContext('2d');let frame=0;
        const draw=()=>{drawing.fillStyle=frame++%2?'#ae9aff':'#75e2eb';drawing.fillRect(0,0,96,64);drawing.fillStyle='#17121f';drawing.fillRect(frame%50,20,25,25);};
        draw();const stream=canvas.captureStream(12);
        const mime=MediaRecorder.isTypeSupported('video/webm;codecs=vp8')?'video/webm;codecs=vp8':'video/webm';
        const recorder=new MediaRecorder(stream,{mimeType:mime}),parts=[];
        recorder.ondataavailable=event=>{if(event.data.size)parts.push(event.data);};
        const stopped=new Promise(resolve=>recorder.onstop=resolve);
        const timer=setInterval(draw,70);recorder.start(100);
        await new Promise(resolve=>setTimeout(resolve,700));recorder.stop();await stopped;
        clearInterval(timer);stream.getTracks().forEach(track=>track.stop());
        return [...new Uint8Array(await new Blob(parts,{type:'video/webm'}).arrayBuffer())];
    }''')
    result = bytes(payload)
    assert result.startswith(b'\x1aE\xdf\xa3') and len(result) > 100
    return {'name': 'baile-propio.webm', 'mimeType': 'video/webm', 'buffer': result}


def my_videos(context):
    response = context.request.get(BASE_URL + '/api/videos/me')
    assert response.status == 200
    return response.json()['videos']


def csrf(context):
    return context.request.get(BASE_URL + '/api/account/me').json()['csrf']


def assert_widths(page):
    for width in WIDTHS:
        page.set_viewport_size({'width': width, 'height': 1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'), (page.url, width)
        assert page.locator('#mobile-dock').evaluate('''dock=>{
            if(!dock.getClientRects().length)return true;
            const box=dock.getBoundingClientRect();return box.left>=-1&&box.right<=innerWidth+1&&box.bottom<=innerHeight+1;
        }''')


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path='/usr/bin/chromium', args=['--no-sandbox'])
        owner_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        public_context = browser.new_context(viewport={'width': 390, 'height': 1000})
        admin_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        failures = {'enabled': False, 'attempts': 0}
        for context in [owner_context, public_context, admin_context]:
            install_r2_routes(context, failures)
        owner = owner_context.new_page();public = public_context.new_page();admin = admin_context.new_page()
        errors = []
        for page in [owner, public, admin]:
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('dialog', lambda dialog: dialog.accept())

        public.goto(BASE_URL + '/videos')
        expect(public.locator('#video-upload-guest')).to_be_visible()
        expect(public.locator('#video-admin')).to_be_hidden()
        assert public_context.request.get(BASE_URL + '/api/videos/me').status == 401
        assert public_context.request.get(BASE_URL + '/api/admin/videos').status == 403
        assert_widths(public)

        username = register(owner, 'video-owner')
        owner.goto(BASE_URL + '/videos#video-upload')
        expect(owner.locator('#video-upload-form')).to_be_visible()
        for width, name in [(390, 'mobile'), (1440, 'desktop')]:
            owner.set_viewport_size({'width': width, 'height': 1500})
            owner.locator('#video-upload').screenshot(path='/tmp/electronicama-video-upload-' + name + '.png')
        owner.set_viewport_size({'width': 390, 'height': 1000})

        expect(owner.locator('#video-admin')).to_be_hidden()
        assert owner_context.request.get(BASE_URL + '/api/admin/videos').status == 403
        sample = genuine_webm(owner)
        title = '<img src=x onerror="window.__videoXss=true"> Mi baile'
        owner.locator('#video-upload-title-input').fill(title)
        owner.locator('#video-upload-description').fill('Vídeo propio para probar la cuarentena de la comunidad.')
        owner.locator('#video-upload-category').select_option('dance')
        owner.locator('#video-upload-file').set_input_files(sample)
        started = []
        owner.on('request', lambda request: started.append(request.url)
                 if request.method == 'POST' and urlsplit(request.url).path == '/api/videos/uploads' else None)
        submit = owner.locator('#video-upload-submit')
        if submit.is_enabled():
            submit.click()
        assert not started, 'missing rights confirmation initiated an upload'
        owner.locator('#video-upload-rights').check()
        expect(submit).to_be_enabled()
        submit.click()
        expect(owner.locator('#video-upload-status')).to_contain_text('Vídeo en cuarentena.', timeout=20000)
        uploaded = my_videos(owner_context)
        assert len(uploaded) == 1
        entry = uploaded[0];ident = entry['id']
        assert entry['state'] == 'quarantined' and entry['technical_checked']
        assert entry['size_bytes'] == len(sample['buffer'])
        assert entry['author']['username'] == username
        assert not public_context.request.get(BASE_URL + '/api/videos').json()['videos']
        assert public_context.request.get(BASE_URL + '/api/videos/' + ident + '/play', max_redirects=0).status == 404
        assert owner_context.request.get(BASE_URL + '/api/admin/videos/' + ident + '/preview', max_redirects=0).status == 403
        expect(owner.locator('#video-mine-list [data-video-id="' + ident + '"]')).to_contain_text(title)
        assert owner.evaluate('window.__videoXss===undefined')

        login_context(admin_context)
        admin.goto(BASE_URL + '/videos#video-admin')
        review = admin.locator('#video-admin-list [data-video-id="' + ident + '"]')
        expect(review).to_be_visible()
        review.locator('summary').filter(has_text='Revisar vídeo').click()
        preview = review.locator('video')
        expect(preview).to_be_visible()
        preview.evaluate('video=>{video.muted=true;return video.play()}')
        admin.wait_for_function('''id=>document.querySelector('#video-admin-list [data-video-id="'+id+'"] video').currentTime>.1''', arg=ident)
        review.locator('[name=reason]').fill('Revisión manual del vídeo y de su descripción completada.')
        review.locator('[name=review_confirmed]').check()
        review.locator('[data-video-decision=approve]').click()
        expect(admin.locator('#video-admin-list [data-video-id="' + ident + '"]')).to_have_count(0)
        published = public_context.request.get(BASE_URL + '/api/videos').json()['videos']
        assert len(published) == 1 and published[0]['id'] == ident

        public.locator('#video-catalogue-refresh').click()
        card = public.locator('#video-catalogue-list [data-video-id="' + ident + '"]')
        expect(card).to_contain_text(title)
        assert card.locator('img[src=x]').count() == 0
        assert public.evaluate('window.__videoXss===undefined')
        movie = card.locator('video')
        movie.scroll_into_view_if_needed()
        movie.evaluate('video=>{video.muted=true;return video.play()}')
        public.wait_for_function('''id=>document.querySelector('#video-catalogue-list [data-video-id="'+id+'"] video').currentTime>.1''', arg=ident)
        for width in [390, 1440]:
            public.set_viewport_size({'width': width, 'height': 1000})
            public.locator('#video-catalogue').scroll_into_view_if_needed()
            public.screenshot(path=f'/tmp/video-zone-{width}.png')
        assert_widths(public)

        # A different free account reports the approved video. A report alone
        # does not allow that member to change its moderation state.
        register(public, 'video-reader')
        public.goto(BASE_URL + '/videos')
        card = public.locator('#video-catalogue-list [data-video-id="' + ident + '"]')
        expect(card).to_be_visible()
        card.locator('summary').filter(has_text='Informar de este vídeo').click()
        card.locator('[name=reason]').fill('Pido que administración vuelva a revisar el contenido y sus créditos.')
        with public.expect_response(lambda response: response.request.method == 'POST' and urlsplit(response.url).path == '/api/videos/' + ident + '/report') as reported:
            card.get_by_role('button', name='Enviar a revisión', exact=True).click()
        assert reported.value.status == 200
        assert public_context.request.get(BASE_URL + '/api/admin/videos').status == 403
        assert len(public_context.request.get(BASE_URL + '/api/videos').json()['videos']) == 1
        admin.locator('#video-admin-state').select_option('published')
        review = admin.locator('#video-admin-list [data-video-id="' + ident + '"]')
        expect(review).to_be_visible()
        if not review.locator('[name=reason]').is_visible():
            review.locator('summary').filter(has_text='Revisar vídeo').click()
        review.locator('[name=reason]').fill('Nueva revisión solicitada por la comunidad.')
        review.locator('[data-video-decision=quarantine]').click()
        expect(admin.locator('#video-admin-list [data-video-id="' + ident + '"]')).to_have_count(0)
        assert not public_context.request.get(BASE_URL + '/api/videos').json()['videos']
        assert public_context.request.get(BASE_URL + '/api/videos/' + ident + '/play', max_redirects=0).status == 404

        owner.locator('#video-mine-refresh').click()
        mine = owner.locator('#video-mine-list [data-video-id="' + ident + '"]')
        expect(mine).to_be_visible()
        mine.locator('[data-video-action=delete]').click()
        expect(owner.locator('#video-mine-list [data-video-id="' + ident + '"]')).to_have_count(0)
        assert not my_videos(owner_context)

        # A failed direct PUT never produces a published card or a successful
        # upload message. Retrying still goes through the real storage checks.
        failures['enabled'] = True
        owner.locator('#video-upload-title-input').fill('Subida interrumpida de prueba')
        owner.locator('#video-upload-file').set_input_files(sample)
        if not owner.locator('#video-upload-rights').is_checked():
            owner.locator('#video-upload-rights').check()
        owner.locator('#video-upload-submit').click()
        expect(owner.locator('#video-upload-progress-panel')).to_be_hidden(timeout=20000)
        expect(owner.locator('#video-upload-status')).to_have_attribute('data-kind', 'error')
        assert failures['attempts'] >= 1
        assert not public_context.request.get(BASE_URL + '/api/videos').json()['videos']
        assert all(item['state'] != 'published' for item in my_videos(owner_context))
        failures['enabled'] = False

        unavailable = owner_context.new_page()
        unavailable.route('**/api/videos/config', lambda route: route.fulfill(json={
            'storage_ready': False, 'max_file_bytes': 5 * 1024 ** 4,
            'allowed_mime_types': ['video/mp4', 'video/webm', 'video/quicktime']}))
        unavailable.goto(BASE_URL + '/videos#video-upload')
        expect(unavailable.locator('#video-storage-status')).to_contain_text('preparando')
        expect(unavailable.locator('#video-upload-submit')).to_be_disabled()
        assert not errors, errors
        browser.close()
    print('OK: genuine WebM direct upload, private quarantine, manual admin approval, actual public playback, report/re-quarantine/delete, interrupted PUT, XSS-safe titles, free account boundaries and responsive video controls')


if __name__ == '__main__':
    run()
