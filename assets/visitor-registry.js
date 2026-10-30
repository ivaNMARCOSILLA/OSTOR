/* Optional first-party visit records. No fingerprint, field contents or full URLs. */
(()=>{
 const KEY='electronicama_visit_registry_consent_v1',OLD_KEY='electronicama_navigation_consent_v1';
 const paths=new Set(['/','/live','/account','/legal/cookies.html','/legal/privacidad.html','/legal/aviso-legal.html']);
 const page=()=>location.pathname==='/streamers'?'/live':location.pathname;
 const privacySignal=()=>navigator.globalPrivacyControl||navigator.doNotTrack==='1';
 const preference=()=>{try{return localStorage.getItem(KEY);}catch{return null;}};
 let csrf='',allowed=preference()==='accepted'&&!privacySignal(),active=null,generation=0,lastAccount,identityReady=false,publicBusy=false,publicLast=0;
 async function token(){const response=await fetch('/api/account/me',{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();csrf=data.csrf;return data;}
 async function request(path,data,retry=true){if(!csrf)await token();const response=await fetch(path,{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});if(response.status===403&&retry){await token();return request(path,data,false);}if(!response.ok)throw Error();return response.json();}
 function record(event='heartbeat'){
  if(!allowed||privacySignal()||!paths.has(page())||document.hidden||active)return Promise.resolve();
  const version=generation;
  active=request('/api/visits',{consent:true,page:page(),event}).then(result=>{if(version===generation&&result.recorded){window.dispatchEvent(new Event('electronicama:visit-recorded'));}}).catch(()=>{}).finally(()=>{active=null;});return active;
 }
 async function choose(value,notifyLegacy=true){
  const version=++generation;allowed=Boolean(value)&&!privacySignal();
  try{localStorage.setItem(KEY,allowed?'accepted':'rejected');if(notifyLegacy)localStorage.setItem(OLD_KEY,allowed?'accepted':'rejected');}catch{}
  document.getElementById('visitor-consent-panel')?.remove();
  if(notifyLegacy)window.dispatchEvent(new CustomEvent('electronicama:navigation-consent',{detail:{allowed,visitRegistryHandled:true}}));
  if(allowed){await record('page');return;}
  // Let any already-submitted write finish before deleting this browser's records.
  const pending=active;if(pending)await pending;if(version!==generation)return;
  try{await request('/api/visits/consent',{allowed:false});}catch{}
  refreshPublic(true);
 }
 function showPreferences(){
  if(document.getElementById('consent-dialog')){document.getElementById('consent-dialog').classList.remove('hidden');return;}
  if(document.getElementById('visitor-consent-panel'))return;
  const panel=document.createElement('aside');panel.id='visitor-consent-panel';panel.className='visitor-consent-panel';panel.setAttribute('aria-label','Preferencias de visitas');
  const title=document.createElement('strong');title.textContent='Tú decides qué compartes';
  const copy=document.createElement('p');copy.textContent='Con tu permiso, guardamos visitas durante 7 días. Las entradas anónimas y el tipo de dispositivo aparecen en la portada. Si entras con cuenta, solo administración puede relacionarlas con tu usuario. Puedes usar la web sin aceptar.';
  const no=document.createElement('button');no.type='button';no.textContent='Solo necesarias';no.addEventListener('click',()=>choose(false));
  const yes=document.createElement('button');yes.type='button';yes.textContent='Permitir visitas opcionales';yes.addEventListener('click',()=>choose(true));
  const privacy=document.createElement('a');privacy.href='/legal/privacidad.html';privacy.textContent='Ver privacidad';panel.append(title,copy,no,yes,privacy);document.body.append(panel);
 }
 async function refreshPublic(force=false){
  const list=document.getElementById('public-visit-list');if(!list||publicBusy||document.hidden||(!force&&Date.now()-publicLast<15000))return;
  publicBusy=true;
  try{const response=await fetch('/api/visits/public',{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();list.replaceChildren();
   const t=text=>window.OlLocale?.t(text)||text;document.getElementById('public-visit-count').textContent=`${data.summary.sessions} ${t('entradas')} · ${data.summary.browsers} ${t('navegadores estimados en 24 horas')}`;
   const labels={desktop:'Ordenador',mobile:'Móvil',tablet:'Tableta',bot:'Automatizado',unknown:'Sin identificar'},pages={'/':'Música','/live':'Ol Livis','/account':'Cuenta','/legal/cookies.html':'Información legal','/legal/privacidad.html':'Información legal','/legal/aviso-legal.html':'Información legal'};
   for(const visit of data.visits){const row=document.createElement('li'),device=document.createElement('strong'),time=document.createElement('time'),where=document.createElement('span');device.textContent=t(labels[visit.device]||visit.device||'Sin identificar');time.dateTime=visit.at;time.textContent=new Intl.DateTimeFormat(document.documentElement.lang||'es',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'}).format(new Date(visit.at));where.textContent=t(pages[visit.page]||visit.page||'Web');row.append(device,where,time);list.append(row);}
   document.getElementById('public-visit-status').textContent=data.visits.length?'Horas de Madrid · datos actualizados.':'Todavía no hay entradas compartidas en las últimas 24 horas.';publicLast=Date.now();
  }catch{document.getElementById('public-visit-status').textContent='No se ha podido actualizar la actividad. Volveremos a intentarlo.';}finally{publicBusy=false;}
 }
 window.addEventListener('electronicama:navigation-consent',event=>{if(!event.detail?.visitRegistryHandled)choose(event.detail?.allowed,false);});
 window.addEventListener('storage',event=>{if(event.key!==KEY)return;allowed=preference()==='accepted'&&!privacySignal();if(allowed)record('page');else choose(false,false);});
 window.addEventListener('ol:account-refreshed',async()=>{if(!allowed)return;try{const account=await token(),id=account.user?.id||null;if(identityReady&&id!==lastAccount)await record('page');lastAccount=id;identityReady=true;}catch{}});
 window.addEventListener('electronicama:visit-recorded',()=>refreshPublic(true));window.addEventListener('ol:language-changed',()=>refreshPublic(true));
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){record();refreshPublic(true);}});
 const settings=document.createElement('button');settings.type='button';settings.className='secondary';settings.textContent='Preferencias de visitas';settings.dataset.visitsPreferences='';settings.addEventListener('click',showPreferences);if(!document.getElementById('privacy-button'))(document.querySelector('footer')||document.body).append(settings);
 if(allowed)token().then(account=>{lastAccount=account.user?.id||null;identityReady=true;record('page');}).catch(()=>{});
 else if(!preference()&&!privacySignal()&&!document.getElementById('consent-dialog'))showPreferences();
 if(privacySignal()&&preference()==='accepted')choose(false,false);
 refreshPublic(true);setInterval(()=>{record();refreshPublic();},60000);setInterval(()=>refreshPublic(),30000);
})();
