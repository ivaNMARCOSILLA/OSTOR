/* Optional first-party visit records. No fingerprint, field contents or full URLs. */
(()=>{
 const KEY='electronicama_visit_registry_consent_v1',OLD_KEY='electronicama_navigation_consent_v1';
 const paths=new Set(['/','/live','/account','/legal/cookies.html','/legal/privacidad.html','/legal/aviso-legal.html']);
 const page=()=>location.pathname==='/streamers'?'/live':location.pathname;
 const privacySignal=()=>navigator.globalPrivacyControl||navigator.doNotTrack==='1';
 const preference=()=>{try{return localStorage.getItem(KEY);}catch{return null;}};
 const PUBLIC_REFRESH_MS=3000,REQUEST_TIMEOUT_MS=8000;
 let csrf='',allowed=preference()==='accepted'&&!privacySignal(),active=null,generation=0,lastAccount,identityReady=false;
 let publicBusy=false,publicQueued=false,publicTimer=null,publicController=null,writeRevision=0,historyPage=1,lastPublicTotal=null;
 let historyRows=new Map(),recentRows=new Map();
 const desiredText=new WeakMap();
 const setText=(node,value)=>{if(desiredText.get(node)===value)return;desiredText.set(node,value);if(node.textContent!==value)node.textContent=value;};
 function placeRows(parent,rows){let cursor=parent.firstElementChild;for(const row of rows){if(row===cursor)cursor=cursor.nextElementSibling;else parent.insertBefore(row,cursor);}while(cursor){const next=cursor.nextElementSibling;cursor.remove();cursor=next;}}
 const t=text=>window.OlLocale?.t(text)||text;
 async function fetchJson(path,options={},controller=new AbortController()){
  const deadline=setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
  try{const response=await fetch(path,{...options,signal:controller.signal});const data=await response.json();return {response,data};}
  finally{clearTimeout(deadline);}
 }
 async function token(){const {response,data}=await fetchJson('/api/account/me',{cache:'no-store'});if(!response.ok)throw Error();csrf=data.csrf;return data;}
 async function request(path,data,retry=true){if(!csrf)await token();const result=await fetchJson(path,{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});if(result.response.status===403&&retry){await token();return request(path,data,false);}if(!result.response.ok)throw Error();return result.data;}
 function record(event='heartbeat'){
  if(!allowed||privacySignal()||!paths.has(page())||document.hidden||active)return Promise.resolve();
  const version=generation;
  active=request('/api/visits',{consent:true,page:page(),event}).then(result=>{if(version===generation&&result.recorded){writeRevision++;if(result.cumulative)renderTotal(result.cumulative);window.dispatchEvent(new Event('electronicama:visit-recorded'));}}).catch(()=>{}).finally(()=>{active=null;});return active;
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
  const copy=document.createElement('p');copy.textContent='Con tu permiso, guardamos el detalle de las visitas durante 7 días. Las entradas recientes y el tipo de dispositivo aparecen en la portada. El total acumulado se conserva de forma anónima, sin identificarte. Si entras con cuenta, solo administración puede relacionar el detalle con tu usuario. Puedes usar la web sin aceptar.';
  const dailyNote=document.createElement('span');dailyNote.textContent='El recorrido diario se conserva de forma anónima.';copy.append(' ',dailyNote);
  const no=document.createElement('button');no.type='button';no.textContent='Solo necesarias';no.addEventListener('click',()=>choose(false));
  const yes=document.createElement('button');yes.type='button';yes.textContent='Permitir visitas opcionales';yes.addEventListener('click',()=>choose(true));
  const privacy=document.createElement('a');privacy.href='/legal/privacidad.html';privacy.textContent='Ver privacidad';panel.append(title,copy,no,yes,privacy);document.body.append(panel);
 }
 function renderTotal(cumulative){
  const count=document.getElementById('public-visit-count');if(!count)return;
  const total=cumulative?.sessions,since=new Date(cumulative?.since);
  if(!Number.isSafeInteger(total)||total<0||typeof cumulative?.since!=='string'||Number.isNaN(since.getTime()))throw Error('Invalid total');
  // Responses can arrive out of order across reads and writes. Keep only a
  // server-confirmed maximum for this origin; never invent a local increment.
  const origin=since.toISOString();
  if(lastPublicTotal?.since===origin&&total<lastPublicTotal.sessions)return false;
  lastPublicTotal={sessions:total,since:origin};
  const locale=document.documentElement.lang||'es';let value=count.querySelector('.public-visit-total'),caption=count.querySelector('.public-visit-caption');
  if(!value||!caption){value=document.createElement('strong');caption=document.createElement('span');value.className='public-visit-total';caption.className='public-visit-caption';count.replaceChildren(value,caption);}
  setText(value,new Intl.NumberFormat(locale).format(total));setText(caption,t(total===1?'entrada acumulada':'entradas acumuladas'));
  setText(document.getElementById('public-visit-since'),`${t('Desde el')} ${new Intl.DateTimeFormat(locale,{timeZone:'Europe/Madrid',dateStyle:'long'}).format(since)} · ${t('total compartido entre dispositivos')}`);
  return true;
 }
 function renderHistory(history){
  const body=document.getElementById('public-visit-days');if(!body||!history)return;
  if(!Array.isArray(history.days)||!Number.isSafeInteger(history.page)||!Number.isSafeInteger(history.pages))throw Error('Invalid history');
  const locale=document.documentElement.lang||'es',number=new Intl.NumberFormat(locale),date=new Intl.DateTimeFormat(locale,{timeZone:'Europe/Madrid',day:'numeric',month:'short',year:'numeric'});
  const maximum=Math.max(1,...history.days.map(day=>Number.isSafeInteger(day.sessions)?day.sessions:0));
  for(const day of history.days)if(!/^\d{4}-\d{2}-\d{2}$/.test(day.day)||!(day.sessions===null||Number.isSafeInteger(day.sessions)&&day.sessions>=0))throw Error('Invalid day');
  const nextRows=new Map(),rows=[];
  for(const day of history.days){
   let record=historyRows.get(day.day);
   if(!record){const row=document.createElement('tr'),when=document.createElement('th'),time=document.createElement('time'),value=document.createElement('td'),label=document.createElement('span'),bar=document.createElement('span'),fill=document.createElement('span');when.scope='row';time.dateTime=day.day;when.append(time);bar.className='public-visit-day-bar';bar.setAttribute('aria-hidden','true');bar.append(fill);value.append(label);row.append(when,value);record={row,time,value,label,bar,fill};}
   const {row,time,value,label,bar,fill}=record,partial=day.complete?'':'public-visit-partial';
   if(row.className!==partial)row.className=partial;
   setText(time,date.format(new Date(day.day+'T12:00:00+00:00')));
   setText(label,day.sessions===null?t('Sin datos disponibles'):day.complete?number.format(day.sessions):`${t('Al menos')} ${number.format(day.sessions)}`);
   const title=day.complete?'':t('Desglose anterior incompleto');if(label.title!==title)label.title=title;
   if(day.sessions!==null){const width=(100*day.sessions/maximum)+'%';if(fill.style.width!==width)fill.style.width=width;if(bar.parentNode!==value)value.append(bar);}else if(bar.parentNode)bar.remove();
   nextRows.set(day.day,record);rows.push(row);
  }
  placeRows(body,rows);historyRows=nextRows;historyPage=history.page;
  const older=document.getElementById('public-visit-older'),newer=document.getElementById('public-visit-newer');
  if(older.disabled!==(history.page>=history.pages))older.disabled=history.page>=history.pages;
  if(newer.disabled!==(history.page<=1))newer.disabled=history.page<=1;
  setText(document.getElementById('public-visit-range'),`${history.page} / ${history.pages}`);
  const unassigned=document.getElementById('public-visit-unassigned');if(unassigned.hidden!==!history.unassigned)unassigned.hidden=!history.unassigned;
  setText(unassigned,history.unassigned?`${number.format(history.unassigned)} · ${t('entradas anteriores sin desglose diario')}`:'');
 }
 function renderRecent(list,visits){
  const labels={desktop:'Ordenador',mobile:'Móvil',tablet:'Tableta',bot:'Automatizado',unknown:'Sin identificar'},pages={'/':'Música','/live':'Ol Live','/account':'Cuenta','/legal/cookies.html':'Información legal','/legal/privacidad.html':'Información legal','/legal/aviso-legal.html':'Información legal'};
  const nextRows=new Map(),rows=[],occurrences=new Map(),date=new Intl.DateTimeFormat(document.documentElement.lang||'es',{timeZone:'Europe/Madrid',hour:'2-digit',minute:'2-digit'});
  for(const visit of visits){const base=JSON.stringify([visit.at,visit.page,visit.device]),number=occurrences.get(base)||0,key=base+':'+number;occurrences.set(base,number+1);let record=recentRows.get(key);if(!record){const row=document.createElement('li'),device=document.createElement('strong'),time=document.createElement('time'),where=document.createElement('span');time.dateTime=visit.at;row.append(device,where,time);record={row,device,time,where};}
   setText(record.device,t(labels[visit.device]||visit.device||'Sin identificar'));setText(record.time,date.format(new Date(visit.at)));setText(record.where,t(pages[visit.page]||visit.page||'Web'));nextRows.set(key,record);rows.push(record.row);
  }
  placeRows(list,rows);recentRows=nextRows;
 }

 function schedulePublic(delay=PUBLIC_REFRESH_MS){
  clearTimeout(publicTimer);if(document.getElementById('public-visit-count')&&!document.hidden)publicTimer=setTimeout(()=>refreshPublic(),delay);
 }
 const recentOpen=()=>Boolean(document.getElementById('public-visit-history')?.open&&document.getElementById('public-visit-recent')?.open);
 async function refreshPublic(force=false){
  if(!document.getElementById('public-visit-count')||document.hidden)return;
  if(publicBusy){publicQueued=publicQueued||force;return;}
  clearTimeout(publicTimer);publicBusy=true;publicController=new AbortController();
  const revision=writeRevision,requestedPage=historyPage,requestedRecent=recentOpen();
  try{
   const params=new URLSearchParams();if(requestedPage>1)params.set('history_page',requestedPage);if(!requestedRecent)params.set('compact','1');
   const path='/api/visits/public'+(params.size?'?'+params:'');
   const {response,data}=await fetchJson(path,{cache:'no-store'},publicController);if(!response.ok)throw Error();
   // A GET already in flight when this browser records a visit can contain an
   // older snapshot. Use the confirmed write, then fetch again for all devices.
   if(revision!==writeRevision){publicQueued=true;return;}
   if(!renderTotal(data.cumulative))return;
   if(requestedPage===historyPage)renderHistory(data.history);
   const updateStatus=document.getElementById('public-visit-update-status');if(updateStatus){if(!updateStatus.hidden)updateStatus.hidden=true;setText(updateStatus,'');}
   if(!requestedRecent||!recentOpen())return;
   renderRecent(document.getElementById('public-visit-list'),data.visits);
   setText(document.getElementById('public-visit-status'),t(data.visits.length?'Horas de Madrid · datos actualizados.':'No hay actividad reciente compartida. El total acumulado se mantiene.'));
  }catch{
   if(!document.hidden){const status=document.getElementById('public-visit-update-status');setText(status,t('No se ha podido actualizar el recuento. Volveremos a intentarlo.'));if(status.hidden)status.hidden=false;}
  }finally{
   publicBusy=false;publicController=null;
   if(publicQueued&&!document.hidden){publicQueued=false;queueMicrotask(()=>refreshPublic(true));}else schedulePublic();
  }
 }
 window.addEventListener('electronicama:navigation-consent',event=>{if(!event.detail?.visitRegistryHandled)choose(event.detail?.allowed,false);});
 window.addEventListener('storage',event=>{if(event.key!==KEY)return;allowed=preference()==='accepted'&&!privacySignal();if(allowed)record('page');else choose(false,false);});
 window.addEventListener('ol:account-refreshed',async()=>{if(!allowed)return;try{const account=await token(),id=account.user?.id||null;if(identityReady&&id!==lastAccount)await record('page');lastAccount=id;identityReady=true;}catch{}});
 window.addEventListener('electronicama:visit-recorded',()=>refreshPublic(true));window.addEventListener('ol:language-changed',()=>refreshPublic(true));
 const resume=()=>{if(!document.hidden){record();refreshPublic(true);}};
 document.addEventListener('visibilitychange',()=>{if(document.hidden){clearTimeout(publicTimer);publicController?.abort();}else resume();});
 window.addEventListener('focus',resume);window.addEventListener('online',resume);window.addEventListener('pageshow',resume);
 document.getElementById('public-visit-older')?.addEventListener('click',()=>{historyPage++;refreshPublic(true);});
 document.getElementById('public-visit-newer')?.addEventListener('click',()=>{historyPage=Math.max(1,historyPage-1);refreshPublic(true);});
 for(const id of ['public-visit-history','public-visit-recent'])document.getElementById(id)?.addEventListener('toggle',()=>{if(!recentOpen())document.getElementById('public-visit-list').replaceChildren();refreshPublic(true);});
 const settings=document.createElement('button');settings.type='button';settings.className='secondary';settings.textContent='Preferencias de visitas';settings.dataset.visitsPreferences='';settings.addEventListener('click',showPreferences);if(!document.getElementById('privacy-button'))(document.querySelector('footer')||document.body).append(settings);
 if(allowed)token().then(account=>{lastAccount=account.user?.id||null;identityReady=true;record('page');}).catch(()=>{});
 else if(!preference()&&!privacySignal()&&!document.getElementById('consent-dialog'))showPreferences();
 if(privacySignal()&&preference()==='accepted')choose(false,false);
 refreshPublic(true);setInterval(()=>record(),60000);
})();
