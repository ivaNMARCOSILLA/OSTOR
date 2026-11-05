"""Founder updates are queued without overwriting unsaved signature edits."""
from copy import deepcopy
import time

from playwright.sync_api import Error, expect, sync_playwright
from browser_support import BASE_URL


HTML='''<!doctype html><html lang="es"><body>
<button id="outside">Fuera del formulario</button><section id="founders">
<span id="founder-remaining"></span><p id="founder-counter"></p><progress id="founder-progress" max="100"></progress>
<fieldset id="founder-human-check" class="hidden"><input id="human-answer"><img id="human-image"><p id="human-status"></p><button id="human-refresh" type="button">Otro código</button></fieldset>
<button id="founder-claim" type="button"></button><p id="founder-status"></p><a id="founder-studio" href="#outside">Estudio</a>
<details id="my-founder-signature" open><summary>Personalizar</summary><form id="founder-signature-form">
<select id="founder-mode"><option value="numero">Número</option><option value="letra">Letra</option><option value="cancion">Canción</option><option value="sonido">Sonido</option></select>
<label id="founder-letter-label">Letra<input id="founder-letter" maxlength="1"></label>
<label>Mensaje<input id="founder-caption" maxlength="40"></label>
<label id="founder-voice-label">Sonido<select id="founder-voice"><option value="brisa">Brisa</option><option value="aurora">Aurora</option></select></label>
<div id="founder-song-panel"><input id="founder-audio-query"><button id="founder-audio-search" type="button">Buscar audio</button><div id="founder-audio-results"></div></div>
<button id="founder-signature-save" type="submit">Guardar</button><p id="founder-signature-status"></p>
</form><div id="founder-signature-preview"></div></details></section>
<style>.hidden{display:none}</style><script type="module" src="/assets/founders.js"></script></body></html>'''


