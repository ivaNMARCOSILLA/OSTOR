/* The server decides registration access; the client only explains and checks it. */
(()=>{
 'use strict';
 if(window.OlRegistrationFee)return;
 const nativeFetch=window.fetch.bind(window),PRICE=100,CURRENCY='eur';
 let currentId=null,currentCsrf='',state=null,blocked=false,verified=false,host=null,ui=null;
 let refreshRevision=0,refreshController=null,queued=null,countdownTimer=null,remaining=0,countdownStarted=0,lastExpiryCheck=-Infinity;
 let checkoutBusy=false,reconciling=false,checkoutRevision=0,checkoutController=null,reconcileController=null,loggingOut=false;
 let processingReturn=new URLSearchParams(location.search).get('registration_fee')==='processing',returnUntil=processingReturn?performance.now()+120000:0,returnTimer=null;
 const make=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(className)node.className=className;return node;};
 const translate=text=>text?(window.OlLocale?.t?.(text)||text):'';
 const say=(text,error=false)=>{if(ui){ui.status.textContent=text;ui.status.classList.toggle('registration-fee-error',error);}};
 const isDue=value=>value?.enabled===true&&value.required===true&&value.exempt!==true&&value.paid!==true&&Boolean(value.deadline)&&value.in_grace!==true;
 const validPrice=value=>value?.price_cents===PRICE&&value.currency===CURRENCY;
 const youtubeOrigin=url=>url.protocol==='https:'&&['www.youtube.com','www.youtube-nocookie.com','youtube.com','youtube-nocookie.com'].includes(url.hostname)&&!url.username&&!url.password;
 function youtubeFrames(){
  return [...document.querySelectorAll('iframe[src]')].flatMap(frame=>{try{const url=new URL(frame.src,location.href);return youtubeOrigin(url)?[{frame,origin:url.origin}]:[];}catch{return [];}});
 }
 function pauseMedia(){
  for(const element of document.querySelectorAll('audio,video'))try{element.pause();}catch{}
  for(const {frame,origin} of youtubeFrames())try{frame.contentWindow?.postMessage(JSON.stringify({event:'command',func:'pauseVideo',args:[]}),origin);}catch{}
 }
 function setBlocked(value){
  const was=blocked;blocked=Boolean(value);document.documentElement.classList.toggle('registration-fee-due',blocked);
  if(blocked&&!was)pauseMedia();
 }
 function stopCountdown(){if(countdownTimer!==null){clearInterval(countdownTimer);countdownTimer=null;}}
 function stopReturnChecks(){if(returnTimer!==null){clearTimeout(returnTimer);returnTimer=null;}}
 function invalidateCheckout(){checkoutRevision++;checkoutController?.abort();reconcileController?.abort();checkoutController=null;reconcileController=null;checkoutBusy=false;reconciling=false;}
 function hide(){
  stopCountdown();stopReturnChecks();setBlocked(false);verified=false;state=null;
  invalidateCheckout();if(ui){ui.terms.checked=false;ui.status.textContent='';ui.status.classList.remove('registration-fee-error');ui.form.removeAttribute('aria-busy');}
  if(host)host.hidden=true;
 }
 function findHost(){
  if(host?.isConnected)return;
  host=document.getElementById('registration-payment');
  if(!host){
   host=make('section',undefined,'registration-payment');host.id='registration-payment';host.hidden=true;
   const header=document.querySelector('.content>.topbar,.account-shell>header');
   if(header)header.after(host);
   else{
    const content=document.querySelector('.platform-content,main.account-shell,main,.content,.account-shell');
    if(content)content.prepend(host);else document.body.prepend(host);
   }
  }
  host.classList.add('registration-payment');host.setAttribute('aria-labelledby','registration-payment-title');
  const title=make('h2','Alta de tu cuenta');title.id='registration-payment-title';
  const copy=make('p');copy.id='registration-fee-copy';
  const countdown=make('p',undefined,'registration-fee-countdown');countdown.id='registration-fee-countdown';countdown.setAttribute('aria-live','off');
  const status=make('p',undefined,'registration-fee-status');status.id='registration-fee-status';status.setAttribute('role','status');status.setAttribute('aria-live','polite');
  const returned=make('p',undefined,'registration-fee-return');returned.id='registration-fee-return';returned.hidden=true;
  const form=make('form',undefined,'registration-fee-form');form.id='registration-fee-form';form.noValidate=true;
  const label=make('label',undefined,'registration-fee-consent'),terms=make('input');terms.type='checkbox';terms.id='registration-fee-terms';terms.name='fee_terms';terms.required=true;terms.addEventListener('change',()=>terms.setCustomValidity(''));
  label.append(terms,make('span','Acepto el alta de mi cuenta por 1 € en un pago único.'));
  const submit=make('button','Pagar el alta · 1 €');submit.id='registration-fee-submit';submit.type='submit';
  const note=make('p','El alta de 1 € es independiente del acceso anual a Ol Live.','registration-fee-note');form.append(label,submit,note);
  const actions=make('nav',undefined,'registration-fee-actions');actions.setAttribute('aria-label','Opciones de la cuenta');
  const account=make('a','Mi cuenta');account.href='/account#profile-settings';
  const legal=make('a','Condiciones');legal.href='/legal/aviso-legal.html';
  const privacy=make('a','Privacidad');privacy.href='/legal/privacidad.html';
  const retry=make('button','Comprobar estado','secondary');retry.id='registration-fee-refresh';retry.type='button';retry.addEventListener('click',()=>refresh());
  const reconcile=make('button','Ya he pagado · comprobar','secondary');reconcile.id='registration-fee-reconcile';reconcile.type='button';reconcile.addEventListener('click',reconcilePayment);
  const logout=make('button','Cerrar sesión','secondary');logout.id='registration-fee-logout';logout.type='button';logout.addEventListener('click',logoutAccount);
  actions.append(account,legal,privacy,retry,reconcile,logout);host.replaceChildren(title,copy,countdown,form,status,returned,actions);
  ui={title,copy,countdown,status,returned,form,terms,submit,retry,reconcile,logout};form.addEventListener('submit',checkout);
 }
 function controls(){
  if(!ui)return;
  ui.form.hidden=!blocked;ui.countdown.hidden=blocked||state?.in_grace!==true;
  ui.terms.disabled=checkoutBusy||reconciling||loggingOut;
  ui.submit.disabled=!blocked||!verified||state?.payment_available!==true||!validPrice(state)||checkoutBusy||reconciling||loggingOut;
  ui.submit.textContent=checkoutBusy?'Abriendo Stripe…':'Pagar el alta · 1 €';
  ui.form.setAttribute('aria-busy',checkoutBusy||reconciling?'true':'false');ui.logout.disabled=loggingOut;ui.retry.disabled=checkoutBusy||reconciling||loggingOut;
  ui.reconcile.hidden=!blocked;ui.reconcile.disabled=checkoutBusy||reconciling||loggingOut;ui.reconcile.textContent=reconciling?'Comprobando pago…':'Ya he pagado · comprobar';
 }
 function scheduleReturnCheck(){
  stopReturnChecks();
  if(processingReturn&&currentId&&state?.enabled===true&&state.paid!==true&&state.exempt!==true&&performance.now()<returnUntil&&!document.hidden){
   returnTimer=setTimeout(()=>{returnTimer=null;refresh();},3000);
  }
 }
 function updateCountdown(){
  if(!ui||!state?.in_grace||host.hidden)return;
  const seconds=Math.max(0,Math.ceil(remaining-(performance.now()-countdownStarted)/1000));
  const value=seconds?String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0'):'Comprobando el estado del alta…';
  if(ui.countdown.textContent!==value)ui.countdown.textContent=value;
  if(seconds===0&&performance.now()-lastExpiryCheck>2000){lastExpiryCheck=performance.now();queueRefresh();}
 }
 function secondsRemaining(value){
  if(typeof value.grace_seconds==='number'&&Number.isFinite(value.grace_seconds))return Math.max(0,Math.min(300,value.grace_seconds));
  const deadline=Date.parse(value.deadline),server=Date.parse(value.server_now);
  return Number.isFinite(deadline)&&Number.isFinite(server)?Math.max(0,Math.min(300,(deadline-server)/1000)):0;
 }
 function apply(snapshot){
  const user=snapshot.account?.user;
  if(!user?.id){currentId=null;currentCsrf='';hide();return;}
  if(currentId!==String(user.id)){hide();currentId=String(user.id);}
  currentCsrf=typeof snapshot.account.csrf==='string'?snapshot.account.csrf:'';
  const next=snapshot.fee;
  if(!next||next.enabled!==true||next.required!==true||next.exempt===true||next.paid===true){hide();return;}
  findHost();state=next;verified=true;host.hidden=false;
  const due=isDue(next);setBlocked(due);host.classList.toggle('registration-payment--due',due);host.classList.toggle('registration-payment--grace',!due);
  ui.title.textContent=due?'Confirma el alta de tu cuenta · 1 €':'Tu cuenta · 5 minutos de prueba';
  ui.copy.textContent=due?'El tiempo de prueba ha terminado. Para continuar con esta cuenta, el alta cuesta 1 € en un pago único.':'Tu cuenta tiene 5 minutos de prueba. Después, el alta cuesta 1 € (pago único).';
  stopCountdown();
  if(!due){ui.terms.checked=false;if(next.in_grace===true){remaining=secondsRemaining(next);countdownStarted=performance.now();updateCountdown();countdownTimer=setInterval(updateCountdown,1000);}else{ui.copy.textContent='El periodo de prueba se activa al completar el acceso a tu cuenta. Después, el alta cuesta 1 € en un pago único.';ui.countdown.textContent='';}say('');}
  else if(!validPrice(next))say('No se ha podido verificar el importe del alta. Vuelve a comprobar el estado de tu cuenta.',true);
  else if(next.payment_available!==true)say('El pago de alta todavía no está disponible. Puedes revisar tu cuenta, cerrar sesión o consultar las condiciones.');
  else if(!checkoutBusy)say('El pago se inicia únicamente cuando aceptas las condiciones y pulsas el botón.');
  ui.returned.hidden=!processingReturn;
  if(processingReturn)ui.returned.textContent='Estamos comprobando la confirmación del alta. Volver de Stripe no confirma el pago.';
  controls();scheduleReturnCheck();
 }
 async function json(path,options={},controller=new AbortController()){
  const timer=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await nativeFetch(path,{cache:'no-store',credentials:'same-origin',...options,signal:controller.signal});
   let data;try{data=await response.json();}catch{throw new Error('No se ha podido leer el estado del alta. Inténtalo de nuevo.');}
   if(!response.ok){const error=new Error(data&&typeof data.error==='string'?data.error:'No se ha podido comprobar el alta de la cuenta.');error.status=response.status;throw error;}
   return data;
  }catch(error){
   if(error.name==='AbortError'){const failure=new Error('La conexión tarda demasiado. No se confirma ningún pago desde esta pantalla.');failure.aborted=true;throw failure;}
   if(error instanceof TypeError)throw new Error('No se ha podido conectar con el servicio. No se confirma ningún pago desde esta pantalla.');
   throw error;
  }finally{clearTimeout(timer);}
 }
 async function readSnapshot(controller){
  const account=await json('/api/account/me',{},controller);
  if(!account?.user?.id)return {account,fee:null};
  const fee=await json('/api/account/registration-fee',{},controller);return {account,fee};
 }
 async function refresh(){
  if(checkoutBusy||reconciling||loggingOut)return null;
  const revision=++refreshRevision;refreshController?.abort();const controller=new AbortController();refreshController=controller;
  try{
   const snapshot=await readSnapshot(controller);if(revision!==refreshRevision)return null;apply(snapshot);return snapshot;
  }catch(error){
   if(revision!==refreshRevision)return null;
   if([401,403,404,405].includes(error.status)){currentId=null;currentCsrf='';hide();return null;}
   verified=false;if(ui&&!host.hidden){say(error.message,true);controls();}scheduleReturnCheck();return null;
  }
 }
 function queueRefresh(){if(queued!==null)return;queued=setTimeout(()=>{queued=null;refresh();},80);}
 async function checkout(event){
  event.preventDefault();if(checkoutBusy||reconciling||loggingOut||!blocked||!verified)return;
  if(state?.payment_available!==true||!validPrice(state)){say('El pago de alta todavía no está disponible.',true);return;}
  ui.terms.setCustomValidity(ui.terms.checked?'':translate('Confirma que aceptas el alta por 1 € en un pago único.'));
  if(!ui.form.reportValidity())return;
  refreshRevision++;refreshController?.abort();
  const owner=currentId,attempt=++checkoutRevision;checkoutController?.abort();const controller=new AbortController();checkoutController=controller;
  checkoutBusy=true;controls();say('Comprobando tu cuenta antes de abrir el pago único…');let navigating=false;
  try{
   const snapshot=await readSnapshot(controller);if(attempt!==checkoutRevision)return;
   apply(snapshot);
   if(attempt!==checkoutRevision||owner!==currentId||!blocked||!verified||!ui.terms.checked)return;
   if(state.payment_available!==true||!validPrice(state)||!currentCsrf)throw new Error('El pago de alta no está disponible para esta cuenta en este momento.');
   const data=await json('/api/account/registration-fee/checkout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':currentCsrf},body:JSON.stringify({fee_terms:true})},controller);
   if(attempt!==checkoutRevision||owner!==currentId)return;
   let target;try{target=new URL(data.url);}catch{throw new Error('No se ha podido confirmar un enlace de pago válido de Stripe.');}
   if(target.protocol!=='https:'||target.hostname!=='checkout.stripe.com'||target.username||target.password||target.port)throw new Error('El enlace de pago recibido no pertenece al checkout seguro de Stripe.');
   say('Abriendo el alta de 1 € en Stripe…');window.location.assign(target.href);navigating=true;
  }catch(error){if(attempt===checkoutRevision)say(error.message||'No se ha podido abrir el pago del alta.',true);}
  finally{if(attempt===checkoutRevision&&!navigating){checkoutBusy=false;controls();}}
 }
 async function reconcilePayment(){
  if(checkoutBusy||reconciling||loggingOut||!currentId||!blocked)return;
  refreshRevision++;refreshController?.abort();
  const owner=currentId,attempt=++checkoutRevision,controller=new AbortController();reconcileController=controller;reconciling=true;controls();say('Comprobando si el alta ya tiene un pago confirmado…');
  try{
   const account=await json('/api/account/me',{},controller);
   if(attempt!==checkoutRevision)return;
   if(String(account?.user?.id||'')!==owner||typeof account?.csrf!=='string'||!account.csrf)throw new Error('La sesión ha cambiado. Vuelve a comprobar el estado de tu cuenta.');
   await json('/api/account/registration-fee/reconcile',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':account.csrf},body:'{}'},controller);
   if(attempt!==checkoutRevision)return;
   const snapshot=await readSnapshot(controller);if(attempt!==checkoutRevision)return;
   apply(snapshot);
   if(attempt===checkoutRevision&&ui&&!host.hidden)say('Todavía no consta una confirmación del alta. Si acabas de pagar, puedes volver a comprobarlo.');
   if(snapshot.fee?.paid===true)window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}));
  }catch(error){if(attempt===checkoutRevision)say(error.message||'No se ha podido comprobar el pago del alta.',true);}
  finally{if(attempt===checkoutRevision){reconciling=false;controls();}}
 }
 async function logoutAccount(){
  if(loggingOut)return;refreshRevision++;refreshController?.abort();invalidateCheckout();loggingOut=true;controls();
  try{
   const account=await json('/api/account/me');if(typeof account?.csrf!=='string'||!account.csrf)throw new Error('No se ha podido verificar la sesión. Inténtalo de nuevo.');
   await json('/api/account/logout',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':account.csrf},body:'{}'});
   currentId=null;currentCsrf='';hide();window.dispatchEvent(new CustomEvent('ol:interface-update',{detail:{public:true,account:true}}));window.dispatchEvent(new Event('ol:account-refreshed'));
  }catch(error){say(error.message||'No se ha podido cerrar la sesión.',true);}
  finally{loggingOut=false;controls();}
 }
 function localApi(input){
  try{const raw=typeof input==='string'||input instanceof URL?input:input?.url;const url=new URL(raw,location.href);return url.origin===location.origin&&url.pathname.startsWith('/api/');}catch{return false;}
 }
 window.fetch=async function(input,options){
  const response=await nativeFetch(input,options);
  if(response.status===402&&localApi(input))response.clone().json().then(data=>{if(data?.code==='registration_fee_required'){pauseMedia();queueRefresh();}}).catch(()=>{});
  return response;
 };
 document.addEventListener('play',event=>{if(blocked&&event.target?.matches?.('audio,video'))try{event.target.pause();}catch{};},true);
 window.addEventListener('message',event=>{
  if(!blocked)return;let data=event.data;if(typeof data==='string'){try{data=JSON.parse(data);}catch{return;}}
  if(data?.info!==1&&data?.info?.playerState!==1)return;
  for(const {frame,origin} of youtubeFrames())if(origin===event.origin&&frame.contentWindow===event.source){pauseMedia();break;}
 });
 for(const event of ['focus','ol:account-refreshed'])window.addEventListener(event,queueRefresh);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)queueRefresh();});
 window.addEventListener('pageshow',event=>{if(event.persisted){invalidateCheckout();if(ui)ui.terms.checked=false;queueRefresh();}});
 window.addEventListener('pagehide',()=>{invalidateCheckout();refreshRevision++;refreshController?.abort();stopReturnChecks();if(queued!==null){clearTimeout(queued);queued=null;}});
 setInterval(()=>{if(!document.hidden)refresh();},30000);
 window.OlRegistrationFee={refresh,get blocked(){return blocked;}};
 const returned=new URLSearchParams(location.search).get('registration_fee');
 if(returned==='cancelled')processingReturn=false;
 refresh();
})();
