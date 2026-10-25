/* Real account progress: one server clock, shared safely across open devices. */
const panel=document.getElementById('ol-collection');
if(panel){
 const $=id=>document.getElementById(id);let csrf='',active=false,lastActivity=Date.now(),busy=false,initialized=false,owned=[],lastUnlocked=-1;
 async function api(path,data){const response=await fetch(path,{headers:{'Content-Type':'application/json',...(data?{'X-CSRF-Token':csrf}:{})},...(data?{method:'POST',body:JSON.stringify(data)}:{})});const result=await response.json();if(!response.ok)throw new Error(result.error||'No se pudo actualizar tu colección.');return result;}
 function render(data){$('reward-points').textContent=data.points.toLocaleString('es-ES');$('reward-time').textContent=data.minutes<60?`${data.minutes} min`:`${Math.floor(data.minutes/60)} h ${data.minutes%60} min`;$('reward-level').textContent=data.level;$('reward-count').textContent=`${data.unlocked}/${data.total}`;
  const next=data.next_sticker;const previous=[...data.stickers].reverse().find(s=>s.unlocked);const from=(previous?.minutes||0)*60,to=(next?.minutes||0)*60;
  $('reward-progress').max=Math.max(1,to-from);$('reward-progress').value=next?Math.max(0,data.active_seconds-from):1;
  $('reward-next').textContent=next?`Próximo: ${next.name} · faltan ${Math.max(1,Math.ceil((to-data.active_seconds)/60))} min activos.`:'¡Colección completa! Sigue disfrutando y aumentando tu nivel.';
  const fresh=lastUnlocked>=0&&data.unlocked>lastUnlocked;lastUnlocked=data.unlocked;
  $('reward-status').textContent=fresh?'¡Nuevo sticker desbloqueado! Ya puedes usarlo en los comentarios.':'Tu progreso se guarda en tu cuenta. El tiempo simultáneo en varias pestañas cuenta una sola vez.';
  owned=data.stickers.filter(s=>s.unlocked);window.OlCollection={stickers:owned};window.dispatchEvent(new CustomEvent('ol:collection',{detail:{stickers:owned}}));
  const grid=$('reward-album');grid.replaceChildren();for(const sticker of data.stickers){const card=document.createElement('article');card.className='collection-sticker'+(sticker.unlocked?' unlocked':' locked');const image=document.createElement('img');image.src=sticker.image;image.alt=sticker.name;image.width=96;image.height=96;image.loading='lazy';const name=document.createElement('strong');name.textContent=`N.º ${sticker.number} · ${sticker.name}`;const info=document.createElement('small');info.textContent=sticker.unlocked?(sticker.points===0?'Gratuito · en tu colección':'En tu colección'):`${sticker.points.toLocaleString('es-ES')} puntos · ${sticker.minutes<60?sticker.minutes+' min':Math.floor(sticker.minutes/60)+' h'+(sticker.minutes%60?' '+sticker.minutes%60+' min':'')}`;card.append(image,name,info);grid.append(card);}
 }
 function openCollection(){panel.open=true;panel.scrollIntoView({behavior:'smooth',block:'start'});}
 document.addEventListener('click',event=>{const link=event.target.closest('a[href="#ol-collection"]');if(link)openCollection();});if(location.hash==='#ol-collection')openCollection();
 async function inspect(){try{await (window.MaggySession?.ready||window.OlAccountReady);const account=await api('/api/account/me');csrf=account.csrf;active=Boolean(account.user?.active);$('reward-access').classList.toggle('hidden',active);$('reward-content').classList.toggle('hidden',!active);if(active){render(await api('/api/rewards'));if(!initialized){initialized=true;await heartbeat();}}else{initialized=false;owned=[];window.OlCollection={stickers:[]};window.dispatchEvent(new CustomEvent('ol:collection',{detail:{stickers:[]}}));$('reward-status').textContent='Entra con acceso activo para guardar tu tiempo y conseguir stickers.';}}catch{$('reward-status').textContent='No se pudo comprobar tu colección. Vuelve a actualizar.';}}
 function usingOl(){const playing=[...document.querySelectorAll('audio,video')].some(media=>!media.paused&&!media.ended&&media.currentTime>0);return playing||(!document.hidden&&Date.now()-lastActivity<300000);}
 async function heartbeat(){if(!active||busy||!usingOl())return;busy=true;try{render(await api('/api/rewards/heartbeat',{}));}catch(error){$('reward-status').textContent=error.message;}finally{busy=false;}}
 for(const event of ['pointerdown','keydown','scroll'])document.addEventListener(event,e=>{if(e.isTrusted)lastActivity=Date.now();},{passive:true});
 $('refresh-rewards').addEventListener('click',()=>{lastActivity=Date.now();inspect();});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden){lastActivity=Date.now();inspect();}});
 window.addEventListener('ol:designs-updated',()=>inspect());
 window.addEventListener('maggy:access-changed',()=>inspect());setInterval(heartbeat,30000);setInterval(inspect,60000);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',inspect,{once:true});else inspect();
}
