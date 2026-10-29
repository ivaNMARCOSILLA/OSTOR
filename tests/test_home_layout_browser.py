"""Music-first home keeps the search beside real catalogue results."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox']);page=browser.new_page(viewport={'width':390,'height':900});errors=[];queries=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  tracks=[{'id':'archive_'+str(i),'source':'ARCHIVE','title':'Música '+str(i)+' · Una cançó amb un títol molt llarg que cal poder llegir completament','channel':'Artista'} for i in range(4)]
  def search(route):queries.append(route.request.url);route.fulfill(json=tracks)
  page.route('**/api/search?*',search);page.goto(BASE_URL+'/');page.locator('#consent-decline').click();page.locator('.track-card').first.wait_for()
  assert page.locator('#library #search-form').count()==1
  assert page.locator('#hero #search-form').count()==0
  assert page.locator('#momentos #quick-style-picker').count()==1
  assert page.evaluate("document.querySelector('#library').compareDocumentPosition(document.querySelector('#momentos'))&Node.DOCUMENT_POSITION_FOLLOWING")
  assert page.evaluate("document.querySelector('#mi-espacio').compareDocumentPosition(document.querySelector('#ol-collection'))&Node.DOCUMENT_POSITION_FOLLOWING")
  assert page.evaluate("document.querySelector('#ol-collection').compareDocumentPosition(document.querySelector('#ol-live-premiere'))&Node.DOCUMENT_POSITION_FOLLOWING")

  for width in [320,390,768,1440]:
   page.set_viewport_size({'width':width,'height':900});page.evaluate('scrollTo(0,0)')
   assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
   for title in page.locator('.track-title').all():
    assert title.evaluate('(el)=>el.scrollWidth<=el.clientWidth+1 && getComputedStyle(el).whiteSpace!=="nowrap"'),(width,'clipped track title')
   metrics=page.evaluate("""()=>{const box=id=>document.getElementById(id).getBoundingClientRect();return {search:box('search-form').top,gap:box('track-grid').top-box('search-form').bottom,hero:box('hero').height,music:box('track-grid').top,styles:box('momentos').top,ad:box('ol-live-premiere').top,libraryEnd:box('library').bottom}}""")
   assert metrics['search']<450,(width,metrics)
   assert 0<=metrics['gap']<280,(width,metrics)
   assert metrics['hero']<190,(width,metrics)
   assert metrics['styles']>=metrics['libraryEnd'],(width,metrics)
   assert not page.locator('#ol-live-premiere').is_visible()
   assert page.locator('#ol-live-premiere').get_attribute('data-announcement-archived')=='true'
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
