"""Automatically fill to 120 unique tracks, stop on scarcity, keep radio separate."""
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=b.new_page();calls=[];errors=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  def search(route):
   args=parse_qs(urlparse(route.request.url).query);q=args.get('q',[''])[0];source=args.get('source',['ALL'])[0];number=int(args.get('page',['1'])[0]);calls.append((q,source,number))
   if q=='scarce':tracks=[{'id':'archive_one','title':'Only match','source':'ARCHIVE'}] if number==1 else []
   elif q=='empty':tracks=[]
   elif source=='MIX':
    tracks=[{'id':f'commons_{number}_{i}','title':f'Piano {i}','source':'COMMONS'} for i in range(40)]
    tracks += [{'id':f'radio_{i}','title':'Radio','source':'RADIO'} for i in range(12)]
   else:tracks=[{'id':f'{source.lower()}_{number}_{i}','title':f'Piano {i}','source':source} for i in range(30)]
   route.fulfill(json=tracks)
  page.route('**/api/search?*',search)
  page.goto(BASE_URL+'/');page.locator('#consent-decline').click()
  page.wait_for_function("document.querySelector('#result-status').textContent.includes('120 resultados') && !document.querySelector('#search-button').disabled")
  assert page.locator('.track-card').count()==120
  assert max(n for q,s,n in calls)==2
  for query,expected in [('scarce',1),('empty',0)]:
   page.locator('#search-input').fill(query);page.locator('#search-button').click()
   page.wait_for_function("!document.querySelector('#search-button').disabled")
   assert page.locator('.track-card').count()==expected
   assert 'No se han encontrado 120' in page.locator('#result-status').inner_text()
  assert max(n for q,s,n in calls if q=='scarce')==2
  assert max(n for q,s,n in calls if q=='empty')==1
  page.locator('[data-source=MIX]').click()
  page.wait_for_function("document.querySelectorAll('.track-card').length===132")
  assert max(n for q,s,n in calls if s=='MIX')==3
  assert not errors,errors
  b.close()
 print('OK: 120 unique search tracks automatically; no fake/duplicate scarce results; MIX counts 120 recordings separately from radio')

if __name__=='__main__':run()
