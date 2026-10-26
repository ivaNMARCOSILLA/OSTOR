/* Optional project introduction; aggregate actions, no third-party advertising. */
(()=>{
 const panel=document.getElementById('ol-intro');if(!panel)return;
 const $=id=>document.getElementById(id),key='ol_intro_bueno_v1';let step=0;
 try{if(localStorage.getItem(key)){panel.classList.add('hidden');return;}}catch{}
 const slides=[['Ol Live, tu mejor momento.','Música gratuita, directos y comunidad. Descubre Ol a tu ritmo.'],['Tres meses para sentirlo.','Cuando el vídeo esté disponible, activa tres meses de prueba. Después, si quieres continuar: 25 € en un único pago.'],['Crea Ol del bueno.','Las 100 primeras plazas de creador se conservan con actividad real. Una insignia, tu espacio y buenos momentos para compartir.']];
 async function event(name){try{await(window.MaggySession?.ready||Promise.resolve());const r=await fetch('/api/account/me');if(!r.ok)return;const d=await r.json();await fetch('/api/promotion/event',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':d.csrf},body:JSON.stringify({event:name})});}catch{}}
 function finish(name){event(name);try{localStorage.setItem(key,'done');}catch{}panel.classList.add('hidden');document.getElementById('search-input')?.focus({preventScroll:true});}
 $('intro-next').addEventListener('click',()=>{if(step===2){finish('complete');return;}event('next');step++;$('ol-intro-title').textContent=slides[step][0];$('ol-intro-copy').textContent=slides[step][1];$('intro-position').textContent=(step+1)+' / 3';$('intro-next').textContent=step===2?'Terminar':'Siguiente';$('intro-start').classList.toggle('hidden',step!==2);$('intro-feedback').textContent=slides[step][0];});
 $('intro-skip').addEventListener('click',()=>finish('skip'));
 $('intro-start').addEventListener('click',()=>finish('complete'));event('shown');
})();