def wait_callback(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'Expected intercepted founder request'
        page.wait_for_timeout(20)


def emit(page,event='ol:interface-update'):
    if event=='ol:interface-update':
        page.evaluate("window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}))")
    else:page.evaluate('(event)=>window.dispatchEvent(new Event(event))',event)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page();page.clock.install();errors=[];navigations=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
        account={'id':'founder-fixture','role':'admin','live_annual':True,'founder_active':True}
        activity={'eligible':True,'activity_exempt':True}
        state={'signature':{'mode':'letra','letter':'A','caption':'Primera','audio':None},'claimed':1}
        held_reads=[];held_posts=[];reads=[];posts=[];hold={'read':False,'post':False}
        track={'id':'archive_founder_fixture','title':'Audio elegido','channel':'Artista de prueba','source':'ARCHIVE'}
        def payload():
            return {'limit':100,'claimed':state['claimed'],'remaining':100-state['claimed'],
                'ownership_permanent':True,'mine':{'number':1,'ownership_permanent':True,'ownership':{'number':1,'permanent':True,'exclusive':True},'revoked_at':None,'activity':deepcopy(activity),'signature':deepcopy(state['signature'])}}
        def read(route):
            reads.append(route.request.url);data=payload()
            if hold['read']:
                hold['read']=False;held_reads.append((route,data));return
            route.fulfill(json=data)
        def write(route):
            data=route.request.post_data_json;posts.append(data)
            signature={'mode':data['mode'],'letter':data['letter'].upper() if data['mode']=='letra' else '',
                'caption':data['caption'] or 'Buen rollo','audio':{'kind':'track','track':track} if data['mode']=='cancion' else None}
            state['signature']=deepcopy(signature)
            response={'ok':True,'number':1,'signature':signature}
            if hold['post']:
                hold['post']=False;held_posts.append((route,response));return
            route.fulfill(json=response)
        page.route('**/founder-refresh-harness',lambda route:route.fulfill(content_type='text/html',body=HTML))
        page.route('**/api/account/me',lambda route:route.fulfill(json={'csrf':'fixture-csrf','user':deepcopy(account)}))
        page.route('**/api/live/founders',read)
        page.route('**/api/live/founders/signature',write)
        page.route('**/api/live/founders/audio-search?*',lambda route:route.fulfill(json={'tracks':[{'track':track,'token':'fixture-audio-token'}]}))
        page.goto(BASE_URL+'/founder-refresh-harness')
        emblem=page.locator('.founder-personal-emblem')
        expect(emblem).to_have_text('A')
        expect(page.locator('#founder-counter')).to_have_text('1 de 100 insignias de fundador asignadas')

        # A real server snapshot changes both the preview and the aggregate,
        # without navigating or recreating an unchanged preview node.
        page.evaluate("window.firstPreview=document.querySelector('#founder-signature-preview').firstElementChild")
        emit(page);page.wait_for_timeout(80)
        assert page.evaluate("window.firstPreview===document.querySelector('#founder-signature-preview').firstElementChild")
        state['signature'].update(letter='B',caption='Remota');state['claimed']=2
        emit(page);expect(emblem).to_have_text('B')
        expect(page.locator('#founder-counter')).to_have_text('2 de 100 insignias de fundador asignadas')

        # Pristine focused fields defer application; leaving the form drains it.
        page.locator('#founder-caption').focus()
        state['signature'].update(letter='C',caption='Tras salir')
        before=len(reads);emit(page);wait_callback(page,lambda:len(reads)>before)
        expect(emblem).to_have_text('B')
        page.locator('#outside').click();expect(emblem).to_have_text('C')

        # Dirty fields survive remote changes even after blur. Only a confirmed
        # explicit save clears the draft.
        page.locator('#founder-letter').fill('D');page.locator('#founder-caption').fill('Mi borrador')
        page.locator('#outside').click();state['signature'].update(letter='E',caption='Otra edición')
        state['claimed']=3;emit(page)
        expect(page.locator('#founder-counter')).to_have_text('3 de 100 insignias de fundador asignadas')
        expect(page.locator('#founder-letter')).to_have_value('D');expect(emblem).to_have_text('D')
        page.locator('#founder-signature-save').click()
        expect(page.locator('#founder-signature-status')).to_contain_text('Insignia personalizada')
        assert posts[-1]['letter']=='D' and posts[-1]['caption']=='Mi borrador'
        page.locator('#outside').click()

        # Hold an older GET while a local POST confirms a different signature.
        hold['read']=True;emit(page);wait_callback(page,lambda:bool(held_reads))
        page.locator('#founder-letter').fill('F');page.locator('#founder-signature-save').click()
        expect(page.locator('#founder-signature-save')).to_be_enabled()
        expect(emblem).to_have_text('F')
        page.evaluate("""()=>{window.emblemHistory=[];new MutationObserver(()=>window.emblemHistory.push(document.querySelector('.founder-personal-emblem')?.textContent)).observe(document.querySelector('#founder-signature-preview'),{childList:true,subtree:true,characterData:true})}""")
        route,data=held_reads.pop(0);route.fulfill(json=data)
        page.locator('#outside').click();page.wait_for_timeout(100)
        expect(emblem).to_have_text('F')
        assert all(value=='F' for value in page.evaluate('window.emblemHistory'))

        # New edits made while a save is in flight are still an unsaved draft
        # after that older save response arrives.
        page.locator('#founder-letter').fill('G');hold['post']=True
        page.locator('#founder-signature-save').click();wait_callback(page,lambda:bool(held_posts))
        page.locator('#founder-letter').fill('H');page.locator('#founder-caption').fill('Edición posterior')
        route,data=held_posts.pop(0);route.fulfill(json=data)
        expect(page.locator('#founder-signature-save')).to_be_enabled()
        expect(page.locator('#founder-signature-status')).to_contain_text('todavía no has guardado')
        expect(page.locator('#founder-letter')).to_have_value('H');expect(emblem).to_have_text('H')
        page.locator('#outside').click();state['signature'].update(letter='I');emit(page);page.wait_for_timeout(80)
        expect(page.locator('#founder-letter')).to_have_value('H')
        page.locator('#founder-signature-save').click();expect(page.locator('#founder-signature-save')).to_be_enabled()
        page.locator('#outside').click()

        # Choosing audio is an edit too, so a remote signature cannot clear its
        # selected track or signed selection token before the save.
        page.locator('#founder-mode').select_option('cancion');page.locator('#founder-audio-query').fill('piano')
        page.locator('#founder-audio-search').click();page.locator('#founder-audio-results button').click()
        page.locator('#outside').click();state['signature'].update(mode='letra',letter='J',audio=None)
        emit(page);page.wait_for_timeout(80)
        expect(page.locator('#founder-mode')).to_have_value('cancion')
        expect(page.locator('#founder-signature-preview')).to_contain_text('Audio elegido')
        page.locator('#founder-signature-save').click();expect(page.locator('#founder-signature-save')).to_be_enabled()
        assert posts[-1]['audio_token']=='fixture-audio-token'
        page.locator('#outside').click()
        page.wait_for_timeout(120)

        # Signals received while hidden remain pending until the document is
        # visible; no hidden polling is required to bring the emblem up to date.
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>true})")
        before=len(reads);state['signature'].update(mode='letra',letter='K',audio=None)
        emit(page);page.wait_for_timeout(80);assert len(reads)==before
        page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,get:()=>false});document.dispatchEvent(new Event('visibilitychange'))")
        expect(emblem).to_have_text('K')

        # A hung public read is aborted after eight seconds, then a lifecycle
        # signal starts a new read. Later signals received while busy are queued.
        hold['read']=True;emit(page);wait_callback(page,lambda:bool(held_reads))
        page.clock.fast_forward(8500)
        expect(page.locator('#founder-status')).to_contain_text('Volveremos a intentarlo')
        old,_=held_reads.pop(0)
        try:old.abort()
        except Error:pass
        state['signature'].update(letter='L');emit(page,'online');expect(emblem).to_have_text('L')
        hold['read']=True;emit(page);wait_callback(page,lambda:bool(held_reads))
        before=len(reads);state['signature'].update(letter='M');emit(page)
        route,data=held_reads.pop(0);route.fulfill(json=data)
        expect(emblem).to_have_text('M');assert len(reads)>before
        # A permanent owner can still personalize after service/activity expires,
        # but the preview must not advertise permission to start a broadcast.
        account.update(role='member',live_annual=False,founder_active=False,streamer_active=False)
        activity.update(eligible=False,activity_exempt=False)
        emit(page);expect(page.locator('#founder-studio')).to_be_hidden()
        expect(page.locator('#my-founder-signature')).to_be_visible()
        expect(page.locator('#founder-status')).to_contain_text('personal, exclusivo y permanente')
        expect(emblem).to_have_text('M')
        state['signature'].update(letter='N');page.clock.fast_forward(31000)
        expect(emblem).to_have_text('N')
        assert len(navigations)==1,navigations
        assert not errors,errors
        browser.close()
    print('OK: queued founder updates, preserved focused/dirty/audio drafts, confirmed-save races, hidden return, timeout recovery and no navigation')


if __name__=='__main__':run()
