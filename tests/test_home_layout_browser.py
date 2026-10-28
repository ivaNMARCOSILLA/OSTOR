"""Music-first home keeps the search beside real catalogue results."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page(viewport={'width':390,'height':900});errors=[];queries=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  tracks=[{'id':'archive_'+str(i),'source':'ARCHIVE','title':'Música '+str(i),'channel':'Artista'} for i in range(4)]
  def search(route):queries.append(route.request.url);route.fulfill(json=tracks)
  page.route('**/api/search?*',search);page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('.track-card').first.wait_for()
  assert page.locator('#library #search-form').count()==1
  assert page.locator('#hero #search-form').count()==0
  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});page.evaluate('scrollTo(0,0)')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   metrics=page.evaluate("""()=>{const box=id=>document.getElementById(id).getBoundingClientRect();return {search:box('search-form').top,gap:box('track-grid').top-box('search-form').bottom,hero:box('hero').height,music:box('track-grid').top,ad:box('ol-live-premiere').top,libraryEnd:box('library').bottom}}""")
   assert metrics['search']<450,(width,metrics)
   assert 0<=metrics['gap']<280,(width,metrics)
   assert metrics['hero']<190,(width,metrics)
   assert metrics['ad']>=metrics['libraryEnd'],(width,metrics)
   if width==390:page.screenshot(path='/tmp/ol-home-compact-mobile.png')
   if width==1440:page.screenshot(path='/tmp/ol-home-compact-desktop.png')
  page.locator('#quick-style-picker summary').click();page.locator('#quick-searches [data-query=techno]').click()
  page.wait_for_function("document.querySelector('#search-input').value==='techno'&&!document.querySelector('#search-button').disabled")
  assert any('q=techno' in query for query in queries)
  page.locator('#search-input').fill('piano');page.locator('#search-form').evaluate('(form)=>form.requestSubmit()')
  page.wait_for_function("document.querySelector('#search-input').value==='piano'&&!document.querySelector('#search-button').disabled")
  assert any('q=piano' in query for query in queries)
  assert page.locator('#founders').count()==1 and page.locator('#intro-skip').count()==1
  assert not errors,errors;browser.close()
 print('OK: search inside catalogue, promotions after music, compact hero, real search submission and 320/390/768/1440 layouts')
if __name__=='__main__':run()
