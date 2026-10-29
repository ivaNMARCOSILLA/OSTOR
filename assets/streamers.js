import {openSubscription} from '/assets/subscriptions.js?v=9.13.0';
import {founderBadge} from '/assets/badges.js?v=9.15.0';
'use strict';
import {StreamCommunity} from '/assets/community.js?v=9.18.2';
import {StudioTools} from '/assets/studio-tools.js?v=9.13.0';
const $=id=>document.getElementById(id);
let premiereOnly=false;
let publicInfo=null,liveCategory='all';
const categoryNames={videojuegos:'Videojuegos',musica:'Música',entretenimiento:'Entretenimiento',actualidad:'Actualidad'};
let info=null,room=null,selected=null,publishing=false,heartbeat=null,sdkPromise=null,connecting=false,connectionGeneration=0,giftRevision=0,refreshing=false,heartbeatBusy=false,heartbeatVerified=false;
const status=text=>{$('stream-status').textContent=text;};
async function api(path,data){
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),18000);
 try{const r=await window.MaggySession.fetch(path,{signal:controller.signal,...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
 let json;try{json=await r.json();}catch{throw new Error('El servidor no devolvió una respuesta válida. Vuelve a intentarlo.');}
 if(!r.ok){const error=new Error(json.error||'No se pudo completar la operación.');error.status=r.status;error.code=json.code;throw error;}return json;
 }catch(error){if(error.name==='AbortError')throw new Error('El servidor tarda en responder. Vuelve a intentarlo.');throw error;}finally{clearTimeout(timer);}
}
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
function clearFounderStamp(){const stamp=$('live-founder-stamp');if(!stamp)return;stamp.querySelectorAll('audio').forEach(audio=>audio.pause());stamp.replaceChildren();}
const attachedTracks=new Map();
const tools=new StudioTools({setLayout:layout=>api('/api/streamers/me/layout',{layout}),getRoom:()=>publishing?room:null,getPreview:()=>previewStream,getChannel:()=>room&&selected?selected:info?.mine,restartPreview:()=>privatePreview(),canPreview:()=>!connecting&&!publishing&&Boolean(info?.mine&&info.streamer_active),report:message=>{status(message);$(room?'live-tools-status':'studio-status').textContent=message;}});
async function sdk(){if(window.LivekitClient)return window.LivekitClient;if(!sdkPromise)sdkPromise=new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='/assets/vendor/livekit-client-2.23.0.umd.js';s.onload=()=>resolve(window.LivekitClient);s.onerror=()=>reject(new Error('No se pudo cargar el reproductor de directos.'));document.head.append(s);});return sdkPromise;}
async function refresh(){
 if(refreshing)return;refreshing=true;try{
 const launch=await api('/api/status');
 const previewUser=(await api('/api/account/me')).user;
 if(room&&!previewUser?.active){await disconnect();status('El acceso a Ol Livis ha terminado. Inicia sesión o revisa tu cuenta.');}
 document.body.classList.toggle('ol-livis-open',!launch.live_premiere);
 premiereOnly=launch.live_premiere&&previewUser?.role!=='admin'&&!previewUser?.full_service;
 document.body.classList.toggle('ol-private-preview',Boolean(launch.live_premiere&&previewUser?.full_service));
 if(premiereOnly){document.body.classList.add('ol-live-premiere-only');return;}
 document.body.classList.remove('ol-live-premiere-only');
 if(!window.MaggySession.premium){publicInfo=await api('/api/live/catalogue');renderCatalogue();return;}
 info=await api('/api/streamers');
 $('stream-unavailable').classList.toggle('hidden',info.video_ready);
 $('video-setup').classList.toggle('hidden',!info.setup_checks);
 if(info.setup_checks){$('open-video-preview').classList.toggle('hidden',info.setup_environment!=='production');$('setup-environment').textContent=info.setup_environment==='production'?'Estás en electronicama.com. El vídeo de esta web necesita sus variables en Production. Las claves guardadas solo en Preview no lo activan. Comprueba aquí la conexión después del despliegue.':info.setup_environment==='preview'?'Estás en la vista previa de pruebas. Los cobros siguen bloqueados durante la comprobación.':'Estudio local de pruebas.';const list=$('video-checks');list.replaceChildren();for(const [name,ok] of Object.entries(info.setup_checks))list.append(node('li',`${name}: ${ok?'correcto':'pendiente de corregir'}`));}
 $('creator-panel').classList.toggle('hidden',!info.streamer_active);$('studio-flow').classList.toggle('hidden',!info.streamer_active);
 renderCatalogue();
 renderStudio();
 if(room&&!publishing&&selected){const current=room,generation=connectionGeneration;try{const access=await api(`/api/streamers/${encodeURIComponent(selected.id)}/access`);if(room===current&&generation===connectionGeneration&&access.layout)$('live-media').dataset.layout=access.layout;if(room===current&&generation===connectionGeneration&&access.ended){await disconnect();status('El creador ha finalizado el directo.');}}catch(error){if(room===current&&generation===connectionGeneration){if([401,402,403,404].includes(error.status)||error.code==='ol_maintenance'){await disconnect();status(error.message);}else status('El vídeo sigue conectado. Estamos reintentando la comprobación de acceso.');}}}
 if(info.mine&&!$('creator-form').contains(document.activeElement)){
  $('creator-category').value=info.mine.category||'entretenimiento';$('channel-title').value=info.mine.title;$('channel-bio').value=info.mine.bio;
 }
 }finally{refreshing=false;}
}
function renderCatalogue(){
 const list=$('live-channels');list.replaceChildren();
 const active=window.MaggySession.premium;
 const directory=active?info:publicInfo;
 const channels=directory?.video_ready?directory.channels:[];
 const rail=$('livis-channel-rail');if(rail){rail.replaceChildren();for(const channel of channels.slice(0,8)){const link=node('button');link.type='button';link.className='rail-channel';const avatar=node('span',channel.username.slice(0,2).toUpperCase());avatar.className='rail-channel-avatar';const label=node('span',channel.username),live=node('small','EN DIRECTO');link.append(avatar,label,live);link.addEventListener('click',()=>{if(window.MaggySession.premium)connect(channel,false);else navigateSection('#stream-access');});rail.append(link);}if(!channels.length)rail.append(node('p','Sin emisiones en este momento.'));}
 const query=$('channel-filter').value.trim().toLocaleLowerCase('es');
 const matches=channels.filter(channel=>(liveCategory==='all'||(liveCategory==='featured'?channel.featured:channel.category===liveCategory))&&[channel.title,channel.username,channel.bio].join(' ').toLocaleLowerCase('es').includes(query));
 document.querySelectorAll('[data-live-category]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.liveCategory===liveCategory)));
 $('channel-filter').disabled=!directory?.video_ready;
 $('catalogue-status').textContent=!directory?'Comprobando los canales de Ol Livis…':!directory.video_ready?'Las emisiones aún no están activadas. Las listas están preparadas para los canales reales.':`${matches.length} de ${channels.length} canales emitiendo ahora · actualización cada 30 segundos.${active?'':' Ver y comentar requiere Ol Livis Premium.'}`;
 $('live-empty').classList.toggle('hidden',matches.length>0);
 $('live-empty').textContent=!directory?.video_ready?'Todavía no hay vídeos de Ol Livis disponibles.':query||liveCategory!=='all'?'No hay emisiones que coincidan con esta lista o búsqueda en este momento.':!channels.length?'Nadie está emitiendo ahora. Puedes actualizar la lista o volver más tarde.':'';
 for(const channel of matches){
  const card=node('article');card.className='live-channel';card.id='canal-'+channel.id;
  const visual=node('div');visual.className='channel-video-cover';const image=node('img');image.src='/assets/ol-infinity.svg';image.alt='';const badge=node('span','EN DIRECTO · VÍDEO');badge.className='channel-live-badge';visual.append(image,badge);
  const button=node('button','Ver vídeo en directo');button.type='button';button.setAttribute('aria-label',`Ver vídeo en directo de ${channel.title}`);button.addEventListener('click',()=>{if(!window.MaggySession.premium){navigateSection('#stream-studio');return;}connect(channel,false);});
  const tags=node('div');tags.className='channel-tags';tags.append(node('span',categoryNames[channel.category]||'Entretenimiento'));if(channel.featured){const badge=node('span','Destacado');badge.className='featured-tag';tags.append(badge);}if(channel.founder_number){tags.append(founderBadge(channel.founder_number,channel.founder_signature||{}));}
  const subscribe=node('button','Suscripción y beneficios');subscribe.type='button';subscribe.className='secondary';subscribe.addEventListener('click',()=>openSubscription(channel.id));
  if(channel.subscribers_only)tags.append(node('span','Directo para suscriptores'));
  card.append(visual,tags,node('h3',channel.title),node('p',channel.username),node('p',channel.bio),node('p',(channel.subscriber_count||0)+' suscriptores activos'),button,subscribe);list.append(card);
 }
}
function focusSection(section,heading){section.classList.remove('hidden');section.scrollIntoView({behavior:'smooth',block:'start'});heading?.focus({preventScroll:true});}
function navigateSection(hash){
 if(hash==='#ol-live-premiere'||premiereOnly&&['#live-catalogue','#creator-panel','#stream-studio'].includes(hash)){const target=$('ol-live-premiere');target.tabIndex=-1;focusSection(target,target);return;}
 if(hash==='#video-setup'){if(info?.setup_checks){const heading=$('video-setup').querySelector('h2');heading.tabIndex=-1;focusSection($('video-setup'),heading);}return;}
 if(hash==='#live-catalogue'){renderCatalogue();focusSection($('live-catalogue'),$('catalogue-title'));return;}
 if(!['#creator-panel','#stream-studio'].includes(hash))return;
 if(!window.MaggySession.premium){$('stream-access').querySelector('a').href='/account?next='+encodeURIComponent('/live'+hash);focusSection($('stream-access'),$('stream-access').querySelector('h2'));return;}
 if(!info){status('No se pudo comprobar el acceso al estudio. Pulsa «Actualizar canales» para reintentar.');focusSection($('live-catalogue'),$('catalogue-title'));return;}
 if(!info.streamer_active){$('creator-access-message').textContent=info.streamer_sales_available?'Contrata Ol Livis por 25 € al año desde tu cuenta. Sin prueba gratuita; el acceso se activa cuando Stripe confirma el pago.':'Puedes ver los directos con tu acceso habitual cuando estén disponibles. Crear y emitir requiere el plan Ol Livis Creador; sus altas y cobros siguen bloqueados mientras se prepara el servicio.';focusSection($('creator-access'),$('creator-access-title'));return;}
 if(hash==='#creator-panel'||!info.mine){focusSection($('creator-panel'),$('creator-form-title'));return;}
 showStudio();
}
$('channel-filter').addEventListener('input',renderCatalogue);
document.querySelectorAll('[data-live-category]').forEach(button=>button.addEventListener('click',()=>{liveCategory=button.dataset.liveCategory;renderCatalogue();}));
$('refresh-channels').addEventListener('click',async()=>{
 const button=$('refresh-channels');button.disabled=true;
 try{await refresh();}
 catch(error){$('catalogue-status').textContent='No se pudo actualizar la lista. '+error.message;}
 finally{button.disabled=false;}
});
document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(!link||!['#live-catalogue','#creator-panel','#stream-studio'].includes(link.hash))return;event.preventDefault();history.pushState(null,'',link.hash);navigateSection(link.hash);});
window.addEventListener('hashchange',()=>navigateSection(location.hash));
window.addEventListener('popstate',()=>navigateSection(location.hash));
const community=new StreamCommunity();
let previewStream=null,previewGeneration=0;
function stopPreview(message='',all=false){
 tools.stopMeter();if(all)tools.stopScreen();
 previewGeneration+=1;if(previewStream)previewStream.getTracks().forEach(track=>track.stop());previewStream=null;
 $('preview-video').srcObject=null;$('preview-camera').disabled=false;$('preview-camera').textContent='Ver cámara y micrófono';$('close-preview').classList.add('hidden');
 if(message)$('studio-status').textContent=message;
}
function renderStudio(){
 document.body.classList.toggle('ol-stream-publishing',publishing);
 const allowed=Boolean(info?.mine&&info.streamer_active);
 $('stream-studio').classList.toggle('hidden',!allowed||publishing);
 if(!allowed){stopPreview('',true);return;}
 if(!tools.devicesInitialized){tools.devicesInitialized=true;tools.devices();}
 $('studio-title').textContent=`Tu estudio · ${info.mine.title}`;
 $('start-camera').disabled=!info.video_ready||connecting;
 $('studio-service-status').textContent=info.video_ready?'Cuando estés preparado, pulsa «Iniciar directo».':'Puedes preparar tu cámara en privado. Ol Livis aún no está disponible: comprueba la conexión con LiveKit arriba.';
}
function showStudio(){
 renderStudio();const target=publishing?$('live-stage'):$('stream-studio');
 target.classList.remove('hidden');target.scrollIntoView({behavior:'smooth',block:'start'});
 if(!publishing)$('studio-title').focus({preventScroll:true});
}
async function privatePreview(){
 if(connecting||publishing){$('studio-status').textContent='Espera a terminar la conexión antes de activar una cámara privada.';return;}
 if(!info?.mine||!info.streamer_active){$('studio-status').textContent='Guarda primero tu canal con una cuenta Ol Livis Creador activa.';return;}
 stopPreview();const generation=previewGeneration;$('preview-camera').disabled=true;$('preview-camera').textContent='Activando cámara…';$('close-preview').classList.remove('hidden');
 $('studio-status').textContent='Autoriza la cámara y el micrófono en el navegador. Esta vista es privada.';
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Abre electronicama mediante HTTPS en Safari, Chrome o Edge para usar la cámara.');
  const media=await navigator.mediaDevices.getUserMedia(tools.captureOptions());
  if(generation!==previewGeneration||!window.MaggySession.premium||!info.streamer_active){media.getTracks().forEach(track=>track.stop());return;}
  await tools.nativeQuality(media);previewStream=media;$('preview-video').srcObject=media;await $('preview-video').play();if(generation!==previewGeneration)return;
  $('studio-status').textContent='Cámara y micrófono preparados. Solo tú ves esta imagen; todavía no estás emitiendo.';
  $('preview-camera').textContent='Reiniciar cámara';tools.monitor(media);tools.devices();$('preview-mute').textContent='Silenciar micrófono privado';
 }catch(error){if(generation===previewGeneration){stopPreview();$('studio-status').textContent=error.name==='NotAllowedError'?'Permiso denegado. Autoriza la cámara y el micrófono desde el candado del navegador y vuelve a intentarlo.':error.name==='NotFoundError'?'No se encontró una cámara o un micrófono. Comprueba que estén conectados.':error.name==='NotReadableError'?'Otra aplicación está usando la cámara o el micrófono. Ciérrala y vuelve a intentarlo.':error.message;}}
 finally{if(generation===previewGeneration)$('preview-camera').disabled=false;}
}
async function sendPresence(current,generation){
 if(heartbeatBusy||room!==current||generation!==connectionGeneration||!publishing)return;
 heartbeatBusy=true;
 try{await api('/api/streamers/me/live',{live:true});if(room===current&&generation===connectionGeneration){if(!heartbeatVerified)status('Estás en directo. Conexión y listado comprobados.');heartbeatVerified=true;}}
 catch(error){if(room!==current||generation!==connectionGeneration)return;heartbeatVerified=false;if([401,402,403].includes(error.status)||error.code==='ol_maintenance'||error.code==='live_premiere'){await disconnect();status(error.message);}else status('El vídeo sigue conectado. Reintentando la verificación del directo; el tiempo aún no se acredita.');}
 finally{if(generation===connectionGeneration)heartbeatBusy=false;}
}
async function disconnect(){
 connectionGeneration+=1;heartbeatBusy=false;heartbeatVerified=false;community.stop();
 const wasPublisher=publishing;publishing=false;clearInterval(heartbeat);heartbeat=null;
 tools.liveEnded();const previous=room;room=null;selected=null;if(previous)await previous.disconnect();
 attachedTracks.clear();clearFounderStamp();$('live-media').replaceChildren();$('live-stage').classList.add('hidden');
 if(wasPublisher&&window.MaggySession.premium)try{await api('/api/streamers/me/live',{live:false});}catch{}
}
function attach(track,local=false){const key=track.sid||track;if(attachedTracks.has(key))return;const element=track.attach();attachedTracks.set(key,element);element.dataset.source=track.source||track.kind;if(track.source==='screen_share')element.classList.add('screen-track');element.autoplay=true;element.playbackRate=1;if(track.kind==='video'){element.playsInline=true;element.controls=false;}if(local)element.muted=true;if(track.kind==='audio'){element.controls=false;if(!local&&track.setPlayoutDelay)try{track.setPlayoutDelay(.1);}catch{}}$('live-media').append(element);}

