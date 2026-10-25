"""Speech captions report their real state, submit final text, and stop on mute."""
from playwright.sync_api import sync_playwright
from browser_support import BASE_URL

def run():
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=browser.new_page();sent=[]
  fields=''.join('<div id="'+name+'"></div>' for name in ['live-comments','comment-status','moderation-warning','transcription-status'])
  html=fields+'''<form id="comment-form"><input id="comment-text"><button>Enviar</button></form><button id="report-stream">Denunciar</button><form id="report-form" class="hidden"><select id="report-reason"><option>Acoso</option></select><textarea id="report-details"></textarea><button>Enviar denuncia</button></form><script>window.MaggySession={fetch:window.fetch.bind(window),active:true};window.SpeechRecognition=class{constructor(){window.speech=this;}start(){this.onstart?.();}abort(){this.aborted=true;}};</script>'''
  page.route('**/community-harness',lambda route:route.fulfill(content_type='text/html',body=html))
  def api(route):
   if route.request.method=='GET':route.fulfill(json={'comments':[{'id':'1','username':'viewer','body':'<img src=x onerror=alert(1)>'}]})
   else:
    sent.append(route.request.post_data_json)
    route.fulfill(json={'accepted':False,'blocked':True,'warning':'Aviso: posible suspensión tras revisión.'})
  page.route('**/api/streamers/test/comments',api)
  page.goto(BASE_URL+'/community-harness')
  page.evaluate("async()=>{const {StreamCommunity}=await import('/assets/community.js');window.community=new StreamCommunity();community.start({id:'test'},true);}")
  page.wait_for_function("document.querySelector('#live-comments').children.length===1")
  assert page.locator('#live-comments img').count()==0
  assert 'activa' in page.locator('#transcription-status').inner_text()
  page.evaluate("()=>{const result=[{transcript:'te voy a matar'}];result.isFinal=true;speech.onresult({resultIndex:0,results:[result]});}")
  page.wait_for_function("document.querySelector('#moderation-warning').textContent.includes('suspensión')")
  assert sent==[{'kind':'transcript','text':'te voy a matar'}]
  page.evaluate('community.syncMicrophone(false)');assert page.evaluate('speech.aborted')
  assert 'silenciado' in page.locator('#transcription-status').inner_text()
  page.evaluate('community.stop();delete window.SpeechRecognition;delete window.webkitSpeechRecognition;community.start({id:"test"},true)')
  assert 'no disponible' in page.locator('#transcription-status').inner_text()
  page.evaluate('community.stop()');browser.close()
 print('OK: final voice captions submitted privately, warnings, mic mute cleanup, unsupported state, comments escaped')

if __name__=='__main__':run()
