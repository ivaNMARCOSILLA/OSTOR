/* Recent activity estimate. No names, addresses, or browsing history are published. */
(()=>{
 const counter=document.querySelector('[data-online-counter]');if(!counter)return;
 let token='',busy=false;
 async function tick(){
  const playing=[...document.querySelectorAll('audio,video')].some(m=>!m.paused&&!m.ended);
  if(busy||(document.hidden&&!playing))return;busy=true;
  try{
   await(window.MaggySession?.ready||window.OlAccountReady);
   if(!token){const r=await fetch('/api/account/me',{cache:'no-store'});if(!r.ok)throw Error();token=(await r.json()).csrf;}
   const r=await fetch('/api/presence',{method:'POST',headers:{'X-CSRF-Token':token}});
   if(!r.ok){if(r.status===403)token='';throw Error();}
   const d=await r.json();counter.textContent=`${d.total.toLocaleString('es-ES')} en línea · ${d.members} con cuenta · ${d.guests} visitantes`;
   counter.title='Estimación de actividad en los últimos 90 segundos. Una cuenta en varios dispositivos cuenta una vez; los visitantes se cuentan por navegador.';
  }catch{counter.textContent='En línea · conexión pendiente';}finally{busy=false;}
 }
 tick();setInterval(tick,30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
})();
