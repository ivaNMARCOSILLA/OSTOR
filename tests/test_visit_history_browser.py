"""Daily anonymous history preserves unknown dates and its real shared total."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from playwright.sync_api import expect, sync_playwright
from browser_support import BASE_URL


TOTAL='#public-visit-count .public-visit-total'


def dates(page):
    return page.locator('#public-visit-days time').evaluate_all('els=>els.map(el=>el.dateTime)')


def labels(page):
    return page.locator('#public-visit-days td>span:first-child').all_text_contents()


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':1000})
        page=context.new_page();errors=[];record_requests=[]
        page.clock.install()
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:record_requests.append(request.url) if request.method=='POST' and request.url.endswith('/api/visits') else None)
        page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
        page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
        expect(page.locator(TOTAL)).to_have_text('0')
        initial=context.request.get(BASE_URL+'/api/visits/public').json()
        assert not record_requests,'opening or inspecting public history must not record a declined visitor'
        assert initial['cumulative']['sessions']==0
        history=initial['history'];first=history['days'][0]['day'];today=history['days'][-1]['day']
        assert len(history['days'])==15
        assert datetime.fromisoformat(today)-datetime.fromisoformat(first)==timedelta(days=14)
        assert all(day['sessions'] is None and not day['complete'] for day in history['days'])
        assert history['since']==initial['cumulative']['since']
        page.locator('#public-visit-history>summary').click()
        expect(page.locator('#public-visit-days tr')).to_have_count(15)
        assert dates(page)==[day['day'] for day in history['days']]
        assert labels(page)==['Sin datos disponibles']*15,'unrecoverable historical visits must not be presented as measured zeroes'
        expect(page.locator('#public-visit-range')).to_have_text('1 / 1')
        expect(page.locator('#public-visit-older')).to_be_disabled()
        expect(page.locator('#public-visit-newer')).to_be_disabled()
        expect(page.locator('#public-visit-unassigned')).to_be_hidden()

        # One real consented visit updates today's partial count. Withdrawal
        # deletes personal details while retaining that anonymous daily sum.
        page.locator('#privacy-button').click()
        with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/visits')):
            page.locator('#consent-accept').click()
        expect(page.locator(TOTAL)).to_have_text('1')
        expect(page.locator('#public-visit-days tr').last.locator('td>span').first).to_have_text('Al menos 1')
        page.locator('#privacy-button').click()
        with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/api/visits/consent')):
            page.locator('#consent-decline').click()
        after=context.request.get(BASE_URL+'/api/visits/public').json()
        assert after['summary']['sessions']==0 and after['visits']==[]
        assert after['cumulative']['sessions']==1
        assert after['history']['days'][-1]=={'day':today,'sessions':1,'complete':False}
        assert after['history']['since']==history['since']
        expect(page.locator(TOTAL)).to_have_text('1')
        expect(page.locator('#public-visit-days tr').last.locator('td>span').first).to_have_text('Al menos 1')

        for width in [320,390,1440]:
            page.set_viewport_size({'width':width,'height':1000})
            page.locator('#public-visit-history').scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),width
            assert page.locator('.public-visit-day-scroll').evaluate('el=>el.scrollWidth<=el.clientWidth+1'),width
            for button in page.locator('#public-visit-older,#public-visit-newer').all():
                assert button.bounding_box()['height']>=44,width
            if width==390:page.locator('#public-visit-registry').screenshot(path='/tmp/electronicama-daily-history-mobile.png')

        # Isolated pagination fixture: retain the actual total of one visit,
        # extend only the date range, and mark unknown older dates honestly.
        # The real API and its fourteen-day origin were checked above.
        start=datetime.fromisoformat(today).date()-timedelta(days=29)
        origin=datetime.combine(start,datetime.min.time(),tzinfo=ZoneInfo('Europe/Madrid')).astimezone(timezone.utc).isoformat()
        requested=[]
        def paginated(route):
            selected=int(parse_qs(urlsplit(route.request.url).query).get('history_page',['1'])[0])
            requested.append(selected);payload=deepcopy(after)
            payload['cumulative']['since']=origin
            payload['history'].update(since=origin,page=selected,pages=2,page_size=15,total_days=30,unassigned=0)
            if selected==2:
                payload['history']['days']=[{'day':(start+timedelta(days=i)).isoformat(),'sessions':None,'complete':False} for i in range(15)]
            route.fulfill(json=payload,headers={'Cache-Control':'no-store'})
        page.route('**/api/visits/public*',paginated)
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        expect(page.locator('#public-visit-range')).to_have_text('1 / 2')
        expect(page.locator('#public-visit-older')).to_be_enabled()
        page.locator('#public-visit-older').click()
        expect(page.locator('#public-visit-range')).to_have_text('2 / 2')
        assert 2 in requested
        assert dates(page)==[(start+timedelta(days=i)).isoformat() for i in range(15)]
        assert labels(page)==['Sin datos disponibles']*15
        expect(page.locator(TOTAL)).to_have_text('1')
        expect(page.locator('#public-visit-older')).to_be_disabled()
        expect(page.locator('#public-visit-newer')).to_be_enabled()
        page.locator('#public-visit-newer').click()
        expect(page.locator('#public-visit-range')).to_have_text('1 / 2')
        assert requested[-1]==1
        assert dates(page)==[day['day'] for day in after['history']['days']]
        expect(page.locator('#public-visit-days tr').last.locator('td>span').first).to_have_text('Al menos 1')
        expect(page.locator(TOTAL)).to_have_text('1')
        expect(page.locator('#public-visit-unassigned')).to_be_hidden()
        assert not errors,errors
        browser.close()
    print('OK: real fourteen-day origin, honest unknown and partial dates, retained daily totals after withdrawal, historical pagination and three widths')


if __name__=='__main__':run()
