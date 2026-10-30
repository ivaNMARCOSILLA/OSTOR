"""Read-only navigation health: source contracts and optional public production probes."""
import argparse,json,re,ssl,os,sys
from datetime import datetime,timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit,unquote
from urllib.request import Request,build_opener,HTTPSHandler,HTTPRedirectHandler
from urllib.error import HTTPError,URLError

ROOT=Path(__file__).resolve().parents[1]
PAGES={'/':'index.html','/account':'assets/account.html','/live':'assets/streamers.html','/streamers':'assets/streamers.html'}
PAGES.update({'/'+p.relative_to(ROOT).as_posix():p.relative_to(ROOT).as_posix() for p in (ROOT/'legal').glob('*.html')})
class Document(HTMLParser):
 def __init__(self,source):
  super().__init__();self.ids=set();self.duplicates=[];self.links=[];self.assets=[];self.feed(source)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if a.get('id'):
   if a['id'] in self.ids:self.duplicates.append(a['id'])
   self.ids.add(a['id'])
  if tag=='a' and a.get('href'):self.links.append(a['href'])
  if tag=='script' and a.get('src'):self.assets.append(a['src'])
  if tag=='link' and a.get('rel') in {'stylesheet','manifest'} and a.get('href'):self.assets.append(a['href'])

def inspect_source(root=ROOT,pages=PAGES):
 docs={route:Document((root/path).read_text()) for route,path in pages.items()};errors=[];links=0
 for route,doc in docs.items():
  errors.extend(f'{route}: ID duplicado {ident}' for ident in doc.duplicates)
  for href in doc.links+doc.assets:
   target=urlsplit(urljoin('https://electronicama.com'+route,href))
   if target.netloc not in {'electronicama.com','www.electronicama.com'}:continue
   path=unquote(target.path);links+=1
   if path in docs:
    if target.fragment and unquote(target.fragment) not in docs[path].ids:errors.append(f'{route}: destino inexistente {path}#{target.fragment}')
   elif not (root/path.lstrip('/')).is_file():errors.append(f'{route}: ruta inexistente {path}')
 for relative in ['assets/account.js','assets/streamers.js','assets/operations.js','assets/navigation.js']:
  for asset in re.findall(r"['\"](/assets/[^'\"?]+)(?:\?[^'\"]*)?['\"]",(root/relative).read_text()):
   if not (root/asset.lstrip('/')).is_file():errors.append(f'{relative}: recurso inexistente {asset}')
 return {'pages':len(docs),'links':links,'errors':errors}

def inspect_browser_security(markup,headers):
 errors=[];policy=headers.get('Content-Security-Policy','')
 if "script-src 'self'" not in policy or "object-src 'none'" not in policy:errors.append('Falta la protección esperada de scripts u objetos del navegador.')
 if "'unsafe-inline'" in policy or "'unsafe-eval'" in policy:errors.append('La política permite código arbitrario en línea o eval.')
 if re.search(r'<link\b[^>]*https://fonts\.(?:googleapis|gstatic)\.com',markup,re.I) or '/_vercel/insights/script.js' in markup:errors.append('Hay una carga automática de fuentes o métricas externas que revisar.')
 return errors

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None

def production(base):
 origin=urlsplit(base)
 if origin.scheme!='https' and not (origin.scheme=='http' and origin.hostname in {'localhost','127.0.0.1'}):raise ValueError('Se requiere HTTPS o un servidor local de pruebas.')
 if origin.username or origin.password or origin.query or origin.fragment:raise ValueError('Usa solo el origen público, sin credenciales ni parámetros.')
 ca=os.getenv('REQUESTS_CA_BUNDLE') or os.getenv('SSL_CERT_FILE');context=ssl.create_default_context(cafile=ca if ca and Path(ca).is_file() else None)
 opener=build_opener(NoRedirect(),HTTPSHandler(context=context));cache={};errors=[]
 def get(path):
  if path in cache:return cache[path]
  current=base.rstrip('/')+path
  for _ in range(4):
   if urlsplit(current).netloc!=origin.netloc:raise ValueError('Redirección fuera del sitio supervisado.')
   try:
    with opener.open(Request(current,headers={'User-Agent':'OlNavigationHealth/1.0','Accept':'text/html,application/json'}),timeout=15) as r:result=(r.status,r.read(4*1024*1024),r.headers)
   except HTTPError as e:result=(e.code,e.read(256*1024),e.headers)
   if result[0] in {301,302,303,307,308}:current=urljoin(current,result[2].get('Location',''));continue
   cache[path]=result;return result
  raise ValueError('Demasiadas redirecciones.')
 status,raw,_=get('/api/status');state=json.loads(raw) if status==200 else {};scope=state.get('maintenance',{}).get('scope','off')
 health,hraw,_=get('/health')
 if health!=200:errors.append('/health: no responde correctamente')
 else:
  if json.loads(hraw).get('status')!='ok':errors.append('/health: estado no saludable')
 docs={};skipped=[]
 for route in PAGES:
  try:
   code,raw,headers=get(route)
   if code==503 and (scope=='all' or scope=='live' and route in {'/live','/streamers'}):skipped.append(route);continue
   if code!=200:errors.append(f'{route}: HTTP {code}');continue
   markup=raw.decode('utf-8');errors.extend(route+': '+error for error in inspect_browser_security(markup,headers));docs[route]=Document(markup)
  except (URLError,ValueError,TimeoutError) as e:errors.append(f'{route}: {type(e).__name__}')
 assets=set()
 for route,doc in docs.items():
  for href in doc.links:
   dest=urlsplit(urljoin(base+route,href))
   if dest.netloc!=origin.netloc:continue
   if dest.path in docs and dest.fragment and unquote(dest.fragment) not in docs[dest.path].ids:errors.append(f'{route}: destino inexistente {dest.path}#{dest.fragment}')
  assets.update(urlsplit(urljoin(base+route,asset)).path for asset in doc.assets if urlsplit(urljoin(base+route,asset)).netloc==origin.netloc)
 for path in sorted(assets):
  try:
   code,raw,_=get(path)
   if code!=200 or not raw:errors.append(f'{path}: recurso no disponible (HTTP {code})')
  except (URLError,ValueError,TimeoutError) as e:errors.append(f'{path}: {type(e).__name__}')
 account=docs.get('/account')
 if account:
  for ident in ['register-form','registration-submit','registration-feedback','registration-human-answer','login-form']:
   if ident not in account.ids:errors.append(f'/account: falta {ident}')
 return {'pages':len(docs),'assets':len(assets),'maintenance_skips':skipped,'errors':errors}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base-url');parser.add_argument('--output',type=Path,default=Path('navigation-health.json'));args=parser.parse_args()
 report={'at':datetime.now(timezone.utc).isoformat(),'source':inspect_source()}
 if args.base_url:
  try:report['production']=production(args.base_url)
  except (URLError,ValueError,TimeoutError,OSError) as e:report['production']={'errors':['No se pudo completar la comprobación: '+type(e).__name__]}
 report['ok']=not any(section.get('errors') for section in report.values() if isinstance(section,dict))
 args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
