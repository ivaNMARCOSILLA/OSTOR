/* Recent activity estimate. No names, addresses, or browsing history are published. */
(()=>{
 const counter=document.querySelector('[data-online-counter]');if(!counter)return;
 const permitted=()=>{try{return localStorage.getItem('electronicama_visit_registry_consent_v1')==='accepted'&&!navigator.globalPrivacyControl&&navigator.doNotTrack!=='1';}catch{return false;}};
 let token='',busy=false;
 async function tick(){
  const playing=[...document.querySelectorAll('audio,video')].some(m=>!m.paused&&!m.ended);
  if(!permitted()){counter.textContent='';return;}if(busy||(document.hidden&&!playing))return;busy=true;
  try{
   await(window.MaggySession?.ready||window.OlAccountReady);
   if(!token){const r=await fetch('/api/account/me',{cache:'no-store'});if(!r.ok)throw Error();token=(await r.json()).csrf;}
   const r=await fetch('/api/presence',{method:'POST',headers:{'X-CSRF-Token':token,'Content-Type':'application/json'},body:JSON.stringify({consent:true})});
   if(!r.ok){if(r.status===403)token='';throw Error();}
   const d=await r.json();if(typeof d.total!=='number'){counter.textContent='';return;}counter.textContent=`${d.total.toLocaleString('es-ES')} en línea · ${d.members} con cuenta · ${d.guests} visitantes`;
   counter.title='Estimación de actividad en los últimos 90 segundos. Una cuenta en varios dispositivos cuenta una vez; los visitantes se cuentan por navegador.';
  }catch{counter.textContent='En línea · conexión pendiente';}finally{busy=false;}
 }
 window.addEventListener('electronicama:navigation-consent',()=>tick());window.addEventListener('storage',()=>tick());
 tick();setInterval(tick,30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});
})();
