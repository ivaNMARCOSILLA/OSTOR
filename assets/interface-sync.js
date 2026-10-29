/* Cross-device changes: small server revisions, no page reload or overlapping polls. */
(()=>{
 let versions=null,busy=false,timer=null,stopped=false,failures=0;
 async function check(){
  clearTimeout(timer);if(stopped)return;
  if(document.hidden||!navigator.onLine){timer=setTimeout(check,15000);return;}
  if(busy)return;busy=true;
  try{
   const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),8000);let response;try{response=await fetch('/api/sync',{cache:'no-store',signal:controller.signal});}finally{clearTimeout(deadline);}
   if(!response.ok)throw Error('sync');const next=await response.json();failures=0;
   const changed={public:versions===null||next.public!==versions.public,account:versions===null||next.account!==versions.account};versions=next;
   if(changed.public||changed.account)window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:changed}));
  }catch{failures=Math.min(failures+1,4);}finally{busy=false;if(!stopped)timer=setTimeout(check,Math.min(30000,3000*2**failures)+Math.random()*350);}
 }
 for(const event of ['focus','online'])window.addEventListener(event,check);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)check();});
 window.addEventListener('pagehide',()=>{stopped=true;clearTimeout(timer);});window.addEventListener('pageshow',()=>{stopped=false;check();});
 check();
})();