async function connect(channel,publish){
 if(connecting)return;connecting=true;renderStudio();let generation;
 try{
  if(!info?.video_ready)throw new Error('Las emisiones todavía no están disponibles.');
  stopPreview('',true);await disconnect();generation=connectionGeneration;if(!window.MaggySession.premium)return;status('Conectando al directo…');$('studio-status').textContent='Conectando al directo…';$('start-camera').textContent='Conectando…';
  const data=await api(`/api/streamers/${encodeURIComponent(channel.id)}/token`,{publish});
  if(generation!==connectionGeneration||!window.MaggySession.premium)return;
  const LK=await sdk();if(generation!==connectionGeneration||!window.MaggySession.premium)return;room=new LK.Room({adaptiveStream:true,dynacast:true,...tools.roomOptions()});const current=room;
  room.on(LK.RoomEvent.TrackSubscribed,track=>{if(room===current)attach(track);});
  room.on(LK.RoomEvent.TrackUnsubscribed,track=>{attachedTracks.delete(track.sid||track);track.detach().forEach(element=>element.remove());});
  room.on(LK.RoomEvent.Disconnected,()=>{if(room===current){publishing=false;clearInterval(heartbeat);tools.liveEnded();community.stop();room=null;selected=null;heartbeatBusy=false;clearFounderStamp();$('live-stage').classList.add('hidden');renderStudio();status('La conexión con el directo ha terminado.');}});
  room.on(LK.RoomEvent.ConnectionStateChanged,state=>{if(room===current)tools.connectionState(state);});
  for(const event of [LK.RoomEvent.ParticipantConnected,LK.RoomEvent.ParticipantDisconnected])room.on(event,()=>{if(room===current)tools.participants(current);});
  if(publish){room.on(LK.RoomEvent.LocalTrackPublished,pub=>{if(pub.track&&room===current){attach(pub.track,true);if(pub.source===LK.Track.Source.Camera&&pub.track.mediaStreamTrack)tools.nativeQuality(new MediaStream([pub.track.mediaStreamTrack]));if(pub.source===LK.Track.Source.Microphone&&pub.track.mediaStreamTrack)tools.monitor(new MediaStream([pub.track.mediaStreamTrack]));if(pub.source===LK.Track.Source.ScreenShare)tools.screenState(true);}});room.on(LK.RoomEvent.LocalTrackUnpublished,pub=>{pub.track?.detach().forEach(element=>element.remove());if(pub.source===LK.Track.Source.ScreenShare)tools.screenState(false);});}
  await current.connect(data.url,data.token);if(generation!==connectionGeneration||!window.MaggySession.premium){await current.disconnect();return;}selected=channel;publishing=publish;
  if(publish){await current.localParticipant.enableCameraAndMicrophone();if(generation!==connectionGeneration||!window.MaggySession.premium){for(const pub of current.localParticipant.trackPublications.values())pub.track?.stop();await current.disconnect();return;}heartbeatVerified=false;await sendPresence(current,generation);if(generation!==connectionGeneration||room!==current)return;heartbeat=setInterval(()=>sendPresence(current,generation),25000);}
  $('live-catalogue').before($('live-stage'));const stamp=$('live-founder-stamp');stamp.replaceChildren();if(channel.founder_number)stamp.append(founderBadge(channel.founder_number,channel.founder_signature||{}));tools.liveConnected(current);community.start(channel,publish);$('leave-room').textContent=publish?'Finalizar directo':'Salir del directo';$('stage-title').textContent=channel.title;$('live-stage').classList.remove('hidden');
  $('toggle-camera').classList.toggle('hidden',!publish);$('toggle-mic').classList.toggle('hidden',!publish);
  $('toggle-camera').textContent='Apagar cámara';$('toggle-mic').textContent='Silenciar micrófono';
  renderStudio();status(publish?(heartbeatVerified?'Estás en directo.':'Vídeo conectado. La verificación del listado se reintentará sin cortar la emisión.'):'Conectado al directo. Pulsa «Activar sonido» si no lo escuchas.');$('live-stage').scrollIntoView({behavior:'smooth'});
 }catch(error){if(generation===undefined||generation===connectionGeneration){await disconnect();const message=error.name==='NotAllowedError'?'Autoriza la cámara y el micrófono para emitir.':error.message||'No se pudo iniciar el directo.';status(message);$('studio-status').textContent=message;if(publish&&info?.mine)showStudio();else{$('catalogue-status').textContent=message;focusSection($('live-catalogue'),$('catalogue-title'));}}}finally{connecting=false;$('start-camera').textContent='Iniciar directo';renderStudio();}
}
$('check-video').addEventListener('click',async()=>{const button=$('check-video');button.disabled=true;$('video-check-status').textContent='Comprobando conexión…';try{const r=await window.MaggySession.fetch('/api/streamers/admin/check-video',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await r.json();$('video-check-status').textContent=data.message||data.error||'No se pudo comprobar la conexión.';}catch{$('video-check-status').textContent='No se pudo conectar. Vuelve a intentarlo.';}finally{button.disabled=false;}});
function creatorStatus(message,error=false){const el=$('creator-status');el.textContent=message;el.className='creator-status '+(error?'error':'success');if(error){el.focus({preventScroll:true});el.scrollIntoView({behavior:'smooth',block:'center'});}}
$('creator-form').addEventListener('invalid',event=>{creatorStatus(event.target.id==='channel-title'?'Escribe un título de al menos 3 caracteres.':event.target.validationMessage||'Revisa los datos del formulario.',true);},true);
$('creator-form').addEventListener('submit',async event=>{
 event.preventDefault();
 const button=$('save-channel');button.disabled=true;button.textContent='Guardando…';creatorStatus('Guardando tu canal…');
 try{const saved=await api('/api/streamers/me',{title:$('channel-title').value,category:$('creator-category').value,bio:$('channel-bio').value});
 info.mine=saved.channel;window.dispatchEvent(new Event('ol:channel-saved'));creatorStatus('Canal guardado. Ya puedes entrar al estudio.');status('Canal guardado.');showStudio();
 refresh().catch(()=>{$('studio-service-status').textContent='Tu canal se ha guardado, pero no se pudo actualizar la conexión. Puedes usar la vista privada de cámara y reintentar después.';});
 }catch(error){creatorStatus(error.message+' Tus datos siguen en el formulario.',true);status(error.message);}
 finally{button.disabled=false;button.textContent='Guardar y entrar al estudio';}
});
$('preview-camera').addEventListener('click',privatePreview);
$('close-preview').addEventListener('click',()=>stopPreview('Vista privada apagada. La cámara, el micrófono y la pantalla están cerrados.',true));
$('start-camera').addEventListener('click',()=>{if(info?.mine)connect(info.mine,true);});
$('leave-room').addEventListener('click',async()=>{const wasPublisher=publishing;await disconnect();status('Has salido del directo.');try{await refresh();}catch(error){status(error.message);}if(wasPublisher&&info?.mine)showStudio();else navigateSection('#live-catalogue');});
$('enable-sound').addEventListener('click',()=>room?.startAudio().catch(()=>status('No se pudo activar el sonido.')));
$('toggle-camera').addEventListener('click',async()=>{if(!publishing||!room)return;const enable=!room.localParticipant.isCameraEnabled;try{await room.localParticipant.setCameraEnabled(enable);$('toggle-camera').textContent=enable?'Apagar cámara':'Encender cámara';}catch{status('No se pudo cambiar la cámara.');}});
$('toggle-mic').addEventListener('click',async()=>{if(!publishing||!room)return;const enable=!room.localParticipant.isMicrophoneEnabled;try{await room.localParticipant.setMicrophoneEnabled(enable);tools.syncRoomMic(room);community.syncMicrophone(enable);$('toggle-mic').textContent=enable?'Silenciar micrófono':'Activar micrófono';}catch{status('No se pudo cambiar el micrófono.');}});
window.addEventListener('maggy:access-changed',event=>{if(!event.detail.premium){stopPreview('',true);$('stream-studio').classList.add('hidden');disconnect();$('creator-panel').classList.add('hidden');renderCatalogue();$('stream-access').classList.remove('hidden');}});
window.addEventListener('pagehide',()=>{community.stop();stopPreview('',true);if(publishing)window.MaggySession.fetch('/api/streamers/me/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({live:false}),keepalive:true}).catch(()=>{});room?.disconnect();});
await window.MaggySession.ready;
$('stream-access').classList.toggle('hidden',window.MaggySession.premium);
if(window.MaggySession.premium){try{await refresh();status(info?.video_ready?'Elige un directo o prepara tu canal.':'Zona preparada; las emisiones y las altas de Ol Livis aún no están disponibles.');navigateSection(location.hash);}catch(error){status(error.message);}}
else{try{await refresh();}catch(error){$('catalogue-status').textContent=error.message;}status('Explora Ol Livis. Para ver o emitir necesitas acceso premium.');const hash=/^#canal-[a-f0-9]{32}$/.test(location.hash)||['#live-catalogue','#creator-panel','#stream-studio'].includes(location.hash)?location.hash:'#live-catalogue';$('stream-access').querySelector('a').href='/account?next='+encodeURIComponent('/live'+hash);}
if(window.MaggySession.premium&&/^#canal-[a-f0-9]{32}$/.test(location.hash)){const card=document.getElementById(location.hash.slice(1));if(card)card.scrollIntoView({behavior:'smooth'});else status('Este canal no está en directo ahora. Vuelve a abrir el enlace cuando comience la emisión.');}
renderCatalogue();
setInterval(()=>refresh().catch(error=>status(error.message)),30000);
