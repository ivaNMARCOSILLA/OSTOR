"""Background counters and rewards update in place without replacing stable art."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import time

from playwright.sync_api import expect, sync_playwright
from browser_support import BASE_URL, login_context


def wait_callback(page,predicate):
    deadline=time.monotonic()+5
    while not predicate():
        assert time.monotonic()<deadline,'Expected a background refresh'
        page.wait_for_timeout(20)


def run():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        login_context(context)
        rewards=context.request.get(BASE_URL+'/api/rewards').json()
        public=context.request.get(BASE_URL+'/api/visits/public').json()
        today=public['history']['days'][-1]['day']
        public['cumulative']['sessions']=5
        public['history']['days'][-1].update(sessions=5,complete=False)
        public['visits']=[{'at':today+'T12:00:00+00:00','page':'/','device':'mobile'}]
        state={'rewards':deepcopy(rewards),'public':deepcopy(public)}
        calls={'read':0,'beat':0,'public':0}
        page=context.new_page();errors=[];navigations=[]
        page.clock.install();page.clock.pause_at(datetime.now(timezone.utc)+timedelta(seconds=1))
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('framenavigated',lambda frame:navigations.append(frame.url) if frame==page.main_frame else None)
        page.route('**/api/search?*',lambda route:route.fulfill(json=[]))
        page.route('**/api/sync',lambda route:route.fulfill(json={'public':'steady','account':'steady'}))
        def reward_read(route):
            calls['read']+=1;route.fulfill(json=deepcopy(state['rewards']))
        def reward_beat(route):
            calls['beat']+=1;route.fulfill(json=deepcopy(state['rewards']))
        def public_read(route):
            calls['public']+=1;route.fulfill(json=deepcopy(state['public']))
        page.route('**/api/rewards?*',reward_read)
        page.route('**/api/rewards/heartbeat?*',reward_beat)
        page.route('**/api/visits/public*',public_read)
        page.goto(BASE_URL+'/#ol-collection');page.locator('#consent-decline').click()
        expect(page.locator('#reward-album .collection-sticker')).to_have_count(len(rewards['stickers']))
        expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('5')
        wait_callback(page,lambda:calls['beat']>=1)
        page.locator('#public-visit-history>summary').click()
        page.locator('#public-visit-recent>summary').click()
        expect(page.locator('#public-visit-list li')).to_have_count(1)
        expect(page.locator('#public-visit-days tr')).to_have_count(len(public['history']['days']))
        # Finish the initial hash navigation and details expansion before taking
        # the scroll baseline. Focusing a control must not start a second smooth
        # scroll that would continue when the test clock advances a minute.
        page.evaluate('() => document.fonts.ready.then(() => true)')
        page.locator('#reward-album .sticker-sound-button').first.evaluate('''button=>{
            button.focus({preventScroll:true});
            button.scrollIntoView({behavior:'instant',block:'center'});
        }''')
        previous_scroll=page.evaluate('scrollY');stable_scroll=0
        for _ in range(12):
            page.clock.run_for(100)
            current_scroll=page.evaluate('scrollY')
            stable_scroll=stable_scroll+1 if abs(current_scroll-previous_scroll)<1 else 0
            previous_scroll=current_scroll
            if stable_scroll>=3:break
        assert stable_scroll>=3,'the initial navigation must settle before background-refresh checks'
        page.evaluate('''()=>{
          window.quietRefs={total:document.querySelector('.public-visit-total'),
            day:document.querySelector('#public-visit-days tr:last-child'),
            dayLabel:document.querySelector('#public-visit-days tr:last-child td>span'),
            recent:document.querySelector('#public-visit-list li'),
            card:document.querySelector('#reward-album article'),
            art:document.querySelector('#reward-album img'),
            sound:document.querySelector('#reward-album button'),
            flower:document.querySelector('.botanical-flower'),scroll:scrollY};
          window.quietCollectionEvents=0;window.quietRemovedArt=0;
          window.addEventListener('ol:collection',()=>window.quietCollectionEvents++);
          new MutationObserver(records=>{for(const record of records)for(const node of record.removedNodes){if(node.nodeType===1){if(node.matches?.('#reward-album img,.collection-sticker img'))window.quietRemovedArt++;window.quietRemovedArt+=node.querySelectorAll?.('.collection-sticker img')?.length||0;}}}).observe(document.querySelector('#ol-collection'),{subtree:true,childList:true});
        }''')
        before=dict(calls);page.clock.fast_forward(61100)
        wait_callback(page,lambda:calls['read']>before['read'] and calls['beat']>before['beat'] and calls['public']>before['public'])
        page.wait_for_timeout(50)
        stable=page.evaluate('''()=>{
          const r=window.quietRefs;return {
            total:r.total===document.querySelector('.public-visit-total'),
            day:r.day===document.querySelector('#public-visit-days tr:last-child'),
            dayLabel:r.dayLabel===document.querySelector('#public-visit-days tr:last-child td>span'),
            recent:r.recent===document.querySelector('#public-visit-list li'),
            card:r.card===document.querySelector('#reward-album article'),
            art:r.art===document.querySelector('#reward-album img'),
            focus:r.sound===document.activeElement,
            flower:r.flower===document.querySelector('.botanical-flower'),
            scroll:Math.abs(scrollY-r.scroll)<2,
            oldScroll:r.scroll,newScroll:scrollY,
            active:document.activeElement?.outerHTML?.slice(0,220),
            oldCardConnected:r.card.isConnected,oldArtConnected:r.art.isConnected
          };
        }''')
        assert all(stable[key] for key in ['total','day','dayLabel','recent','card','art','focus','flower','scroll']),('unchanged background snapshots must keep nodes, focus and scroll',stable,calls)
        assert page.evaluate('window.quietRemovedArt')==0
        assert page.evaluate('window.quietCollectionEvents')==0

        # Actual shared changes still arrive immediately; stable rows and images
        # remain attached, including a recent entry shifted by a new arrival.
        state['public']['cumulative']['sessions']=6
        state['public']['history']['days'][-1]['sessions']=6
        state['public']['visits'].insert(0,{'at':today+'T12:01:00+00:00','page':'/live','device':'desktop'})
        state['rewards']['points']=10
        unlocked=next(item for item in state['rewards']['stickers'] if not item['unlocked'])
        unlocked['unlocked']=True
        state['rewards']['unlocked']+=1
        state['rewards']['owned_preview'].append(deepcopy(unlocked))
        page.clock.fast_forward(31100)
        expect(page.locator('#public-visit-count .public-visit-total')).to_have_text('6')
        expect(page.locator('#public-visit-days tr').last.locator('td>span').first).to_have_text('Al menos 6')
        expect(page.locator('#public-visit-list li')).to_have_count(2)
        expect(page.locator('#reward-points')).to_have_text('10')
        changed=page.evaluate('''()=>{const r=window.quietRefs;return {total:r.total===document.querySelector('.public-visit-total'),day:r.day===document.querySelector('#public-visit-days tr:last-child'),recent:r.recent===document.querySelector('#public-visit-list li:nth-child(2)'),card:r.card===document.querySelector('#reward-album article'),art:r.art===document.querySelector('#reward-album img'),focus:r.sound===document.activeElement};}''')
        assert all(changed.values()),('real updates must preserve the existing rows and artwork',changed,calls)
        assert page.evaluate('window.quietRemovedArt')==0
        assert page.evaluate('window.quietCollectionEvents')==1
        expect(page.locator('#reward-album .collection-sticker.unlocked')).to_have_count(sum(item['unlocked'] for item in state['rewards']['stickers']))
        assert len(navigations)==1,'quiet refresh must never reload the page'
        assert not errors,errors
        browser.close()
    print('OK: unchanged refresh keeps counter/history/recent/reward art, focus and scroll; real updates arrive in place without a page reload')


if __name__=='__main__':run()
