/* Community uploads stay private until the server confirms a human review. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id);
 const categories={music:'Música',dance:'Bailes',ai:'Inteligencia artificial',other:'Otras creaciones'};
 const states={uploading:'Subida en curso',quarantined:'En cuarentena',published:'Publicado',rejected:'Rechazado',failed:'Subida fallida',deleted:'Retirado'};
 const lists={catalogue:{page:1,pages:1,revision:0},mine:{page:1,pages:1,revision:0},admin:{page:1,pages:1,revision:0}};
 let current=null,csrf='',identityKnown=false,configuration={storage_ready:false,max_file_bytes:0,allowed_mime_types:[]};
 let upload=null,activeQuery='',activeCategory='all';
 const cardRecords=new WeakMap();
 const node=(tag,value,className)=>{const element=document.createElement(tag);if(value!==undefined)element.textContent=value;if(className)element.className=className;return element;};
 const original=(tag,value,className)=>{const element=node(tag,String(value??''),className);element.setAttribute('translate','no');return element;};
 const formatBytes=value=>{
  let size=Number(value)||0,index=0;const units=['B','KB','MB','GB','TB'];
  while(size>=1024&&index<units.length-1){size/=1024;index++;}
  return new Intl.NumberFormat(document.documentElement.lang||'es',{maximumFractionDigits:index?1:0}).format(size)+' '+units[index];
 };
 const when=value=>{if(!value)return '';const date=new Date(value);return Number.isNaN(date.getTime())?'':new Intl.DateTimeFormat(document.documentElement.lang||'es',{dateStyle:'medium'}).format(date);};
 function status(id,message,kind=''){const element=typeof id==='string'?$(id):id;element.textContent=message;element.dataset.kind=kind;}
 function message(error){return error?.message||'No se ha podido completar la operación. Vuelve a intentarlo.';}
 function pauseMedia(root){for(const media of root.querySelectorAll('video')){media.pause();media.removeAttribute('src');media.load();}}
 function updateUploadControls(){
  $('video-upload-form').hidden=!current;
  $('video-upload-guest').hidden=Boolean(current);
  $('video-upload-fields').disabled=!current||Boolean(upload&&!upload.cleanupPending);
  $('video-upload-submit').disabled=!current||!configuration.storage_ready||Boolean(upload);
  $('video-upload-cancel').disabled=Boolean(upload?.cancelling||upload?.finalizationBusy);
  $('video-upload-retry').disabled=Boolean(upload?.finalizationBusy);
 }
 function applyIdentity(data){
  const next=data.user||null,changed=identityKnown&&(current?.id||null)!==(next?.id||null);
  if(changed){
   if(upload){upload.cancelled=true;for(const xhr of upload.requests)xhr.abort();upload=null;$('video-upload-progress-panel').hidden=true;}
   $('video-upload-form').reset();pauseMedia($('video-mine-list'));pauseMedia($('video-admin-list'));
   $('video-mine-list').replaceChildren();$('video-admin-list').replaceChildren();lists.mine.revision++;lists.admin.revision++;
   status('video-upload-status','La cuenta ha cambiado. Comprueba tu sesión antes de continuar.');
  }
  current=next;csrf=data.csrf||'';identityKnown=true;
  $('my-videos').hidden=!current;$('video-my-link').hidden=!current;$('video-admin').hidden=current?.role!=='admin';
  $('video-session-status').textContent=current?'Tu cuenta · @'+current.username:'Puedes descubrir los vídeos publicados sin iniciar sesión.';
  if(current)$('video-session-status').setAttribute('translate','no');else $('video-session-status').removeAttribute('translate');
  updateUploadControls();
 }
 async function identity(){
  const response=await fetch('/api/account/me',{cache:'no-store'});
  if(!response.ok)throw new Error('No se ha podido comprobar la sesión. Recarga la página.');
  const data=await response.json();applyIdentity(data);return data;
 }
 async function api(path,data,retry=true){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),25000),actor=current?.id||null;
  try{
   const response=await fetch(path,data===undefined?{cache:'no-store',signal:controller.signal}:{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
   let result;try{result=await response.json();}catch{throw new Error('El servidor no ha respondido correctamente. Inténtalo de nuevo.');}
   if(response.status===403&&result.code==='csrf_expired'&&data!==undefined&&retry){
    await identity();if((current?.id||null)!==actor)throw new Error('La cuenta ha cambiado. Vuelve a revisar la operación.');
    return api(path,data,false);
   }
   if(!response.ok){const error=new Error(result.error||'No se ha podido completar la operación.');error.status=response.status;error.code=result.code;if(response.status===401&&current)applyIdentity({user:null,csrf});throw error;}
   return result;
  }catch(error){if(error.name==='AbortError')throw new Error('La conexión tarda demasiado. Comprueba el estado antes de repetir la operación.');throw error;}
  finally{clearTimeout(timer);}
 }
 function pagination(kind,data){
  const state=lists[kind];state.page=Math.max(1,Number(data.page)||1);state.pages=Math.max(1,Number(data.pages)||1);
  const total=Math.max(0,Number(data.total)||0);
  $('video-'+kind+'-pagination').hidden=state.pages<=1;
  $('video-'+kind+'-page').textContent='Página '+state.page+' de '+state.pages;
  $('video-'+kind+'-previous').disabled=state.page<=1;$('video-'+kind+'-next').disabled=state.page>=state.pages;
  return total;
 }
 function media(id,preview=false,title=''){
  const root=node('div',undefined,'video-media'),video=node('video');
  video.controls=true;video.preload='none';video.playsInline=true;
  const path=preview?'/api/admin/videos/'+encodeURIComponent(id)+'/preview':'/api/videos/'+encodeURIComponent(id)+'/play';
  video.src=path;video.setAttribute('aria-label',(preview?'Vista privada del vídeo en revisión':'Reproducir vídeo')+(title?' · '+String(title):''));video.setAttribute('translate','no');
  const feedback=node('div',undefined,'video-media-feedback');
  video.addEventListener('play',()=>{for(const other of document.querySelectorAll('.video-zone video'))if(other!==video)other.pause();});
  video.addEventListener('error',()=>{
   if(!video.getAttribute('src'))return;
   const hint=node('p','No se ha podido reproducir el vídeo. Puedes volver a cargarlo; algunos formatos también dependen de tu navegador.');
   const retry=node('button','Volver a cargar el vídeo','secondary');retry.type='button';
   retry.addEventListener('click',()=>{
    const saved=Number.isFinite(video.currentTime)?video.currentTime:0;
    video.addEventListener('loadedmetadata',()=>{if(saved>0&&Number.isFinite(video.duration)&&saved<video.duration)video.currentTime=saved;},{once:true});
    feedback.replaceChildren();video.src=path+'?reload='+Date.now();video.load();
   });feedback.replaceChildren(hint,retry);
  });
  root.append(video,feedback);return root;
 }
 function describe(item,root){
  const tag=node('span',categories[item.category]||'Otras creaciones','video-tag');
  const title=original('h3',item.title||'Vídeo sin título');
  const author=item.author||{},name=author.nickname||author.username||'Comunidad';
  const by=original('p','Por '+name+(author.username&&author.username!==name?' (@'+author.username+')':''),'video-author');
  root.append(tag,title,by);
  if(item.description)root.append(original('p',item.description,'video-description'));
 }
 function reportControl(item){
  const details=node('details',undefined,'video-report');details.append(node('summary','Informar de este vídeo'));
  if(!current){const hint=node('p','Inicia sesión para enviar un aviso a revisión.');const link=node('a','Entrar con mi cuenta','button secondary');link.href='/account?next=%2Fvideos';details.append(hint,link);return details;}
  const form=node('form'),label=node('label','Motivo del aviso'),reason=node('textarea');reason.name='reason';reason.maxLength=1000;reason.rows=3;reason.required=true;reason.placeholder='Explica qué debe revisar administración';label.append(reason);
  const submit=node('button','Enviar a revisión');submit.type='submit';
  const feedback=node('p',undefined,'video-status');feedback.setAttribute('role','status');form.append(label,submit,feedback);
  form.addEventListener('submit',async event=>{event.preventDefault();if(!form.reportValidity())return;submit.disabled=true;try{await api('/api/videos/'+encodeURIComponent(item.id)+'/report',{reason:reason.value.trim()});status(feedback,'Aviso enviado a revisión.','success');reason.value='';}catch(error){status(feedback,message(error),'error');}finally{submit.disabled=false;}});
  details.append(form);return details;
 }
 function publicCard(item){
  const card=node('article',undefined,'video-card');card.dataset.videoId=item.id;card.append(media(item.id,false,item.title));
  const content=node('div',undefined,'video-card-content');describe(item,content);
  if(item.published_at)content.append(node('p',when(item.published_at),'video-meta'));
  content.append(reportControl(item));card.append(content);return card;
 }
 function syncCards(list,items,kind){
  const previous=new Map([...list.children].map(card=>[card.dataset.videoId,card]));
  const desired=items.map(item=>{
   const signature=JSON.stringify([kind,current?.id||null,item.id,item.title,item.description,item.category,item.size_bytes,item.mime_type,item.state,item.created_at,item.published_at,item.author,item.review_reason,item.technical_checked,item.storage_cleanup_pending]);
   let card=previous.get(String(item.id));
   if(!card||cardRecords.get(card)!==signature){card=kind==='catalogue'?publicCard(item):ownerCard(item,kind==='admin');cardRecords.set(card,signature);}
   const reports=card.querySelector('[data-video-report-count]');
   if(reports){const value=(Number(item.report_count)||0)+' avisos recibidos';if(reports.textContent!==value)reports.textContent=value;}
   return card;
  });
  const kept=new Set(desired);
  for(const card of [...list.children])if(!kept.has(card)){pauseMedia(card);card.remove();}
  desired.forEach((card,index)=>{if(list.children[index]!==card)list.insertBefore(card,list.children[index]||null);});
 }
 function ownerCard(item,admin=false){
  const card=node('article',undefined,'video-owner-card');card.dataset.videoId=item.id;
  describe(item,card);
  const badge=node('span',item.storage_cleanup_pending?'Eliminación pendiente':states[item.state]||'Pendiente de revisión','video-state');badge.dataset.state=item.state||'';card.append(badge);
  const meta=[when(item.created_at),formatBytes(item.size_bytes)].filter(Boolean).join(' · ');card.append(node('p',meta,'video-meta'));
  if(item.review_reason)card.append(original('p',item.review_reason,'video-review-reason'));
  if(item.state==='quarantined')card.append(node('p','El vídeo sigue privado. Administración debe revisar su contenido antes de publicarlo.'));
  if(admin){const reports=node('p',(Number(item.report_count)||0)+' avisos recibidos','video-meta');reports.dataset.videoReportCount='true';card.append(reports);if(item.technical_checked&&['quarantined','published','rejected'].includes(item.state))card.append(reviewControl(item));else if(item.state!=='deleted')card.append(node('p','La comprobación técnica todavía no permite revisar este archivo.','video-subtle'));}
  else if(item.state==='published')card.append(media(item.id,false,item.title));
  if(item.storage_cleanup_pending)card.append(node('p','El vídeo está retirado. Su archivo sigue pendiente de eliminación.','video-subtle'));
  const actions=node('div',undefined,'video-actions'),remove=node('button',item.storage_cleanup_pending?'Reintentar eliminación':'Eliminar vídeo','secondary video-danger');remove.type='button';remove.dataset.videoAction='delete';
  const feedback=node('p',undefined,'video-status');feedback.setAttribute('role','status');
  remove.addEventListener('click',async()=>{
   if(!confirm('¿Eliminar este vídeo? Dejará de estar disponible en la comunidad.'))return;
   if(upload?.id===item.id&&!upload.finished){await cancelUpload();return;}
   remove.disabled=true;
   try{
    const result=await api('/api/videos/'+encodeURIComponent(item.id)+'/delete',{});
    pauseMedia(card);badge.textContent=result.storage_deleted===false?'Eliminación pendiente':'Retirado';badge.dataset.state='deleted';
    if(result.storage_deleted===false){status(feedback,'El vídeo está retirado. Falta borrar el archivo almacenado; puedes reintentar la eliminación.');remove.textContent='Reintentar eliminación';await loadCatalogue(lists.catalogue.page);}
    else{if(upload?.id===item.id){upload=null;$('video-upload-progress-panel').hidden=true;updateUploadControls();}status(feedback,'Vídeo eliminado.','success');await Promise.all([loadMine(lists.mine.page),loadCatalogue(lists.catalogue.page),current?.role==='admin'?loadAdmin(lists.admin.page):Promise.resolve()]);}
   }catch(error){status(feedback,message(error),'error');}finally{remove.disabled=false;}
  });actions.append(remove);card.append(actions,feedback);return card;
 }
 function reviewControl(item){
  const details=node('details',undefined,'video-review');details.append(node('summary','Revisar vídeo'));
  details.append(node('p','Vista privada para administración. No compartas el enlace de revisión.','video-subtle'));
  let preview=null;
  details.addEventListener('toggle',()=>{if(details.open&&!preview){preview=media(item.id,true,item.title);details.insertBefore(preview,details.querySelector('form'));}if(!details.open&&preview)for(const video of preview.querySelectorAll('video'))video.pause();});
  const form=node('form'),label=node('label','Motivo o indicación de revisión'),reason=node('textarea');reason.name='reason';reason.rows=3;reason.maxLength=1000;reason.placeholder='Obligatorio para rechazar o devolver a cuarentena';label.append(reason);
  const confirmLabel=node('label',undefined,'video-review-confirm'),checked=node('input');checked.type='checkbox';checked.name='review_confirmed';confirmLabel.append(checked,node('span','He revisado el vídeo y su descripción, y confirmo que puede publicarse.'));
  const actions=node('div',undefined,'video-review-buttons'),feedback=node('p',undefined,'video-status');feedback.setAttribute('role','status');
  const decisions=item.state==='quarantined'?[['approve','Aprobar y publicar'],['reject','Rechazar vídeo']]:[['quarantine','Volver a cuarentena']];
  for(const [decision,title] of decisions){
   const button=node('button',title,decision==='approve'?'':'secondary');button.type='button';button.dataset.videoDecision=decision;
   if(decision==='approve'){button.disabled=true;checked.addEventListener('change',()=>{button.disabled=!checked.checked;});}
   button.addEventListener('click',async()=>{
    if(decision==='approve'&&!checked.checked){status(feedback,'Confirma primero que has revisado el vídeo.','error');checked.focus();return;}
    if(decision!=='approve'&&!reason.value.trim()){status(feedback,'Indica el motivo de la revisión.','error');reason.focus();return;}
    for(const action of actions.querySelectorAll('button'))action.disabled=true;
    try{
     await api('/api/admin/videos/'+encodeURIComponent(item.id)+'/review',{decision,reason:reason.value.trim(),review_confirmed:checked.checked});
     pauseMedia(details);status(feedback,decision==='approve'?'Vídeo aprobado y publicado.':decision==='reject'?'Vídeo rechazado.':'Vídeo devuelto a cuarentena.','success');
     await Promise.all([loadAdmin(lists.admin.page),loadCatalogue(lists.catalogue.page),loadMine(lists.mine.page)]);
     status('video-admin-status',decision==='approve'?'Vídeo aprobado y publicado.':decision==='reject'?'Vídeo rechazado.':'Vídeo devuelto a cuarentena.','success');
    }catch(error){if(error.status===409){await Promise.all([loadAdmin(lists.admin.page),loadCatalogue(lists.catalogue.page),loadMine(lists.mine.page)]);status('video-admin-status','La lista se ha actualizado. '+message(error),'error');}else status(feedback,message(error),'error');for(const action of actions.querySelectorAll('button'))action.disabled=action.dataset.videoDecision==='approve'&&!checked.checked;}
   });actions.append(button);
  }
  if(item.state!=='quarantined')confirmLabel.hidden=true;
  form.append(label,confirmLabel,actions,feedback);form.addEventListener('submit',event=>event.preventDefault());details.append(form);return details;
 }
 async function loadCatalogue(page=1){
  const state=lists.catalogue,revision=++state.revision,list=$('video-catalogue-list');
  $('video-catalogue-refresh').disabled=true;list.setAttribute('aria-busy','true');status('video-catalogue-status','Buscando vídeos…');
  try{
   const query=new URLSearchParams({q:activeQuery,category:activeCategory,page:String(page)}),data=await api('/api/videos?'+query);
   if(revision!==state.revision)return;
   syncCards(list,data.videos||[],'catalogue');const total=pagination('catalogue',data);
   status('video-catalogue-status',total?total+' vídeos publicados.':'Todavía no hay vídeos publicados para esta búsqueda.');
  }catch(error){if(revision===state.revision)status('video-catalogue-status',message(error),'error');}
  finally{if(revision===state.revision){$('video-catalogue-refresh').disabled=false;list.removeAttribute('aria-busy');}}
 }
 async function loadMine(page=1){
  if(!current)return;const actor=current.id,state=lists.mine,revision=++state.revision,list=$('video-mine-list');
  $('video-mine-refresh').disabled=true;status('video-mine-status','Cargando tus vídeos…');
  try{
   const data=await api('/api/videos/me?page='+page);if(revision!==state.revision||current?.id!==actor)return;
   syncCards(list,data.videos||[],'mine');const total=pagination('mine',data);
   status('video-mine-status',total?total+' vídeos en tu cuenta.':'Todavía no has subido ningún vídeo.');
  }catch(error){if(revision===state.revision&&current?.id===actor)status('video-mine-status',message(error),'error');}
  finally{if(revision===state.revision)$('video-mine-refresh').disabled=false;}
 }
 async function loadAdmin(page=1){
  if(current?.role!=='admin')return;const actor=current.id,state=lists.admin,revision=++state.revision,list=$('video-admin-list'),filter=$('video-admin-state').value;
  $('video-admin-refresh').disabled=true;status('video-admin-status','Cargando la revisión…');
  try{
   const data=await api('/api/admin/videos?'+new URLSearchParams({state:filter,page:String(page)}));if(revision!==state.revision||current?.id!==actor||current?.role!=='admin')return;
   syncCards(list,data.videos||[],'admin');const total=pagination('admin',data);
   status('video-admin-status',total?total+' vídeos en este estado.':'No hay vídeos pendientes en este estado.');
  }catch(error){if(revision===state.revision&&current?.id===actor)status('video-admin-status',message(error),'error');}
  finally{if(revision===state.revision)$('video-admin-refresh').disabled=false;}
 }
 async function loadConfiguration(){
  try{
   configuration=await api('/api/videos/config');
   status('video-storage-status',configuration.storage_ready?'La subida está disponible. Tus vídeos se revisan antes de publicarse.':'La subida de vídeos se está preparando.');
   const allowed=Array.isArray(configuration.allowed_mime_types)?configuration.allowed_mime_types:[];
   if(allowed.length)$('video-upload-file').accept=allowed.join(',')+',.mp4,.webm,.mov';
   $('video-file-guidance').textContent='MP4, WebM o MOV. '+(configuration.max_file_bytes?'Máximo técnico por archivo: '+formatBytes(configuration.max_file_bytes)+'. ':'')+'Mantén esta página abierta durante la subida.';
  }catch(error){status('video-storage-status','No se ha podido comprobar la disponibilidad de las subidas. Recarga la página.','error');}
  updateUploadControls();
 }
 class UploadCancelled extends Error{}
 const wait=delay=>new Promise(resolve=>setTimeout(resolve,delay));
 function progress(context){
  if(upload!==context)return;
  const transferred=context.completed+[...context.loaded.values()].reduce((total,value)=>total+value,0);
  const percent=context.file.size?Math.min(100,transferred/context.file.size*100):0;
  $('video-upload-progress').value=percent;
  $('video-upload-progress-label').textContent=Math.floor(percent)+' % · '+formatBytes(transferred)+' de '+formatBytes(context.file.size);
 }
 function partPut(context,url,blob,part){
  let target;try{target=new URL(url);}catch{throw new Error('El destino de subida no es válido.');}
  if(target.protocol!=='https:'||!target.hostname.endsWith('.r2.cloudflarestorage.com')||target.username||target.password)throw new Error('El destino de subida no es válido.');
  return new Promise((resolve,reject)=>{
   const xhr=new XMLHttpRequest();context.requests.add(xhr);xhr.open('PUT',target.href);xhr.timeout=3600000;
   const finish=()=>{context.requests.delete(xhr);};
   xhr.upload.addEventListener('progress',event=>{context.loaded.set(part,Math.min(blob.size,event.loaded));progress(context);});
   xhr.addEventListener('load',()=>{finish();if(xhr.status>=200&&xhr.status<300)resolve();else reject(new Error('No se ha podido transferir una parte del vídeo.'));});
   xhr.addEventListener('error',()=>{finish();reject(new Error('Se ha interrumpido la conexión durante la subida.'));});
   xhr.addEventListener('timeout',()=>{finish();reject(new Error('Una parte del vídeo ha tardado demasiado en subir.'));});
   xhr.addEventListener('abort',()=>{finish();reject(context.cancelled?new UploadCancelled():new Error('La transferencia se ha detenido.'));});
   if(context.cancelled){finish();reject(new UploadCancelled());return;}xhr.send(blob);
  });
 }
 async function sendPart(context,part){
  const start=(part-1)*context.partSize,end=Math.min(context.file.size,start+context.partSize),blob=context.file.slice(start,end);
  for(let attempt=0;attempt<3;attempt++){
   if(context.cancelled)throw new UploadCancelled();
   try{
    const signed=await api('/api/videos/uploads/'+encodeURIComponent(context.id)+'/parts',{part_number:part});if(context.cancelled)throw new UploadCancelled();
    context.loaded.set(part,0);await partPut(context,signed.url,blob,part);
    context.loaded.delete(part);context.completed+=blob.size;progress(context);return;
   }catch(error){
    context.loaded.delete(part);progress(context);
    if(error instanceof UploadCancelled||context.cancelled||attempt===2||error.status&&error.status<500&&error.status!==429)throw error;
    status('video-upload-status','La conexión se ha interrumpido. Reintentando una parte del vídeo…');await wait(700*(attempt+1));
   }
  }
 }
 async function cleanup(context){
  if(!context.id)return true;
  if(current?.id!==context.ownerId)throw new Error('La cuenta ha cambiado. Revisa la subida desde su cuenta original.');
  const result=await api('/api/videos/'+encodeURIComponent(context.id)+'/delete',{});return result.storage_deleted!==false;
 }
 async function cancelUpload(){
  const context=upload;if(!context)return;
  if(context.cleanupPending||context.finalizationPending){
   context.cancelling=true;updateUploadControls();
   try{if(await cleanup(context)){upload=null;$('video-upload-progress-panel').hidden=true;status('video-upload-status','Subida eliminada.','success');await Promise.all([loadMine(1),loadCatalogue(lists.catalogue.page)]);}else{context.cleanupPending=true;context.finalizationPending=false;$('video-upload-retry').hidden=true;$('video-upload-cancel').textContent='Reintentar limpieza';status('video-upload-status','El vídeo está retirado. La limpieza sigue pendiente; vuelve a intentarlo.','error');}}
   catch(error){status('video-upload-status',message(error),'error');}finally{context.cancelling=false;updateUploadControls();}
   return;
  }
  context.cancelled=true;context.cancelling=true;for(const xhr of context.requests)xhr.abort();
  status('video-upload-status','Cancelando la subida…');updateUploadControls();
 }
 async function confirmCompletion(context){
  const completed=await api('/api/videos/uploads/'+encodeURIComponent(context.id)+'/complete',{});
  if(context.cancelled)throw new UploadCancelled();
  const state=completed.video?.state;
  if(!['quarantined','published'].includes(state))throw new Error('El servidor no ha confirmado el estado final. Comprueba Mis vídeos.');
  context.finished=true;context.finalizationPending=false;$('video-upload-form').reset();$('video-upload-retry').hidden=true;
  status('video-upload-status',state==='published'?'El servidor confirma que tu vídeo ya está aprobado y publicado.':'Vídeo en cuarentena. Seguirá privado hasta que administración lo revise y lo apruebe.','success');
  await Promise.all([loadMine(1),current?.role==='admin'?loadAdmin(1):Promise.resolve(),state==='published'?loadCatalogue(lists.catalogue.page):Promise.resolve()]);
  $('video-upload-status').focus({preventScroll:true});
 }
 function uncertainCompletion(context,error){
  context.cancelled=false;context.finalizationPending=true;context.cancelling=false;
  const permanent=error.status&&error.status<500&&![408,409,429].includes(error.status);
  $('video-upload-retry').hidden=Boolean(permanent);$('video-upload-cancel').textContent='Eliminar subida';
  status('video-upload-status','La transferencia ha terminado. '+message(error)+(permanent?' Puedes consultar el resultado en Mis vídeos o eliminar la subida.':' Pulsa Reintentar comprobación para confirmar su estado sin volver a subir el archivo.'),'error');
 }
 async function retryCompletion(){
  const context=upload;if(!context?.finalizationPending||context.finalizationBusy)return;
  context.finalizationBusy=true;updateUploadControls();status('video-upload-status','Comprobando el estado del vídeo…');
  try{await confirmCompletion(context);}catch(error){if(upload===context)uncertainCompletion(context,error);}
  finally{context.finalizationBusy=false;if(upload===context&&context.finished){upload=null;$('video-upload-progress-panel').hidden=true;}updateUploadControls();}
 }
 async function startUpload(event){
  event.preventDefault();const form=$('video-upload-form');if(upload||!current||!configuration.storage_ready||!form.reportValidity())return;
  const file=$('video-upload-file').files[0];if(!file||file.size<=0){status('video-upload-status','Selecciona un vídeo que no esté vacío.','error');return;}
  if(configuration.max_file_bytes&&file.size>Number(configuration.max_file_bytes)){status('video-upload-status','El archivo supera el máximo técnico de '+formatBytes(configuration.max_file_bytes)+'.','error');return;}
  const extension=file.name.split('.').pop().toLowerCase(),fallback={mp4:'video/mp4',webm:'video/webm',mov:'video/quicktime'};
  const mime=configuration.allowed_mime_types?.includes(file.type)?file.type:fallback[extension]||'';
  if(!configuration.allowed_mime_types?.includes(mime)){status('video-upload-status','Selecciona un archivo MP4, WebM o MOV.','error');return;}
  const context={id:null,ownerId:current.id,file,partSize:0,partCount:0,completed:0,loaded:new Map(),requests:new Set(),cancelled:false,cancelling:false,cleanupPending:false,finished:false,finalizing:false,finalizationPending:false,finalizationBusy:false};upload=context;
  updateUploadControls();$('video-upload-progress-panel').hidden=false;$('video-upload-progress').value=0;$('video-upload-cancel').textContent='Cancelar subida';$('video-upload-retry').hidden=true;
  $('video-upload-progress-label').textContent='Preparando la subida…';status('video-upload-status','Preparando tu vídeo. Todavía no está publicado.');
  try{
   const result=await api('/api/videos/uploads',{title:form.elements.title.value.trim(),description:form.elements.description.value.trim(),category:form.elements.category.value,filename:file.name,size_bytes:file.size,mime_type:mime,rights_confirmed:$('video-upload-rights').checked});
   context.id=result.id;context.partSize=Number(result.part_size);context.partCount=Number(result.part_count);
   if(!context.id||!Number.isInteger(context.partSize)||context.partSize<=0||!Number.isInteger(context.partCount)||context.partCount<1||context.partCount>10000||Math.ceil(file.size/context.partSize)!==context.partCount)throw new Error('El servidor no ha podido preparar una subida válida.');
   if(context.cancelled)throw new UploadCancelled();
   let next=1;
   async function worker(){while(next<=context.partCount&&!context.cancelled){const part=next++;await sendPart(context,part);}}
   await Promise.all(Array.from({length:Math.min(2,context.partCount)},()=>worker()));
   if(context.cancelled)throw new UploadCancelled();
   status('video-upload-status','Transferencia terminada. Comprobando el archivo antes de ponerlo en cuarentena…');
   context.finalizing=true;await confirmCompletion(context);
  }catch(error){
   const userCancelled=context.cancelled;context.cancelled=true;
   for(const xhr of context.requests)xhr.abort();
   if(upload!==context)return;
   if(context.finalizing&&!userCancelled){uncertainCompletion(context,error);await loadMine(1);return;}
   let cleaned=true;
   if(!context.finished){try{cleaned=await cleanup(context);}catch{cleaned=false;}}
   if(upload!==context)return;
   if(!cleaned){context.cleanupPending=true;context.cancelling=false;$('video-upload-cancel').textContent='Reintentar limpieza';status('video-upload-status',(userCancelled?'La subida se ha detenido.':message(error))+' El archivo no está publicado. Falta confirmar su eliminación; pulsa Reintentar limpieza.','error');}
   else status('video-upload-status',userCancelled?'Subida cancelada.':message(error),'error');
   await loadMine(1);
  }finally{
   if(upload===context&&!context.cleanupPending&&!context.finalizationPending){upload=null;$('video-upload-progress-panel').hidden=true;}
   updateUploadControls();
  }
 }
 $('video-search-form').addEventListener('submit',event=>{event.preventDefault();activeQuery=$('video-search').value.trim();activeCategory=$('video-category').value;loadCatalogue(1);});
 $('video-category').addEventListener('change',()=>{activeQuery=$('video-search').value.trim();activeCategory=$('video-category').value;loadCatalogue(1);});
 $('video-catalogue-refresh').addEventListener('click',()=>loadCatalogue(lists.catalogue.page));
 $('video-mine-refresh').addEventListener('click',()=>loadMine(lists.mine.page));
 $('video-admin-refresh').addEventListener('click',()=>loadAdmin(lists.admin.page));
 $('video-admin-state').addEventListener('change',()=>loadAdmin(1));
 for(const [kind,loader] of [['catalogue',loadCatalogue],['mine',loadMine],['admin',loadAdmin]]){
  $('video-'+kind+'-previous').addEventListener('click',()=>loader(Math.max(1,lists[kind].page-1)));
  $('video-'+kind+'-next').addEventListener('click',()=>loader(Math.min(lists[kind].pages,lists[kind].page+1)));
 }
 $('video-upload-form').addEventListener('submit',startUpload);$('video-upload-cancel').addEventListener('click',cancelUpload);$('video-upload-retry').addEventListener('click',retryCompletion);
 window.addEventListener('beforeunload',event=>{if(upload&&!upload.finished&&!upload.cleanupPending&&!upload.finalizationPending){event.preventDefault();event.returnValue='';}});
 let checkingIdentity=false;
 document.addEventListener('visibilitychange',async()=>{if(document.hidden||upload||checkingIdentity)return;checkingIdentity=true;const previous=current?.id;try{await identity();if(previous!==current?.id){await Promise.all([loadCatalogue(lists.catalogue.page),loadMine(1),loadAdmin(1)]);}}catch{}finally{checkingIdentity=false;}});
 window.addEventListener('pageshow',event=>{if(event.persisted)identity().catch(()=>{});});
 window.OlVideosReady=(async()=>{
  try{await identity();}catch(error){status('video-session-status',message(error),'error');updateUploadControls();}
  await Promise.all([loadConfiguration(),loadCatalogue(1),loadMine(1),loadAdmin(1)]);
 })();
})();
