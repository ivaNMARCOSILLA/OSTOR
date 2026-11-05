"""An older operational read cannot roll back a confirmed save or a draft."""
from copy import deepcopy
import time

from playwright.sync_api import expect, sync_playwright
from browser_support import BASE_URL


# The shared account module owns the draft markers. This small page supplies
# that contract while running the real operational module and HTTP requests.
HTML='''<!doctype html><html lang="es"><body>
<button id="outside">Fuera del formulario</button>
<form id="maintenance-form">
<label>Ámbito<select id="maintenance-scope"><option value="off">Disponible</option><option value="live">Directos</option><option value="payments">Pagos</option></select></label>
<label>Aviso<textarea id="maintenance-message"></textarea></label>
<button type="submit">Guardar mantenimiento</button></form><p id="operations-status"></p>
<section id="fan-alias-panel"><form id="fan-alias-form">
<label>Apodo<select id="fan-alias"><option value="">Sin apodo</option><option>Lola</option><option>Lolo</option><option>Loles</option></select></label>
<button type="submit">Guardar apodo</button><p id="fan-alias-status"></p></form></section>
<script>for(const event of ['input','change'])document.addEventListener(event,e=>{if(e.target.closest('form'))e.target.dataset.userDraft='true';});</script>
<script type="module" src="/assets/operations.js"></script></body></html>'''


def wait_callback(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'Expected intercepted operational request'
        page.wait_for_timeout(20)


def update(page):
    page.evaluate("window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true}}))")


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page();errors=[];posts=[];status_reads=[];fan_reads=[]
        held_manager=[];held_fan=[];hold={'manager':False,'fan':False}
        state={'maintenance':{'scope':'off','message':'Aviso anterior'},'alias':'Lola'}
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.route('**/operations-refresh-harness',lambda route:route.fulfill(content_type='text/html',body=HTML))
        page.route('**/api/account/me',lambda route:route.fulfill(json={'csrf':'fixture-csrf','user':{'id':'admin-fixture','role':'admin'}}))
        def status(route):
            status_reads.append(route.request.url)
            route.fulfill(json={'maintenance':deepcopy(state['maintenance']),'live_premiere':False})
        page.route('**/api/status',status)
        def manager(route):
            payload={'provider':'legacy_paypal','enabled':True}
            if hold['manager']:
                hold['manager']=False;held_manager.append((route,payload));return
            route.fulfill(json=payload)
        page.route('**/api/payments/status',manager)
        def maintenance(route):
            assert route.request.method=='POST'
            assert route.request.headers.get('x-csrf-token')=='fixture-csrf'
            payload=route.request.post_data_json;posts.append(('maintenance',payload))
            state['maintenance']=deepcopy(payload);route.fulfill(json={'ok':True})
        page.route('**/api/admin/maintenance',maintenance)
        def fan(route):
            if route.request.method=='POST':
                assert route.request.headers.get('x-csrf-token')=='fixture-csrf'
                payload=route.request.post_data_json;posts.append(('alias',payload))
                state['alias']=payload['alias'];route.fulfill(json={'ok':True});return
            fan_reads.append(route.request.url);payload={'alias':state['alias']}
            if hold['fan']:
                hold['fan']=False;held_fan.append((route,payload));return
            route.fulfill(json=payload)
        page.route('**/api/account/fan-alias',fan)
        page.goto(BASE_URL+'/operations-refresh-harness')
        expect(page.locator('#maintenance-message')).to_have_value('Aviso anterior')
        expect(page.locator('#fan-alias')).to_have_value('Lola')
        assert not posts,'Read-only inspection must not submit any changes'

        # Record assignments as well as the final UI, so a transient rollback
        # followed by a fresh read cannot hide the stale-response regression.
        page.evaluate('''()=>{window.controlAssignments=[];for(const id of ['maintenance-scope','maintenance-message','fan-alias']){
          const field=document.getElementById(id),descriptor=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field),'value');
          Object.defineProperty(field,'value',{configurable:true,get(){return descriptor.get.call(this);},set(value){window.controlAssignments.push([id,value]);descriptor.set.call(this,value);}});
        }}''')

        # The status snapshot is old, but its inspection is still waiting for
        # another GET when an explicit maintenance save succeeds.
        hold['manager']=True;update(page);wait_callback(page,lambda:bool(held_manager))
        page.locator('#maintenance-scope').select_option('live')
        page.locator('#maintenance-message').fill('Nuevo aviso confirmado')
        page.get_by_role('button',name='Guardar mantenimiento',exact=True).click()
        expect(page.locator('#operations-status')).to_contain_text('Estado guardado')
        page.locator('#outside').click()
        assert page.locator('#maintenance-message').get_attribute('data-user-draft') is None
        before=len(status_reads);page.evaluate('window.controlAssignments=[]')
        route,payload=held_manager.pop();route.fulfill(json=payload)
        wait_callback(page,lambda:len(status_reads)>before)
        expect(page.locator('#maintenance-scope')).to_have_value('live')
        expect(page.locator('#maintenance-message')).to_have_value('Nuevo aviso confirmado')
        wait_callback(page,lambda:len(fan_reads)>=3)
        page.wait_for_timeout(80)
        assignments=page.evaluate('window.controlAssignments')
        assert ['maintenance-scope','off'] not in assignments,assignments
        assert ['maintenance-message','Aviso anterior'] not in assignments,assignments
        assert len(posts)==1

        # Likewise, an old alias GET finishes after the new alias was saved.
        hold['fan']=True;update(page);wait_callback(page,lambda:bool(held_fan))
        page.locator('#fan-alias').select_option('Loles')
        page.get_by_role('button',name='Guardar apodo',exact=True).click()
        expect(page.locator('#fan-alias-status')).to_contain_text('Apodo guardado')
        page.locator('#outside').click()
        assert page.locator('#fan-alias').get_attribute('data-user-draft') is None
        before=len(fan_reads);page.evaluate('window.controlAssignments=[]')
        route,payload=held_fan.pop();route.fulfill(json=payload)
        wait_callback(page,lambda:len(fan_reads)>before)
        page.wait_for_timeout(80)
        expect(page.locator('#fan-alias')).to_have_value('Loles')
        assert ['fan-alias','Lola'] not in page.evaluate('window.controlAssignments')

        # Unsaved values remain drafts after blur even when the server changes.
        page.locator('#maintenance-scope').select_option('payments')
        page.locator('#maintenance-message').fill('Mi aviso sin guardar')
        page.locator('#fan-alias').select_option('Lolo');page.locator('#outside').click()
        state.update(maintenance={'scope':'off','message':'Cambio remoto'},alias='Lola')
        before=len(fan_reads);update(page);wait_callback(page,lambda:len(fan_reads)>before)
        page.wait_for_timeout(80)
        expect(page.locator('#maintenance-scope')).to_have_value('payments')
        expect(page.locator('#maintenance-message')).to_have_value('Mi aviso sin guardar')
        expect(page.locator('#fan-alias')).to_have_value('Lolo')
        assert posts==[('maintenance',{'scope':'live','message':'Nuevo aviso confirmado'}),('alias',{'alias':'Loles'})],posts
        assert not errors,errors
        browser.close()
        print('Operations refresh: confirmed saves, queued reads and blurred drafts preserved')


if __name__=='__main__':run()
