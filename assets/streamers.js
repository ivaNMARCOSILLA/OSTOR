'use strict';
import {StudioTools} from '/assets/studio-tools.js?v=9.0.0';
const $=id=>document.getElementById(id);
let info=null,room=null,selected=null,publishing=false,heartbeat=null,sdkPromise=null,connecting=false,connectionGeneration=0,giftRevision=0;
const status=text=>{$('stream-status').textContent=text;};
async function api(path,data){
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),18000);
 try{const r=await window.MaggySession.fetch(path,{signal:controller.signal,...(data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})});
 let json;try{json=await r.json();}catch{throw new Error('El servidor no devolvió una respuesta válida. Vuelve a intentarlo.');}
 if(!r.ok)throw new Error(json.error||'No se pudo completar la operación.');return json;
 }catch(error){if(error.name==='AbortError')throw new Error('El servidor tarda en responder. Vuelve a intentarlo.');throw error;}finally{clearTimeout(timer);}
}
function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
const tools=new StudioTools({getRoom:()=>publishing?room:null,getPreview:()=>previewStream,getChannel:()=>room&&selected?selected:info?.mine,restartPreview:()=>privatePreview(),canPreview:()=>!connecting&&!publishing&&Boolean(info?.mine&&info.streamer_active),report:message=>{status(message);$(room?'live-tools-status':'studio-status').textContent=message;}});
async function sdk(){if(window.LivekitClient)return window.LivekitClient;if(!sdkPromise)sdkPromise=new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='/assets/vendor/livekit-client-2.23.0.umd.js';s.onload=()=>resolve(window.LivekitClient);s.onerror=()=>reject(new Error('No se pudo cargar el reproductor de directos.'));document.head.append(s);});return sdkPromise;}
async function refresh(){
 if(!window.MaggySession.active)return;
 info=await api('/api/streamers');
 $('stream-unavailable').classList.toggle('hidden',info.video_ready);
 $('video-setup').classList.toggle('hidden',!info.setup_checks);
 if(info.setup_checks){$('open-video-preview').classList.toggle('hidden',info.setup_environment!=='production');$('setup-environment').textContent=info.setup_environment==='production'?'Estás en electronicama.com. Las claves guardadas solo en Preview no activan el vídeo de esta web principal. Usa la vista previa para comprobarlas.':info.setup_environment==='preview'?'Estás en la vista previa de pruebas. Los cobros siguen bloqueados durante la comprobación.':'Estudio local de pruebas.';const list=$('video-checks');list.replaceChildren();for(const [name,ok] of Object.entries(info.setup_checks))list.append(node('li',`${name}: ${ok?'correcto':'pendiente de corregir'}`));}
 $('creator-panel').classList.toggle('hidden',!info.streamer_active);
 $('live-catalogue').classList.toggle('hidden',!info.video_ready);
 renderStudio();
 if(room&&!publishing&&selected&&!info.channels.some(channel=>channel.id===selected.id)){await disconnect();status('El directo ha terminado.');}
 if(info.mine&&!$('creator-form').contains(document.activeElement)){
  $('channel-title').value=info.mine.title;$('channel-bio').value=info.mine.bio;$('creator-paypal').value=info.mine.paypal_url;
 }
 const list=$('live-channels');list.replaceChildren();$('live-empty').classList.toggle('hidden',Boolean(info.channels.length));
 for(const channel of info.channels){const card=node('article');card.className='live-channel';card.id='canal-'+channel.id;const image=node('img');image.src='/assets/app-icon-192.png';image.alt='Logo de Ol';const button=node('button','Ver directo');button.type='button';button.addEventListener('click',()=>connect(channel,false));card.append(image,node('h3',channel.title),node('p',channel.username),node('p',channel.bio),button);list.append(card);}
}
let previewStream=null,previewGeneration=0;
function stopPreview(message='',all=false){
 tools.stopMeter();if(all)tools.stopScreen();
 previewGeneration+=1;if(previewStream)previewStream.getTracks().forEach(track=>track.stop());previewStream=null;
 $('preview-video').srcObject=null;$('preview-camera').disabled=false;$('preview-camera').textContent='Ver cámara y micrófono';$('close-preview').classList.add('hidden');
 if(message)$('studio-status').textContent=message;
}
function renderStudio(){
 const allowed=Boolean(info?.mine&&info.streamer_active);
 $('stream-studio').classList.toggle('hidden',!allowed||publishing);
 if(!allowed){stopPreview('',true);return;}
 if(!tools.devicesInitialized){tools.devicesInitialized=true;tools.devices();}
 $('studio-title').textContent=`Tu estudio · ${info.mine.title}`;
 $('start-camera').disabled=!info.video_ready||connecting;
 $('studio-service-status').textContent=info.video_ready?'Cuando estés preparado, pulsa «Iniciar directo».':'Puedes preparar tu cámara en privado. La emisión aún no está disponible: comprueba la conexión con LiveKit arriba.';
}
function showStudio(){
 renderStudio();const target=publishing?$('live-stage'):$('stream-studio');
 target.classList.remove('hidden');target.scrollIntoView({behavior:'smooth',block:'start'});
 if(!publishing)$('studio-title').focus({preventScroll:true});
}
async function privatePreview(){
 if(connecting||publishing){$('studio-status').textContent='Espera a terminar la conexión antes de activar una cámara privada.';return;}
 if(!info?.mine||!info.streamer_active){$('studio-status').textContent='Guarda primero tu canal con una cuenta Streamer activa.';return;}
 stopPreview();const generation=previewGeneration;$('preview-camera').disabled=true;$('preview-camera').textContent='Activando cámara…';$('close-preview').classList.remove('hidden');
 $('studio-status').textContent='Autoriza la cámara y el micrófono en el navegador. Esta vista es privada.';
 try{
  if(!navigator.mediaDevices?.getUserMedia)throw new Error('Abre Ol mediante HTTPS en Safari, Chrome o Edge para usar la cámara.');
  const media=await navigator.mediaDevices.getUserMedia(tools.captureOptions());
  if(generation!==previewGeneration||!window.MaggySession.active||!info.streamer_active){media.getTracks().forEach(track=>track.stop());return;}
  previewStream=media;$('preview-video').srcObject=media;await $('preview-video').play();if(generation!==previewGeneration)return;
  $('studio-status').textContent='Cámara y micrófono preparados. Solo tú ves esta imagen; todavía no estás emitiendo.';
  $('preview-camera').textContent='Reiniciar cámara';tools.monitor(media);tools.devices();$('preview-mute').textContent='Silenciar micrófono privado';
 }catch(error){if(generation===previewGeneration){stopPreview();$('studio-status').textContent=error.name==='NotAllowedError'?'Permiso denegado. Autoriza la cámara y el micrófono desde el candado del navegador y vuelve a intentarlo.':error.name==='NotFoundError'?'No se encontró una cámara o un micrófono. Comprueba que estén conectados.':error.name==='NotReadableError'?'Otra aplicación está usando la cámara o el micrófono. Ciérrala y vuelve a intentarlo.':error.message;}}
 finally{if(generation===previewGeneration)$('preview-camera').disabled=false;}
}
async function disconnect(){
 connectionGeneration+=1;
 const wasPublisher=publishing;publishing=false;clearInterval(heartbeat);heartbeat=null;
 tools.liveEnded();const previous=room;room=null;selected=null;if(previous)await previous.disconnect();
 $('live-media').replaceChildren();$('live-stage').classList.add('hidden');$('gift-link').classList.add('hidden');
 if(wasPublisher&&window.MaggySession.active)try{await api('/api/streamers/me/live',{live:false});}catch{}
}
function attach(track,local=false){const element=track.attach();if(track.source==='screen_share')element.classList.add('screen-track');element.autoplay=true;if(track.kind==='video'){element.playsInline=true;element.controls=!local;}if(local)element.muted=true;if(track.kind==='audio')element.controls=true;$('live-media').append(element);}
async function connect(channel,publish){
 if(connecting)return;connecting=true;renderStudio();let generation;
 try{
  if(!info?.video_ready)throw new Error('Las emisiones todavía no están disponibles.');
  stopPreview('',true);await disconnect();generation=connectionGeneration;if(!window.MaggySession.active)return;status('Conectando al directo…');$('studio-status').textContent='Conectando al directo…';$('start-camera').textContent='Conectando…';
  const data=await api(`/api/streamers/${encodeURIComponent(channel.id)}/token`,{publish});
  if(generation!==connectionGeneration||!window.MaggySession.active)return;
  const LK=await sdk();if(generation!==connectionGeneration||!window.MaggySession.active)return;room=new LK.Room({adaptiveStream:true,dynacast:true,...tools.roomOptions()});const current=room;
  room.on(LK.RoomEvent.TrackSubscribed,track=>{if(room===current)attach(track);});
  room.on(LK.RoomEvent.TrackUnsubscribed,track=>track.detach().forEach(element=>element.remove()));
  room.on(LK.RoomEvent.Disconnected,()=>{if(room===current){publishing=false;clearInterval(heartbeat);tools.liveEnded();$('live-stage').classList.add('hidden');status('La emisión ha terminado.');}});
  room.on(LK.RoomEvent.ConnectionStateChanged,state=>{if(room===current)tools.connectionState(state);});
  for(const event of [LK.RoomEvent.ParticipantConnected,LK.RoomEvent.ParticipantDisconnected])room.on(event,()=>{if(room===current)tools.participants(current);});
  if(publish){room.on(LK.RoomEvent.LocalTrackPublished,pub=>{if(pub.track&&room===current){attach(pub.track,true);if(pub.source===LK.Track.Source.Microphone&&pub.track.mediaStreamTrack)tools.monitor(new MediaStream([pub.track.mediaStreamTrack]));if(pub.source===LK.Track.Source.ScreenShare)tools.screenState(true);}});room.on(LK.RoomEvent.LocalTrackUnpublished,pub=>{pub.track?.detach().forEach(element=>element.remove());if(pub.source===LK.Track.Source.ScreenShare)tools.screenState(false);});}
  await current.connect(data.url,data.token);if(generation!==connectionGeneration||!window.MaggySession.active){await current.disconnect();return;}selected=channel;publishing=publish;
  if(publish){await current.localParticipant.enableCameraAndMicrophone();if(generation!==connectionGeneration||!window.MaggySession.active){for(const pub of current.localParticipant.trackPublications.values())pub.track?.stop();await current.disconnect();return;}await api('/api/streamers/me/live',{live:true});heartbeat=setInterval(()=>api('/api/streamers/me/live',{live:true}).catch(async error=>{await disconnect();status(error.message);}),25000);}
  tools.liveConnected(current);$('leave-room').textContent=publish?'Finalizar directo':'Salir del directo';$('stage-title').textContent=channel.title;$('live-stage').classList.remove('hidden');
  $('toggle-camera').classList.toggle('hidden',!publish);$('toggle-mic').classList.toggle('hidden',!publish);
  $('toggle-camera').textContent='Apagar cámara';$('toggle-mic').textContent='Silenciar micrófono';
  $('gift-panel').classList.toggle('hidden',publish||!channel.paypal_url);$('gift-link').classList.add('hidden');$('gift-status').textContent='';
  renderStudio();status(publish?'Estás en directo.':'Conectado al directo. Pulsa «Activar sonido» si no lo escuchas.');$('live-stage').scrollIntoView({behavior:'smooth'});
 }catch(error){if(generation===undefined||generation===connectionGeneration){await disconnect();const message=error.name==='NotAllowedError'?'Autoriza la cámara y el micrófono para emitir.':error.message||'No se pudo iniciar el directo.';status(message);$('studio-status').textContent=message;if(info?.mine)showStudio();}}finally{connecting=false;$('start-camera').textContent='Iniciar directo';renderStudio();}
}
$('check-video').addEventListener('click',async()=>{const button=$('check-video');button.disabled=true;$('video-check-status').textContent='Comprobando conexión…';try{const r=await window.MaggySession.fetch('/api/streamers/admin/check-video',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await r.json();$('video-check-status').textContent=data.message||data.error||'No se pudo comprobar la conexión.';}catch{$('video-check-status').textContent='No se pudo conectar. Vuelve a intentarlo.';}finally{button.disabled=false;}});
function creatorStatus(message,error=false){const el=$('creator-status');el.textContent=message;el.className='creator-status '+(error?'error':'success');if(error){el.focus({preventScroll:true});el.scrollIntoView({behavior:'smooth',block:'center'});}}
$('creator-form').addEventListener('invalid',event=>{creatorStatus(event.target.id==='channel-title'?'Escribe un título de al menos 3 caracteres.':event.target.validationMessage||'Revisa los datos del formulario.',true);},true);
$('creator-form').addEventListener('submit',async event=>{
 event.preventDefault();
 if($('creator-paypal').value.trim()&&!$('owns-paypal').checked){creatorStatus('Marca la casilla que confirma que el enlace de PayPal te pertenece, o deja el enlace vacío para guardar sin regalos.',true);return;}
 const button=$('save-channel');button.disabled=true;button.textContent='Guardando…';creatorStatus('Guardando tu canal…');
 try{const saved=await api('/api/streamers/me',{title:$('channel-title').value,bio:$('channel-bio').value,paypal_url:$('creator-paypal').value,owns_paypal:$('owns-paypal').checked});
 info.mine=saved.channel;creatorStatus('Canal guardado. Ya puedes entrar al estudio.');status('Canal guardado.');showStudio();
 refresh().catch(()=>{$('studio-service-status').textContent='Tu canal se ha guardado, pero no se pudo actualizar la conexión. Puedes usar la vista privada de cámara y reintentar después.';});
 }catch(error){creatorStatus(error.message+' Tus datos siguen en el formulario.',true);status(error.message);}
 finally{button.disabled=false;button.textContent='Guardar y entrar al estudio';}
});
$('preview-camera').addEventListener('click',privatePreview);
$('close-preview').addEventListener('click',()=>stopPreview('Vista privada apagada. La cámara, el micrófono y la pantalla están cerrados.',true));
$('start-camera').addEventListener('click',()=>{if(info?.mine)connect(info.mine,true);});
$('leave-room').addEventListener('click',async()=>{await disconnect();status('Has salido del directo.');await refresh();if(info?.mine)showStudio();});
$('enable-sound').addEventListener('click',()=>room?.startAudio().catch(()=>status('No se pudo activar el sonido.')));
$('toggle-camera').addEventListener('click',async()=>{if(!publishing||!room)return;const enable=!room.localParticipant.isCameraEnabled;try{await room.localParticipant.setCameraEnabled(enable);$('toggle-camera').textContent=enable?'Apagar cámara':'Encender cámara';}catch{status('No se pudo cambiar la cámara.');}});
$('toggle-mic').addEventListener('click',async()=>{if(!publishing||!room)return;const enable=!room.localParticipant.isMicrophoneEnabled;try{await room.localParticipant.setMicrophoneEnabled(enable);tools.syncRoomMic(room);$('toggle-mic').textContent=enable?'Silenciar micrófono':'Activar micrófono';}catch{status('No se pudo cambiar el micrófono.');}});
$('gift-amount').addEventListener('input',()=>{giftRevision+=1;$('gift-link').classList.add('hidden');$('gift-status').textContent='';});
$('gift-form').addEventListener('submit',async event=>{event.preventDefault();$('gift-link').classList.add('hidden');try{const channelId=selected?.id,generation=connectionGeneration,revision=giftRevision;if(!channelId)throw new Error('Elige un directo.');const amount=$('gift-amount').value;if(!/^\d+(?:[.,]\d{1,2})?$/.test(amount))throw new Error('Utiliza como máximo dos decimales.');const cents=Math.round(Number(amount.replace(',','.'))*100);const result=await api(`/api/streamers/${encodeURIComponent(channelId)}/gift-link`,{amount_cents:cents});if(channelId!==selected?.id||generation!==connectionGeneration||revision!==giftRevision)return;$('gift-link').href=result.url;$('gift-link').textContent=`Enviar ${(result.amount_cents/100).toFixed(2)} € en PayPal ↗`;$('gift-link').classList.remove('hidden');$('gift-status').textContent=`Para ${result.creator}. Comisión de Ol: 0 €. Revisa el destinatario en PayPal antes de confirmar.`;}catch(error){$('gift-status').textContent=error.message;}});
window.addEventListener('maggy:access-changed',event=>{if(!event.detail.active){stopPreview('',true);$('stream-studio').classList.add('hidden');disconnect();$('creator-panel').classList.add('hidden');$('live-catalogue').classList.add('hidden');$('stream-access').classList.remove('hidden');}});
window.addEventListener('pagehide',()=>{stopPreview('',true);if(publishing)window.MaggySession.fetch('/api/streamers/me/live',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({live:false}),keepalive:true}).catch(()=>{});room?.disconnect();});
await window.MaggySession.ready;
$('stream-access').classList.toggle('hidden',window.MaggySession.active);
if(window.MaggySession.active){try{await refresh();status(info.video_ready?'Elige un directo o prepara tu canal.':'Zona preparada; las emisiones y las altas de streamer aún no están disponibles.');if(location.hash==='#stream-studio'&&info.mine)showStudio();}catch(error){status(error.message);}}
else{status('Inicia sesión para acceder a los directos.');const hash=/^#canal-[a-f0-9]{32}$/.test(location.hash)?location.hash:'#stream-studio';$('stream-access').querySelector('a').href='/account?next='+encodeURIComponent('/streamers'+hash);}
if(window.MaggySession.active&&/^#canal-[a-f0-9]{32}$/.test(location.hash)){const card=document.getElementById(location.hash.slice(1));if(card)card.scrollIntoView({behavior:'smooth'});else status('Este canal no está en directo ahora. Vuelve a abrir el enlace cuando comience la emisión.');}
setInterval(()=>{if(window.MaggySession.active)refresh().catch(error=>status(error.message));},30000);
