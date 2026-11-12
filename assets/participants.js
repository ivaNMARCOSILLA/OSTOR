/* Read-only participant records, loaded only for an authenticated administrator. */
(()=>{
 'use strict';
 const panel=document.getElementById('participant-tracking'),root=document.getElementById('participant-tracking-content');
 if(!panel||!root)return;
 let adminId=null,authRevision=0,epoch=0,authController=null,listController=null,detailController=null;
 let mounted=false,loaded=false,page=1,pages=1,selected=null,detailLoadedId=null,listRows=[],timer=null,listRevision=0,detailRevision=0,ui={};
 panel.hidden=true;
 const make=(tag,value,className)=>{const node=document.createElement(tag);if(value!==undefined)node.textContent=String(value);if(className)node.className=className;return node;};
 const original=(tag,value,className)=>{const node=make(tag,value,className);node.setAttribute('translate','no');return node;};
 const valueOrUnknown=value=>value===null||value===undefined||value===''?'No disponible':String(value);
 const validId=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
 const labelled=(label,value,className='participant-meta')=>{const node=make('span',undefined,className);node.append(make('span',label),document.createTextNode(' '),original('span',value));return node;};
 const states={uploading:'Subiendo',quarantined:'En cuarentena',published:'Publicado',rejected:'Rechazado',failed:'Con error',deleted:'Eliminado'};
 function date(value){
  if(!value)return 'No disponible';
  const instant=new Date(value);if(!Number.isFinite(instant.getTime()))return 'No disponible';
  if(instant.getUTCFullYear()>9000)return 'Sin vencimiento';
  return instant.toLocaleString(document.documentElement.lang||'es',{dateStyle:'medium',timeStyle:'short'});
 }
 function duration(value){
  if(value===null||value===undefined||!Number.isFinite(Number(value))||Number(value)<0)return 'No disponible';
  const minutes=Math.floor(Math.max(0,Number(value))/60),hours=Math.floor(minutes/60);
  return hours?hours+' h '+minutes%60+' min':minutes+' min';
 }
 function accessLabel(row){
  if(row.archived)return 'Cuenta archivada';
  if(row.account_activated===false)return 'Invitación pendiente';
  if(row.live_annual)return 'Ol Live anual activo';
  if(row.full_service)return 'Acceso completo gratuito';
  if(row.complimentary)return 'Acceso gratuito de administración';
  return row.streamer_active||row.access_active?'Acceso a Ol Live activo':'Cuenta gratuita';
 }
 function notice(value,error=false){if(ui.status){ui.status.textContent=value;ui.status.classList.toggle('participant-error',error);}}
 function cancel(){clearTimeout(timer);timer=null;listController?.abort();detailController?.abort();listRevision++;detailRevision++;}
 function clearPrivate(){
  cancel();epoch++;adminId=null;loaded=false;mounted=false;selected=null;detailLoadedId=null;page=1;pages=1;listRows=[];ui={};root.replaceChildren();panel.open=false;panel.hidden=true;
 }
 async function json(path,controller){
  const timeout=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await fetch(path,{cache:'no-store',credentials:'same-origin',signal:controller.signal});
   let data;try{data=await response.json();}catch{throw new Error('No se han podido leer los datos. Inténtalo de nuevo.');}
   if(!response.ok){const error=new Error(data.error||'No se han podido consultar los participantes.');error.status=response.status;throw error;}
   return data;
  }finally{clearTimeout(timeout);}
 }
 function button(label,action,className='secondary'){
  const node=make('button',label,className);node.type='button';node.addEventListener('click',action);return node;
 }
 function mount(){
  if(mounted)return;mounted=true;
  const note=make('p','Consulta el registro y la participación que constan en electronicama. Cuando no hay actividad registrada se indica como no disponible.','participant-note');
  const form=make('form',undefined,'participant-search');form.id='participant-search-form';form.setAttribute('role','search');
  const searchLabel=make('label','Usuario o apodo');searchLabel.htmlFor='participant-search';
  const search=make('input');search.id='participant-search';search.type='search';search.maxLength=120;search.placeholder='Buscar una cuenta';search.autocomplete='off';searchLabel.append(search);
  const archivedLabel=make('label',undefined,'participant-archived');
  const archived=make('input');archived.id='participant-show-archived';archived.type='checkbox';archivedLabel.append(archived,make('span','Incluir cuentas archivadas'));
  const submit=make('button','Buscar');submit.type='submit';
  const refresh=button('Actualizar seguimiento',()=>{clearTimeout(timer);loadList(true);});refresh.id='participant-refresh';
  form.append(searchLabel,archivedLabel,submit,refresh);
  const status=make('p',undefined,'participant-status');status.id='participant-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const layout=make('div',undefined,'participant-layout'),column=make('div',undefined,'participant-list-column');
  const list=make('ul',undefined,'participant-list');list.id='participant-list';list.setAttribute('aria-label','Cuentas participantes');
  const pagination=make('nav',undefined,'participant-pagination');pagination.setAttribute('aria-label','Páginas de participantes');
  const previous=button('Anterior',()=>{if(page>1){page--;loadList();}});previous.id='participant-previous';
  const pageText=make('span');pageText.id='participant-page';
  const next=button('Siguiente',()=>{if(page<pages){page++;loadList();}});next.id='participant-next';pagination.append(previous,pageText,next);
  const detail=make('section',undefined,'participant-detail');detail.id='participant-detail';detail.setAttribute('aria-labelledby','participant-detail-title');
  detail.append(make('h3','Ficha del participante'),make('p','Selecciona una cuenta para consultar su seguimiento.'));detail.firstElementChild.id='participant-detail-title';
  column.append(list,pagination);layout.append(column,detail);root.append(note,form,status,layout);
  ui={search,archived,submit,refresh,status,list,previous,next,pageText,detail};
  form.addEventListener('submit',event=>{event.preventDefault();clearTimeout(timer);page=1;loadList();});
  search.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>{page=1;loadList();},250);});
  archived.addEventListener('change',()=>{clearTimeout(timer);page=1;loadList();});
 }
 function renderList(data){
  listRows=Array.isArray(data.participants)?data.participants:[];
  page=Math.max(1,Number(data.page)||1);pages=Math.max(1,Number(data.pages)||1);
  const fragment=document.createDocumentFragment();
  for(const row of listRows){
   if(!validId(row.id))continue;
   const item=make('li'),open=button('',()=>openParticipant(row.id),'participant-choice');
   open.dataset.participantId=row.id;open.setAttribute('aria-controls','participant-detail');open.setAttribute('aria-pressed',row.id===selected?'true':'false');
   open.append(original('strong',row.nickname||row.username||'Cuenta'),original('span','@'+String(row.username||''),'participant-username'),make('span',accessLabel(row),'participant-access'));
   open.append(labelled('Alta:',date(row.created_at)),labelled('Última actividad:',date(row.last_activity_at)));
   item.append(open);fragment.append(item);
  }
  if(!fragment.childNodes.length)fragment.append(make('li','No hay participantes para esta búsqueda.','participant-empty'));
  ui.list.replaceChildren(fragment);ui.previous.disabled=page<=1;ui.next.disabled=page>=pages;ui.pageText.textContent='Página '+page+' de '+pages;
  const total=Math.max(0,Number(data.total)||0);notice(total+' cuentas · selecciona una para ver su ficha.');
 }
 async function loadList(refreshDetail=false){
  if(!adminId||!panel.open)return;mount();
  const revision=++listRevision,currentEpoch=epoch;listController?.abort();const controller=new AbortController();listController=controller;
  const params=new URLSearchParams({q:ui.search.value.trim(),page:String(page),archived:ui.archived.checked?'1':'0'});
  notice('Consultando participantes…');ui.list.setAttribute('aria-busy','true');
  try{
   const data=await json('/api/admin/participants?'+params,controller);
   if(revision!==listRevision||currentEpoch!==epoch||!adminId||!panel.open)return;
   loaded=true;renderList(data);if(refreshDetail&&selected)openParticipant(selected);
  }catch(error){
   if(currentEpoch!==epoch||revision!==listRevision)return;
   if(error.status===401||error.status===403){clearPrivate();return;}
   if(error.name!=='AbortError')notice(error.message,true);
   else if(listController===controller)notice('La consulta tarda demasiado. Puedes volver a actualizar.',true);
  }finally{if(currentEpoch===epoch&&listController===controller)ui.list?.removeAttribute('aria-busy');}
 }
 function facts(rows){
  const dl=make('dl',undefined,'participant-facts');
  for(const [label,value] of rows){dl.append(make('dt',label),make('dd',valueOrUnknown(value)));}return dl;
 }
 function block(title,content){const article=make('article',undefined,'participant-block');article.append(make('h4',title),content);return article;}
 function records(rows,build,empty){
  if(!Array.isArray(rows)||!rows.length)return make('p',empty,'participant-empty');
  const list=make('ul',undefined,'participant-records');for(const row of rows.slice(0,50)){const item=make('li');build(row,item);list.append(item);}return list;
 }
 function renderDetail(data){
  const participant=data.participant||{},access=participant.access||{},activity=data.activity||{},ownership=data.founder_ownership;
  const fragment=document.createDocumentFragment(),title=original('h3',(participant.nickname&&participant.nickname!==participant.username?participant.nickname+' · ':'')+'@'+String(participant.username||''));
  title.id='participant-detail-title';title.tabIndex=-1;fragment.append(title);
  fragment.append(facts([
   ['Alta de la cuenta',date(participant.created_at)],['Registro de participante',date(participant.registered_at)],['Activación',participant.account_activated===false?'Invitación pendiente':'Cuenta activada'],
   ['Estado',participant.archived?'Archivada':'Disponible'],['Permiso de cuenta',participant.role==='admin'?'Administrador':'Participante'],
   ['Rol de comunidad',({activo:'Activo',voluntario:'Voluntario',docente:'Docente'})[access.community_role]||'No disponible'],
   ['Última actividad registrada',date(activity.last_activity_at||participant.last_activity_at)]
  ]));
  const founder=ownership?('N.º '+String(ownership.number)+(ownership.revoked?' · revocada':ownership.permanent?' · pertenencia permanente':'')):'Sin insignia asignada';
  fragment.append(block('Acceso a Ol Live',facts([
   ['Acceso actual',accessLabel({...participant,...access,access_active:access.active})],
   ['Vigente hasta',date(access.access_until)],['Insignia de fundador',founder]
  ])));
  if(ownership)fragment.append(make('p','La pertenencia de la insignia y el acceso anual se muestran por separado.','participant-note'));
  fragment.append(block('Actividad verificada',facts([
   ['Tiempo registrado',duration(activity.verified_seconds)],['Última verificación',date(activity.last_verified_at)],['Vigencia de la actividad',date(activity.qualification_until)]
  ])));
  fragment.append(block('Canales de Ol Live',records(data.channels,(row,item)=>{
   item.append(original('strong',row.title||'Canal'),make('span',row.live?'En directo':'Sin emisión activa'),labelled('Actualizado:',date(row.updated_at)));
   if(validId(row.id)){const link=make('a','Abrir canal');link.href='/live#canal-'+row.id;item.append(link);}
  },'No hay canales registrados.')));
  const videos=data.videos||{},counts=videos.counts||{},videoSection=make('div');
  videoSection.append(facts(Object.entries(states).map(([state,label])=>[label,counts[state]===null||counts[state]===undefined?'No disponible':counts[state]])));
  videoSection.append(records(videos.latest,(row,item)=>{
   item.append(original('strong',row.title||'Vídeo'),make('span',states[row.state]||'Estado no disponible'),make('span',date(row.published_at||row.updated_at||row.created_at),'participant-meta'));
  },'No hay vídeos registrados.'));
  fragment.append(block('Vídeos de la comunidad',videoSection));
  fragment.append(block('Pagos verificados',records(data.payments,(row,item)=>{
   const amount=Number.isFinite(Number(row.amount_cents))&&row.amount_cents!==null?new Intl.NumberFormat(document.documentElement.lang||'es',{style:'currency',currency:'EUR'}).format(Number(row.amount_cents)/100):'Importe no disponible';
   item.append(make('strong',amount+' · '+(row.plan==='annual'?'Ol Live anual':row.plan==='lifetime'?'Acceso histórico':'Periodo de acceso')),
    labelled('Verificado:',date(row.verified_at)),labelled('Acceso hasta:',date(row.ends_at)));
  },'No hay pagos verificados.')));
  fragment.append(block('Recorrido de la cuenta',records(data.timeline,(row,item)=>{
   item.append(make('strong',row.label||'Registro de la cuenta'),make('span',date(row.at),'participant-meta'));
   if(row.detail)item.append(original('span',row.detail));
  },'No hay más cambios registrados.')));
  ui.detail.replaceChildren(fragment);detailLoadedId=selected;
 }
 async function openParticipant(id){
  if(!adminId||!panel.open||!validId(id))return;
  selected=id;detailLoadedId=null;for(const button of ui.list.querySelectorAll('[data-participant-id]'))button.setAttribute('aria-pressed',button.dataset.participantId===id?'true':'false');
  const revision=++detailRevision,currentEpoch=epoch;detailController?.abort();const controller=new AbortController();detailController=controller;
  const heading=make('h3','Ficha del participante');heading.id='participant-detail-title';const progress=make('p','Cargando ficha…');progress.setAttribute('role','status');ui.detail.replaceChildren(heading,progress);ui.detail.setAttribute('aria-busy','true');
  try{
   const data=await json('/api/admin/participants/'+encodeURIComponent(id),controller);
   if(revision!==detailRevision||currentEpoch!==epoch||!adminId||selected!==id||!panel.open)return;
   renderDetail(data);
  }catch(error){
   if(revision!==detailRevision||currentEpoch!==epoch)return;
   if(error.status===401||error.status===403){clearPrivate();return;}
   const feedback=make('p',error.name==='AbortError'?'La consulta tarda demasiado. Vuelve a seleccionar la cuenta.':error.message,'participant-error');feedback.setAttribute('role','status');ui.detail.replaceChildren(heading,feedback);
  }finally{if(currentEpoch===epoch&&detailController===controller)ui.detail?.removeAttribute('aria-busy');}
 }
 async function inspectAccount(){
  const revision=++authRevision;authController?.abort();const controller=new AbortController();authController=controller;
  try{
   const data=await json('/api/account/me',controller);
   if(revision!==authRevision)return;
   if(data.user?.role!=='admin'||!data.user.id){clearPrivate();return;}
   if(adminId!==data.user.id){clearPrivate();adminId=data.user.id;}
   panel.hidden=false;mount();if(panel.open&&!loaded)loadList();
  }catch(error){if(revision===authRevision)clearPrivate();}
 }
 panel.addEventListener('toggle',()=>{if(panel.open&&adminId){if(!loaded)loadList();else if(selected&&detailLoadedId!==selected)openParticipant(selected);}else if(!panel.open)cancel();});
 window.addEventListener('ol:account-refreshed',inspectAccount);window.addEventListener('pageshow',inspectAccount);
 inspectAccount();
})();
