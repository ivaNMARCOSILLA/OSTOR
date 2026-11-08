import {playStickerSound,mountStickerVoiceControls} from '/assets/sticker-audio.js?v=9.29.7';
import {decorateSticker} from '/assets/sticker-scenes.js?v=9.29.7';
/* Account collection: paginated artwork, bounded active-time rewards. */
const panel=document.getElementById('ol-collection');
if(panel){
 mountStickerVoiceControls(panel);
 const $=id=>document.getElementById(id);let csrf='',active=false,lastActivity=Date.now(),busy=false,initialized=false,lastUnlocked=-1,page=1,pages=1,viewRevision=0,searchTimer;
 let stickerCards=new Map(),collectionSignature='';
 const desiredText=new WeakMap();
 const setText=(node,value)=>{if(desiredText.get(node)===value)return;desiredText.set(node,value);if(node.textContent!==value)node.textContent=value;};
 function publishCollection(stickers,total){const signature=JSON.stringify([stickers,total]);if(signature===collectionSignature)return;collectionSignature=signature;window.OlCollection={stickers,total};window.dispatchEvent(new CustomEvent('ol:collection',{detail:window.OlCollection}));}
 function placeCards(parent,cards){let cursor=parent.firstElementChild;for(const card of cards){if(card===cursor)cursor=cursor.nextElementSibling;else parent.insertBefore(card,cursor);}while(cursor){const next=cursor.nextElementSibling;cursor.remove();cursor=next;}}
 function renderAlbum(stickers){
  const grid=$('reward-album'),nextCards=new Map(),cards=[];
  for(const sticker of stickers){let record=stickerCards.get(sticker.id);if(!record){const card=document.createElement('article'),image=document.createElement('img'),name=document.createElement('strong'),info=document.createElement('small'),series=document.createElement('small'),sound=document.createElement('button');decorateSticker(card,sticker.id);image.width=96;image.height=96;image.loading='lazy';sound.type='button';sound.className='sticker-sound-button';sound.textContent='♪ Escuchar frase';record={card,image,name,info,series,sound,sticker,signature:''};sound.addEventListener('click',()=>playStickerSound(record.sticker.id,sound,record.sticker.phrase));card.append(image,name,series,info,sound);}
   const signature=JSON.stringify([sticker.id,sticker.number,sticker.name,sticker.image,sticker.unlocked,sticker.points,sticker.minutes,sticker.series,sticker.phrase]);
   if(signature!==record.signature){record.signature=signature;record.sticker=sticker;record.card.className='collection-sticker'+(sticker.unlocked?' unlocked':' locked');if(record.image.getAttribute('src')!==sticker.image)record.image.src=sticker.image;if(record.image.alt!==sticker.name)record.image.alt=sticker.name;setText(record.name,`N.º ${sticker.number} · ${sticker.name}`);setText(record.info,sticker.unlocked?(sticker.points===0?'Gratuito · en tu colección':'En tu colección'):`${sticker.points.toLocaleString('es-ES')} puntos · ${sticker.minutes<60?sticker.minutes+' min':Math.floor(sticker.minutes/60)+' h'+(sticker.minutes%60?' '+sticker.minutes%60+' min':'')}`);setText(record.series,sticker.series);if(record.sound.title!==sticker.phrase)record.sound.title=sticker.phrase;const label='Escuchar frase de '+sticker.name;if(record.sound.getAttribute('aria-label')!==label)record.sound.setAttribute('aria-label',label);}
   nextCards.set(sticker.id,record);cards.push(record.card);
  }
  if(!cards.length){let empty=grid.querySelector('p');if(!empty){empty=document.createElement('p');empty.textContent='No hay stickers que coincidan con esta búsqueda.';}cards.push(empty);}
  placeCards(grid,cards);stickerCards=nextCards;
 }
 const options=()=>new URLSearchParams({page:String(page),q:$('reward-search').value.trim(),series:$('reward-series').value,owned:$('reward-owned').checked?'1':'0'});
 async function api(path,data){const response=await fetch(path,{headers:{'Content-Type':'application/json',...(data?{'X-CSRF-Token':csrf}:{})},...(data?{method:'POST',body:JSON.stringify(data)}:{})});const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo actualizar tu colección.');return result;}
 function render(data){
  page=data.page;pages=data.pages;setText($('reward-points'),data.points.toLocaleString('es-ES'));setText($('reward-time'),data.minutes<60?`${data.minutes} min`:`${Math.floor(data.minutes/60)} h ${data.minutes%60} min`);setText($('reward-level'),String(data.level));setText($('reward-count'),`${data.unlocked}/${data.total}`);
  const next=data.next_sticker,from=data.last_milestone_minutes*60,to=(next?.minutes||0)*60;const progress=$('reward-progress'),maximum=Math.max(1,to-from),value=next?Math.max(0,data.active_seconds-from):1;if(progress.max!==maximum)progress.max=maximum;if(progress.value!==value)progress.value=value;
  setText($('reward-next'),next?`Próximo: ${next.name} · faltan ${Math.max(1,Math.ceil((to-data.active_seconds)/60))} min activos.`:'¡Colección completa! Sigue disfrutando y aumentando tu nivel.');
  const fresh=lastUnlocked>=0&&data.unlocked>lastUnlocked;lastUnlocked=data.unlocked;setText($('reward-status'),fresh?'¡Nuevo sticker desbloqueado! Ya puedes usarlo en los comentarios.':'Tu progreso se guarda en tu cuenta. El tiempo simultáneo en varias pestañas cuenta una sola vez.');
  publishCollection(data.owned_preview,data.unlocked);
  const current=$('reward-series').value,signature=data.series.join('|');if($('reward-series').dataset.values!==signature){$('reward-series').replaceChildren(new Option('Todas las colecciones',''));for(const series of data.series)$('reward-series').append(new Option(series,series));$('reward-series').value=current;$('reward-series').dataset.values=signature;}
  setText($('reward-page'),`Página ${page} de ${pages} · ${data.filtered_total} stickers`);if($('reward-prev').disabled!==(page<=1))$('reward-prev').disabled=page<=1;if($('reward-next-page').disabled!==(page>=pages))$('reward-next-page').disabled=page>=pages;
  renderAlbum(data.stickers);
 }
 async function loadView(){const revision=++viewRevision;try{const data=await api('/api/rewards?'+options());if(revision===viewRevision)render(data);}catch(error){$('reward-status').textContent=error.message;}}
 function openCollection(){panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'});}
 document.addEventListener('click',event=>{const link=event.target.closest('a[href="#ol-collection"]');if(link)openCollection();});if(location.hash==='#ol-collection')openCollection();
 async function inspect(){try{await(window.MaggySession?.ready||window.OlAccountReady);const account=await api('/api/account/me');csrf=account.csrf;active=Boolean(account.user);$('reward-access').classList.toggle('hidden',active);$('reward-content').classList.toggle('hidden',!active);if(active){await loadView();if(!initialized){initialized=true;await heartbeat();}}else{initialized=false;publishCollection([],0);$('reward-status').textContent='Crea una cuenta gratuita para guardar tu tiempo y conseguir stickers.';}}catch{$('reward-status').textContent='No se pudo comprobar tu colección. Vuelve a actualizar.';}}
 function usingOl(){const playing=[...document.querySelectorAll('audio,video')].some(media=>!media.paused&&!media.ended&&media.currentTime>0);return playing||(!document.hidden&&Date.now()-lastActivity<300000);}
 async function heartbeat(){if(!active||busy||!usingOl())return;busy=true;const revision=viewRevision;try{const data=await api('/api/rewards/heartbeat?'+options(),{});if(revision===viewRevision)render(data);}catch(error){$('reward-status').textContent=error.message;}finally{busy=false;}}
 for(const event of ['pointerdown','keydown','scroll'])document.addEventListener(event,e=>{if(e.isTrusted)lastActivity=Date.now();},{passive:true});
 $('reward-prev').addEventListener('click',()=>{page=Math.max(1,page-1);loadView();});$('reward-next-page').addEventListener('click',()=>{page=Math.min(pages,page+1);loadView();});
 $('reward-search').addEventListener('input',()=>{clearTimeout(searchTimer);page=1;viewRevision+=1;searchTimer=setTimeout(loadView,300);});$('reward-series').addEventListener('change',()=>{page=1;loadView();});$('reward-owned').addEventListener('change',()=>{page=1;loadView();});
 $('refresh-rewards').addEventListener('click',()=>{lastActivity=Date.now();inspect();});document.addEventListener('visibilitychange',()=>{if(!document.hidden){lastActivity=Date.now();inspect();}});window.addEventListener('ol:designs-updated',()=>inspect());window.addEventListener('maggy:access-changed',()=>inspect());setInterval(heartbeat,30000);setInterval(inspect,60000);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',inspect,{once:true});else inspect();
}
