"""Independent devices share a real total and recover stalled public updates."""
from datetime import datetime, timedelta, timezone
import time

from playwright.sync_api import Error, expect, sync_playwright
from browser_support import BASE_URL


PUBLIC='**/api/visits/public*'
TOTAL='#public-visit-count .public-visit-total'
MOBILE='Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'
DESKTOP='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'
TABLET='Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Safari/604.1'


def open_device(browser, errors, *, viewport, user_agent, mobile=False, frozen=False):
    context=browser.new_context(viewport=viewport,user_agent=user_agent,is_mobile=mobile,has_touch=mobile)
    page=context.new_page()
    page.clock.install()
    if frozen:
        page.clock.pause_at(datetime.now(timezone.utc)+timedelta(seconds=1))
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
    return context,page


def expect_total(page, value, timeout=5000):
    expect(page.locator(TOTAL)).to_have_text(str(value),timeout=timeout)


def record(context, event='page'):
    csrf=context.request.get(BASE_URL+'/api/account/me').json()['csrf']
    response=context.request.post(BASE_URL+'/api/visits',data={'consent':True,'page':'/','event':event},headers={'X-CSRF-Token':csrf})
    assert response.status==200,response.status
    assert response.json()['recorded']


def wait_callback(page, predicate):
    # Route callbacks are dispatched while Playwright pumps its protocol loop.
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'public request was not intercepted'
        page.wait_for_timeout(20)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        errors=[];devices=[];navigations=[]
        specs=[({'width':393,'height':852},MOBILE,True),({'width':1440,'height':1000},DESKTOP,False),({'width':768,'height':1024},TABLET,True)]
        for number,(viewport,agent,mobile) in enumerate(specs,1):
            context,page=open_device(browser,errors,viewport=viewport,user_agent=agent,mobile=mobile)
            seen=[]
            page.on('framenavigated',lambda frame,seen=seen,page=page:seen.append(frame.url) if frame==page.main_frame else None)
            page.goto(BASE_URL+'/')
            with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/visits')) as entry:
                page.locator('#consent-accept').click()
            assert entry.value.json()['recorded']
            expect_total(page,number)
            devices.append((context,page));navigations.append(seen)

        # All contexts use the same local server/IP; their signed browser
        # cookies stay distinct and every API response returns the same total.
        cookies=[next(cookie['value'] for cookie in context.cookies() if cookie['name']=='electronicama_visits') for context,_ in devices]
        assert len(set(cookies))==3
        origins=set()
        for context,page in devices:
            page.clock.fast_forward(3500)
            expect_total(page,3)
            data=context.request.get(BASE_URL+'/api/visits/public').json()
            assert data['cumulative']['sessions']==3
            origins.add(data['cumulative']['since'])
        assert len(origins)==1
        assert all(len(seen)==1 for seen in navigations),'synchronization must not reload any device'

        # Refreshing a continuing session is not another visitor, regardless of
        # whether that request came from a phone, computer or tablet.
        for context,_ in devices:
            record(context,'heartbeat');record(context)
        assert devices[0][0].request.get(BASE_URL+'/api/visits/public').json()['cumulative']['sessions']==3

        observer,watch=open_device(browser,errors,viewport={'width':390,'height':844},user_agent=MOBILE,mobile=True)
        observed_posts=[]
        watch.on('request',lambda request:observed_posts.append(request.url) if request.method=='POST' and request.url.endswith('/api/visits') else None)
        watch.goto(BASE_URL+'/');watch.locator('#consent-decline').click()
        expect_total(watch,3)
        assert not observed_posts,'a declined device may see the global sum without being tracked'

        _,phone=devices[0]
        phone.locator('#privacy-button').click()
        with phone.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/visits/consent')):
            phone.locator('#consent-decline').click()
        after=observer.request.get(BASE_URL+'/api/visits/public').json()
        assert after['summary']['sessions']==2 and after['cumulative']['sessions']==3
        for _,page in devices:
            page.clock.fast_forward(3500);expect_total(page,3)

        # Hold a real, older server snapshot while a fourth consented device
        # enters. With time frozen, periodic polling cannot hide a dropped
        # forced refresh: the queued follow-up itself must fetch the new sum.
        racing,race=open_device(browser,errors,viewport={'width':393,'height':852},user_agent=MOBILE,mobile=True,frozen=True)
        held=[];race_requests=[]
        def hold_initial(route):
            race_requests.append(route.request.url)
            if len(race_requests)==1:
                response=route.fetch()
                assert response.json()['cumulative']['sessions']==3
                held.append((route,response))
            else:
                route.continue_()
        race.route(PUBLIC,hold_initial)
        race.goto(BASE_URL+'/');wait_callback(race,lambda:bool(held))
        with race.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/visits')) as entry:
            race.locator('#consent-accept').click()
        assert entry.value.json()['recorded']
        held[0][0].fulfill(response=held[0][1])
        expect_total(race,4,timeout=2500)
        wait_callback(race,lambda:len(race_requests)>=2)
        assert len(race_requests)>=2,'a newer entry arriving during a GET must schedule another GET'

        # A hung public request must time out and allow another request. The
        # observer has declined metrics, so these lifecycle checks add no visits.
        stalled_context,stalled=open_device(browser,errors,viewport={'width':1440,'height':1000},user_agent=DESKTOP,frozen=True)
        stalled_requests=[];blocked=[]
        def stall_initial(route):
            stalled_requests.append(route.request.url)
            if len(stalled_requests)==1:blocked.append(route)
            else:route.continue_()
        stalled.route(PUBLIC,stall_initial)
        stalled.goto(BASE_URL+'/');wait_callback(stalled,lambda:bool(blocked))
        stalled.locator('#consent-decline').click()
        stalled.clock.fast_forward(8500)
        stalled.evaluate("window.dispatchEvent(new Event('focus'))")
        expect_total(stalled,4)
        assert len(stalled_requests)>=2,'a timed-out request must not freeze future refreshes'
        try:blocked[0].abort()
        except Error:pass  # AbortController may already have cancelled it.

        # Real entries on other contexts must be reflected on focus, restored
        # connection and BFCache return without waiting for the frozen interval.
        for total,event in [(5,'focus'),(6,'online'),(7,'pageshow')]:
            extra=browser.new_context(user_agent=DESKTOP);record(extra)
            if event=='pageshow':
                stalled.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true}))")
            else:
                stalled.evaluate('(name)=>window.dispatchEvent(new Event(name))',event)
            expect_total(stalled,total,timeout=2500)
        for context,page in devices:
            page.clock.fast_forward(3500);expect_total(page,7)
            assert context.request.get(BASE_URL+'/api/visits/public').json()['cumulative']['sessions']==7
        assert all(len(seen)==1 for seen in navigations),'the original devices must stay on their initial document'

        # A successful write can arrive after a newer GET from another device.
        # Execute the real eighth entry, hold its response, then let a ninth
        # device enter and confirm nine before delivering the older POST.
        posting,post_page=open_device(browser,errors,viewport={'width':393,'height':852},user_agent=MOBILE,mobile=True,frozen=True)
        held_posts=[]
        def hold_first_post(route):
            if held_posts:
                route.continue_();return
            response=route.fetch()
            assert response.json()['recorded']
            assert response.json()['cumulative']['sessions']==8
            held_posts.append((route,response))
        post_page.route('**/api/visits',hold_first_post)
        post_page.goto(BASE_URL+'/');expect_total(post_page,7)
        older_snapshot=posting.request.get(BASE_URL+'/api/visits/public').json()
        assert older_snapshot['cumulative']['sessions']==7
        post_page.locator('#consent-accept').click()
        wait_callback(post_page,lambda:bool(held_posts))
        ninth=browser.new_context(user_agent=DESKTOP);record(ninth)
        post_page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect_total(post_page,9)
        latest=posting.request.get(BASE_URL+'/api/visits/public').json()
        assert latest['cumulative']['sessions']==9
        assert latest['cumulative']['since']==older_snapshot['cumulative']['since']==held_posts[0][1].json()['cumulative']['since']

        # Observe every rendered value: checking only the final nine would miss
        # a brief regression to eight followed by the automatic fresh GET.
        observe_totals="""() => {
            window.counterSnapshots=[];
            new MutationObserver(() => {
                const text=document.querySelector('#public-visit-count .public-visit-total')?.textContent;
                if(text)window.counterSnapshots.push(Number(text.replace(/\\D/g,'')));
            }).observe(document.querySelector('#public-visit-count'),{
                subtree:true,childList:true,characterData:true
            });
        }"""
        post_page.evaluate(observe_totals)
        held_posts[0][0].fulfill(response=held_posts[0][1])
        wait_callback(post_page,lambda:bool(post_page.evaluate('window.counterSnapshots.length')))
        expect_total(post_page,9)
        assert all(value>=9 for value in post_page.evaluate('window.counterSnapshots')),'a delayed confirmed POST must never lower a newer confirmed global total'

        # An older GET with the same origin must also leave the confirmed total
        # alone. This declined observer cannot create a write revision, so only
        # the stale-total guard can reject the real earlier snapshot of seven.
        stalled.evaluate("window.dispatchEvent(new Event('focus'))")
        expect_total(stalled,9)
        stalled.evaluate(observe_totals)
        old_reads=[];old_routes=[]
        def hold_old_snapshot(route):
            old_reads.append(route.request.url)
            if len(old_reads)==1:old_routes.append(route)
            else:route.continue_()
        stalled.route(PUBLIC,hold_old_snapshot)
        stalled.evaluate("window.dispatchEvent(new Event('focus'))")
        wait_callback(stalled,lambda:bool(old_routes))
        stalled.evaluate("window.dispatchEvent(new Event('focus'))")
        old_routes[0].fulfill(json=older_snapshot)
        wait_callback(stalled,lambda:len(old_reads)>=2)
        wait_callback(stalled,lambda:bool(stalled.evaluate('window.counterSnapshots.length')))
        expect_total(stalled,9)
        assert all(value>=9 for value in stalled.evaluate('window.counterSnapshots')),'an older same-origin GET must never lower a confirmed global total'
        assert not errors,errors
        browser.close()
    print('OK: shared phone/computer/tablet total, same-IP cookies, continuing-session deduplication, consent boundaries, queued GET, timeout recovery, lifecycle refresh and out-of-order POST/GET totals')


if __name__=='__main__':run()
