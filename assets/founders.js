import {founderBadge} from '/assets/badges.js?v=9.15.0';
/* Ol Live promotion: real numbered places, one per account, no payment. */
const banner=document.getElementById('founders');
if(banner&&!banner.hasAttribute('data-informational')){const $=id=>document.getElementById(id);let csrf='',account=null,busy=false,mine=null,signature={},selectedAudio=null,audioToken='',humanId='';
 let inspectBusy=false,inspectPending=false,fieldsPending=false,dirty=false,editRevision=0,writeRevision=0,inspectRevision=0,previewKey='';
 const inspectWaiters=[];
 const form=$('founder-signature-form'),editing=()=>form.contains(document.activeElement);
 function markDirty(){dirty=true;editRevision++;}
 async function api(path,data){
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),8000);
  try{
   const response=await fetch(path,{cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json',...(data?{'X-CSRF-Token':csrf}:{})},...(data?{method:'POST',body:JSON.stringify(data)}:{})});
   const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo comprobar la promoción.');return result;
  }catch(error){if(error.name==='AbortError')throw new Error('No se pudo actualizar la insignia. Volveremos a intentarlo.');throw error;}
  finally{clearTimeout(deadline);}
 }
 function applySignature(next){
  signature=next||{};$('founder-mode').value=signature.mode||'numero';$('founder-letter').value=signature.letter||'';
  $('founder-caption').value=signature.caption||'Buen rollo';$('founder-voice').value=signature.audio?.voice||'brisa';
  selectedAudio=signature.audio?.kind==='track'?signature.audio.track:null;audioToken='';fieldsPending=false;updateSignaturePreview(true);
 }
 function inspect(){
  inspectPending=true;inspectRevision++;
  const complete=new Promise(resolve=>inspectWaiters.push(resolve));void drainInspection();return complete;
 }
 async function drainInspection(){
  if(inspectBusy||document.hidden||!inspectPending)return;
  inspectBusy=true;inspectPending=false;
  const waiting=inspectWaiters.splice(0),readRevision=writeRevision,requestedRevision=inspectRevision;
  try{
   const current=await api('/api/account/me');csrf=current.csrf;account=current.user;
   const data=await api('/api/live/founders');
   // Reads can finish after another change or a confirmed write from this page.
   if(readRevision!==writeRevision||requestedRevision!==inspectRevision||document.hidden){inspectPending=true;return;}
   $('founder-remaining').textContent=data.remaining;
   $('founder-counter').textContent=`${data.claimed} de ${data.limit} insignias de fundador asignadas`;
   $('founder-progress').value=data.claimed;mine=data.mine;
   if(!busy&&!humanId)$('founder-human-check').classList.add('hidden');
   $('founder-claim').disabled=Boolean(mine)||Boolean(account?.live_annual)||busy;
   $('founder-claim').textContent=mine?'Tu insignia de fundador n.º '+mine.number:(account?.live_annual?'Ol Live activo · participante':account?.live_lifetime||account?.full_service||account?.role==='admin'?'Consultar mi insignia de fundador':'1 · Contratar Ol Live · 25 €/año');
   $('founder-status').textContent=mine?(mine.revoked_at?'Tu número de fundador n.º '+mine.number+' está desactivado. Contacta con administración.':'Tu insignia de fundador n.º '+mine.number+'. Tu número es personal, exclusivo y permanente. Emitir requiere acceso vigente a Ol Live.'+(mine.activity?.activity_exempt?' No tienes obligación de emitir.':'')):'El pago anual confirmado asigna automáticamente una de las 100 insignias numeradas disponibles. Cada número es personal, exclusivo y permanente. El acceso a Ol Live se renueva por separado: 25 € al año, sin prueba gratuita. Después de las 100 insignias, continúa el acceso anual ordinario. Para conservar los beneficios de emisión se mantiene la actividad indicada; el fundador n.º 1 está exento de emitir.';
   const canStream=Boolean(account?.streamer_active||account?.live_annual||account?.live_lifetime||account?.full_service||account?.role==='admin');
   $('founder-studio').classList.toggle('hidden',!mine||Boolean(mine.revoked_at)||mine.activity?.eligible===false||!canStream);
   $('my-founder-signature').classList.toggle('hidden',!mine||Boolean(mine.revoked_at));
   if(mine&&!mine.revoked_at){
    signature=mine.signature||{};
    // Focus is checked after both requests, so typing during a slow read wins.
    if(dirty||editing())fieldsPending=true;else applySignature(signature);
   }
  }catch(error){$('founder-status').textContent=error.message;$('founder-claim').disabled=true;}
  finally{
   inspectBusy=false;for(const resolve of waiting)resolve();
   if(inspectPending&&!document.hidden)queueMicrotask(()=>void drainInspection());
  }
 }
 async function loadHuman(){$('human-answer').disabled=true;$('founder-claim').disabled=true;try{const d=await api('/api/account/human-check');humanId=d.id;$('human-image').src=d.image;$('human-answer').value='';$('human-status').textContent='El código caduca a los cinco minutos.';}catch(e){$('human-status').textContent=e.message;humanId='';}finally{$('human-answer').disabled=false;$('founder-claim').disabled=false;}}
 $('human-refresh').addEventListener('click',loadHuman);
 $('founder-claim').addEventListener('click',async()=>{if(busy)return;if(!account){location.assign('/account?next='+encodeURIComponent('/live#founders'));return;}if(!account.live_annual&&!account.live_lifetime&&!account.full_service&&account.role!=='admin'){location.assign('/account#pricing');return;}if(!humanId){$('founder-human-check').classList.remove('hidden');await loadHuman();$('human-answer').focus();$('founder-claim').textContent='Confirmar mi insignia';$('founder-status').textContent='Completa el código visual y pulsa Confirmar mi insignia.';return;}busy=true;$('founder-claim').disabled=true;$('founder-status').textContent='Asignando tu insignia de fundador…';try{await api('/api/live/founders/claim',{human_id:humanId,human_answer:$('human-answer').value});location.assign('/live?welcome=founder#creator-panel');}catch(error){$('founder-status').textContent=error.message;$('founder-claim').disabled=false;await loadHuman();}finally{busy=false;}});
 function updateSignaturePreview(preserveOpen=false){
  if(!mine)return;
  const mode=$('founder-mode').value;
  $('founder-letter-label').classList.toggle('hidden',mode!=='letra');$('founder-song-panel').classList.toggle('hidden',mode!=='cancion');$('founder-voice-label').classList.toggle('hidden',mode!=='sonido');
  const audio=mode==='sonido'?{kind:'tone',voice:$('founder-voice').value}:mode==='cancion'&&selectedAudio?{kind:'track',track:selectedAudio}:null;
  const next={mode,letter:$('founder-letter').value.toUpperCase(),caption:$('founder-caption').value,audio},key=JSON.stringify({number:mine.number,...next});
  if(key===previewKey&&$('founder-signature-preview').firstElementChild)return;
  const previous=$('founder-signature-preview').firstElementChild,preview=founderBadge(mine.number,next);
  preview.open=preserveOpen&&previous?previous.open:true;
  previous?.querySelectorAll('audio').forEach(media=>media.pause());$('founder-signature-preview').replaceChildren(preview);previewKey=key;
 }
 const previewInputs=new Set(['founder-mode','founder-letter','founder-caption','founder-voice']);
 for(const event of ['input','change'])form.addEventListener(event,event=>{markDirty();if(previewInputs.has(event.target.id))updateSignaturePreview();});
 $('founder-audio-search').addEventListener('click',async()=>{const button=$('founder-audio-search');button.disabled=true;$('founder-signature-status').textContent='Buscando canciones y sonidos gratuitos…';try{const data=await api('/api/live/founders/audio-search?q='+encodeURIComponent($('founder-audio-query').value));$('founder-audio-results').replaceChildren();for(const item of data.tracks){const choice=document.createElement('button');choice.type='button';choice.textContent=item.track.title+' · '+item.track.channel;choice.addEventListener('click',()=>{selectedAudio=item.track;audioToken=item.token;markDirty();$('founder-signature-status').textContent='Seleccionado: '+item.track.title;updateSignaturePreview();});$('founder-audio-results').append(choice);}$('founder-signature-status').textContent=data.tracks.length?'Elige una grabación para tu firma sonora.':'No se encontraron grabaciones. Prueba piano, campana o aplausos.';}catch(error){$('founder-signature-status').textContent=error.message;}finally{button.disabled=false;}});
 form.addEventListener('submit',async event=>{
  event.preventDefault();const button=$('founder-signature-save');if(button.disabled)return;button.disabled=true;
  const submittedRevision=editRevision;
  try{
   const data=await api('/api/live/founders/signature',{mode:$('founder-mode').value,letter:$('founder-letter').value,caption:$('founder-caption').value,voice:$('founder-voice').value,audio_token:audioToken,keep_audio:!audioToken});
   writeRevision++;signature=data.signature;
   if(mine)mine={...mine,number:data.number,signature};
   if(editRevision===submittedRevision){dirty=false;applySignature(signature);}
   $('founder-signature-status').textContent=editRevision===submittedRevision?'Insignia personalizada. Tu número oficial sigue siendo el '+data.number+'.':'Insignia guardada. Conservamos los cambios nuevos que todavía no has guardado.';
   void inspect();
  }catch(error){$('founder-signature-status').textContent=error.message;}
  finally{button.disabled=false;}
 });
 window.addEventListener('ol:interface-update',event=>{if(event.detail?.public||event.detail?.account)void inspect();});
 document.addEventListener('focusout',()=>{setTimeout(()=>{if(fieldsPending&&!dirty&&!editing())void inspect();},0);});
 for(const event of ['focus','online','pageshow'])window.addEventListener(event,()=>void inspect());
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)void inspect();});
 setInterval(()=>{if(!document.hidden&&(account?.role==='admin'||mine))void inspect();},30000);
 window.OlFounders={begin:async()=>{await inspect();$('founder-claim').click();}};
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',inspect,{once:true});else inspect();
}
