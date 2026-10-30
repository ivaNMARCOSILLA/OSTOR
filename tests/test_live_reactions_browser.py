"""Two real browser clients exercise reaction races and session-private chat DOM."""
from copy import deepcopy
from urllib.parse import urlparse,parse_qs
from playwright.sync_api import sync_playwright,expect
from browser_support import BASE_URL

HTML='''<!doctype html><html><body><div id="live-comments"></div><p id="comment-status"></p><p id="moderation-warning"></p><p id="transcription-status"></p><form id="comment-form"><input id="comment-text"><button>Enviar</button></form><button id="report-stream">Denunciar</button><form id="report-form" class="hidden"><select id="report-reason"><option>Acoso</option></select><textarea id="report-details"></textarea><button>Enviar denuncia</button></form><script>window.MaggySession={fetch:window.fetch.bind(window),active:true};</script></body></html>'''

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  pages=[browser.new_page(),browser.new_page()];errors=[]
  state={'session':'emission-a','ids':['first'],'likes':set(),'private_visible':True,'like_calls':0}
  hold_read=[];hold_like=[];queries=[]
  def feed(client,path):
   query=parse_qs(urlparse(path).query);queries.append(query)
   ids=state['ids'] if client==0 or state['private_visible'] else []
   comments=[{'id':ident,'username':'Creador','body':('Mensaje privado' if ident=='private' else 'Mensaje '+ident),'kind':'comment','likes':len(state['likes']),'liked':client in state['likes']} for ident in ids] if not query.get('after') or query.get('session_start',[''])[0]!=state['session'] else []
   return {'comments':comments,'reactions':[{'id':ident,'likes':len(state['likes']),'liked':client in state['likes']} for ident in ids],'cursor':'cursor-'+state['session'],'session_start':state['session'],'can_post':True}
  def route_for(client):
   def route(request):
    if request.request.method=='GET':
     data=deepcopy(feed(client,request.request.url))
     if client==0 and hold_read and hold_read[0] is True:hold_read[0]=(request,data);return
     request.fulfill(json=data);return
    state['like_calls']+=1
    if hold_like and hold_like[0] is True:hold_like[0]=request;return
    if request.request.post_data_json['liked']:state['likes'].add(client)
    else:state['likes'].discard(client)
    request.fulfill(json={'liked':client in state['likes'],'likes':len(state['likes'])})
   return route
  for i,page in enumerate(pages):
   page.on('pageerror',lambda error:errors.append(str(error)))
   page.route('**/community-reactions-harness',lambda route:route.fulfill(content_type='text/html',body=HTML))
   page.route('**/api/streamers/*/comments**',route_for(i))
   page.route('**/api/rewards?*',lambda route:route.fulfill(json={'stickers':[],'page':1,'pages':1,'filtered_total':0}))
   page.goto(BASE_URL+'/community-reactions-harness')
   page.evaluate("async()=>{const {StreamCommunity}=await import('/assets/community.js');window.community=new StreamCommunity();community.start({id:'channel-a'},false);}")
   page.locator('.comment-like-button').wait_for()
  first,second=pages
  first.locator('.comment-like-button').click();expect(first.locator('.comment-like-button')).to_have_attribute('aria-pressed','true')
  second.evaluate('community.loadComments()');expect(second.locator('.comment-like-button')).to_have_text('♡ 1')
  second.locator('.comment-like-button').click();expect(second.locator('.comment-like-button')).to_have_text('♡ 2')
  first.evaluate('community.loadComments()');expect(first.locator('.comment-like-button')).to_have_text('♡ 2')
  first.locator('.comment-like-button').click();expect(first.locator('.comment-like-button')).to_have_attribute('aria-pressed','false');expect(first.locator('.comment-like-button')).to_have_text('♡ 1')
  # A delayed poll cannot roll a completed like back to its earlier state.
  first.evaluate('clearTimeout(community.poll)');hold_read.append(True)
  first.evaluate('void community.loadComments()');first.wait_for_timeout(30);assert isinstance(hold_read[0],tuple)
  first.locator('.comment-like-button').click();expect(first.locator('.comment-like-button')).to_have_text('♡ 2')
  held,data=hold_read.pop();held.fulfill(json=data);first.wait_for_timeout(30)
  expect(first.locator('.comment-like-button')).to_have_attribute('aria-pressed','true');expect(first.locator('.comment-like-button')).to_have_text('♡ 2')
  # A live session change clears both old rows and an open report target.
  first.locator('.comment-report-button').click();assert first.evaluate('community.reportTarget')=='first'
  state['session']='emission-b';state['ids']=['private']
  first.evaluate('community.loadComments()');assert 'Mensaje privado' in first.locator('#live-comments').inner_text();assert 'Mensaje first' not in first.locator('#live-comments').inner_text();assert first.evaluate('community.reportTarget') is None
  second.evaluate('community.loadComments()');assert 'Mensaje privado' in second.locator('#live-comments').inner_text()
  state['private_visible']=False;second.evaluate('community.loadComments()');expect(second.locator('#live-comments p')).to_have_count(0)
  assert any(q.get('session_start')==['emission-a'] for q in queries)
  # A response to the previous channel must not write a warning into the new one.
  first.evaluate('clearTimeout(community.poll)');hold_like.append(True)
  first.locator('.comment-like-button').click();first.wait_for_timeout(50);assert hold_like and hold_like[0] is not True
  first.evaluate("community.start({id:'channel-b'},false)")
  hold_like.pop().fulfill(status=409,json={'error':'Error viejo que no debe mostrarse'})
  first.wait_for_timeout(50);assert 'Error viejo' not in first.locator('#comment-status').inner_text()
  for page in pages:page.evaluate('community.stop()')
  assert not errors,errors;browser.close()
 print('OK: two browser clients, real reaction counters, toggle removal, stale poll/write races, new-session reset and private message removal')
if __name__=='__main__':run()
