/* A blocked member must leave an already open page instead of becoming a guest. */
(()=>{
 'use strict';
 const nativeFetch=window.fetch.bind(window);
 let blocked=false,authenticated=false,interval=null,polling=false;
 function stopPolling(){if(interval!==null){window.clearInterval(interval);interval=null;}}
 function leave(){
  if(blocked)return;
  blocked=true;authenticated=false;stopPolling();
  document.querySelectorAll('audio,video').forEach(media=>{try{media.pause();}catch{}});
  window.dispatchEvent(new CustomEvent('electronicama:account-blocked'));
  window.location.replace('/account?blocked=1');
 }
 async function inspect(){
  if(blocked||!authenticated||document.hidden||polling)return;
  polling=true;
  const controller=new AbortController(),timeout=window.setTimeout(()=>controller.abort(),10000);
  try{await window.fetch('/api/account/me',{cache:'no-store',signal:controller.signal});}
  catch{/* A network failure does not mean that the account was blocked. */}
  finally{window.clearTimeout(timeout);polling=false;}
 }
 window.fetch=async function(input,options){
  const response=await nativeFetch(input,options);
  let url;
  try{url=new URL(typeof input==='string'||input instanceof URL?input:input.url,window.location.href);}catch{return response;}
  if(url.origin!==window.location.origin)return response;
  if(response.status===403){
   try{if((await response.clone().json()).code==='account_blocked')leave();}catch{}
  }else if(url.pathname==='/api/account/me'&&response.ok&&!blocked){
   try{
    authenticated=Boolean((await response.clone().json()).user?.id);
    if(authenticated&&interval===null)interval=window.setInterval(inspect,60000);
    else if(!authenticated)stopPolling();
   }catch{}
  }
  return response;
 };
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)inspect();});
 window.addEventListener('pageshow',event=>{if(event.persisted)inspect();});
})();
