"""Necessary display-language preference; no address lookup, storage or tracking."""
import os,re
from flask import Blueprint,jsonify,request

bp=Blueprint('locale_preferences',__name__)
SUPPORTED=('es','ca','en','fr','pt','de','it')
COOKIE='electronicama_language'
COUNTRIES={
 'ES':('es','ca'),'AD':('ca',),'US':('en',),'GB':('en',),'IE':('en',),'AU':('en',),'NZ':('en',),
 'CA':('en','fr'),'FR':('fr',),'BE':('fr','de'),'CH':('de','fr','it'),'LU':('fr','de'),
 'PT':('pt',),'BR':('pt',),'AO':('pt',),'MZ':('pt',),'DE':('de',),'AT':('de',),'LI':('de',),
 'IT':('it',),'SM':('it',),'VA':('it',),'MX':('es',),'AR':('es',),'CO':('es',),'CL':('es',),
 'PE':('es',),'EC':('es',),'VE':('es',),'UY':('es',),'PY':('es',),'BO':('es',),'CR':('es',),
 'PA':('es',),'GT':('es',),'HN':('es',),'SV':('es',),'NI':('es',),'DO':('es',),'CU':('es',),
 'PR':('es','en'),'GQ':('es','fr','pt'),'SN':('fr',),'CI':('fr',),'CM':('fr','en')}

def browser_languages():
 return [tag.lower().split('-')[0] for tag,q in request.accept_languages if q>0 and re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',tag)]

@bp.get('/api/locale')
def preference():
 manual=request.cookies.get(COOKIE)
 if manual in SUPPORTED:language=manual;source='saved'
 else:
  country=request.headers.get('X-Vercel-IP-Country','') if os.getenv('VERCEL')=='1' else ''
  country=country.upper() if re.fullmatch('[A-Za-z]{2}',country) else ''
  regional=COUNTRIES.get(country);preferred=browser_languages()
  if regional:
   language=next((tag for tag in preferred if tag in regional),regional[0]);source='country'
  else:language=next((tag for tag in preferred if tag in SUPPORTED),'es');source='browser' if any(tag in SUPPORTED for tag in preferred) else 'default'
 response=jsonify(language=language,source=source,supported=list(SUPPORTED))
 response.headers['Cache-Control']='private, no-store'
 response.headers['Vary']='Accept-Language, Cookie, X-Vercel-IP-Country'
 return response

def install(app):app.register_blueprint(bp)
