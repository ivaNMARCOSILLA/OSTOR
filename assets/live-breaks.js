/* A local reminder only: never pause media, change permissions, or disconnect a room. */
(()=>{
 const panel=document.getElementById('live-break-reminder');if(!panel)return;let active=false,publisher=false,due=0,started=0;
 const minute=60000;
 function inspect(){if(!active||document.hidden||Date.now()<due||!panel.classList.contains('hidden'))return;const elapsed=Math.floor((Date.now()-started)/minute);document.getElementById('live-break-copy').textContent=`Llevas ${elapsed} minutos ${publisher?'emitiendo':'en el directo'}. Puedes descansar la vista, moverte un poco y volver cuando quieras.`;panel.classList.remove('hidden');}
 function postpone(minutes){panel.classList.add('hidden');due=Date.now()+minutes*minute;}
 window.addEventListener('ol:live-session',event=>{active=Boolean(event.detail?.connected);panel.classList.add('hidden');if(active){publisher=Boolean(event.detail.publisher);started=Date.now();due=started+120*minute;}else{due=0;started=0;}});
 document.getElementById('live-break-snooze').addEventListener('click',()=>postpone(240));document.getElementById('live-break-dismiss').addEventListener('click',()=>postpone(240));document.addEventListener('visibilitychange',inspect);setInterval(inspect,30000);
})();
