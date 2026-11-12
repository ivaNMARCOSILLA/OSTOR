/* Voluntary, one-time contributions: checkout starts only after a confirmed click. */
(()=>{
 'use strict';
 const panel=document.getElementById('contributions');
 if(!panel)return;
 const find=id=>panel.querySelector('#'+id);
 const form=find('contributions-form'),amount=find('contribution-amount'),terms=find('contribution-terms'),submit=find('contribution-submit'),status=find('contribution-status');
 if(!form||!amount||!terms||!submit||!status)return;
 const presets=[...panel.querySelectorAll('[data-contribution-cents]')];
 const normalSubmit=submit.textContent||'Continuar a Stripe';
 let available=false,busy=false,min=100,max=50000,configurationRevision=0,configurationController=null;
 const retry=document.createElement('button');retry.type='button';retry.id='contribution-retry-config';retry.className='secondary contribution-retry';retry.textContent='Volver a comprobar';retry.hidden=true;status.after(retry);
 form.noValidate=true;
 function tell(message,error=false){status.textContent=message;status.classList.toggle('contribution-error',error);}
 function cents(raw){
  const text=String(raw??'').trim();
  if(text.length>10||!/^\d+(?:[.,]\d{1,2})?$/.test(text))return null;
  const [integer,fraction='']=text.split(/[.,]/),whole=integer.replace(/^0+(?=\d)/,'');
  if(whole.length>3)return null;
  // Only whole-number cents enter the request; decimal text is never parsed as a float.
  const result=Number(whole)*100+Number(fraction.padEnd(2,'0'));
  return Number.isSafeInteger(result)?result:null;
 }
 function decimal(value){
  const whole=Math.floor(value/100),fraction=String(value%100).padStart(2,'0');
  return fraction==='00'?String(whole):String(whole)+','+fraction;
 }
 function selected(){
  const value=cents(amount.value);
  for(const button of presets)button.setAttribute('aria-pressed',value===Number(button.dataset.contributionCents)?'true':'false');
 }
 function controls(){
  amount.disabled=busy;terms.disabled=busy;submit.disabled=busy||!available;retry.disabled=busy;
  for(const button of presets){const value=Number(button.dataset.contributionCents);button.disabled=busy||!available||!Number.isSafeInteger(value)||value<min||value>max;}
  form.setAttribute('aria-busy',busy?'true':'false');submit.textContent=busy?'Abriendo Stripe…':normalSubmit;
 }
 async function json(path,options={},controller=new AbortController()){
  const timer=setTimeout(()=>controller.abort(),15000);
  try{
   const response=await fetch(path,{cache:'no-store',credentials:'same-origin',...options,signal:controller.signal});
   let data;try{data=await response.json();}catch{throw new Error('No se ha podido leer la respuesta. Inténtalo de nuevo.');}
   if(!response.ok){const error=new Error(data&&typeof data.error==='string'?data.error:'No se ha podido abrir Stripe. No se confirma ningún pago desde esta pantalla.');error.status=response.status;throw error;}
   return data;
  }catch(error){
   if(error.name==='AbortError'){const failure=new Error('La conexión tarda demasiado. No se confirma ningún pago desde esta pantalla. Puedes volver a intentarlo.');failure.aborted=true;throw failure;}
   if(error instanceof TypeError)throw new Error('No se ha podido conectar con el servicio de pago. No se confirma ningún pago desde esta pantalla. Puedes volver a intentarlo.');
   throw error;
  }finally{clearTimeout(timer);}
 }
 async function configuration(){
  if(busy)return;
  const revision=++configurationRevision;configurationController?.abort();const controller=new AbortController();configurationController=controller;
  available=false;retry.hidden=true;controls();tell('Comprobando disponibilidad…');
  try{
   const data=await json('/api/contributions/config',{},controller);
   if(revision!==configurationRevision)return;
   const low=data.min_amount_cents,high=data.max_amount_cents;
   const valid=data.currency==='eur'&&Number.isSafeInteger(low)&&Number.isSafeInteger(high)&&low>=100&&high<=50000&&low<=high&&data.one_time!==false&&data.grants_access!==true;
   if(!data.available||!valid){tell('Las aportaciones no están disponibles en este momento. Puedes seguir disfrutando de electronicama.');retry.hidden=false;return;}
   min=low;max=high;available=true;
   amount.placeholder='Entre '+decimal(min)+' y '+decimal(max)+' €';
   tell('Aportación voluntaria y de pago único. No activa Ol Live.');
  }catch(error){
   if(revision!==configurationRevision)return;
   tell('No se ha podido comprobar la disponibilidad de las aportaciones. Vuelve a intentarlo.',true);retry.hidden=false;
  }finally{if(revision===configurationRevision)controls();}
 }
 for(const button of presets)button.addEventListener('click',()=>{
  if(busy||!available)return;
  const value=Number(button.dataset.contributionCents);if(!Number.isSafeInteger(value)||value<min||value>max)return;
  amount.value=decimal(value);amount.setCustomValidity('');selected();
 });
 amount.addEventListener('input',()=>{amount.setCustomValidity('');selected();});
 retry.addEventListener('click',configuration);
 form.addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;
  if(!available){tell('Las aportaciones no están disponibles en este momento.',true);return;}
  const value=cents(amount.value);
  const validation=value===null?'Escribe una cantidad en euros con una coma o un punto y hasta dos decimales.':value<min||value>max?'Elige una cantidad entre '+decimal(min)+' y '+decimal(max)+' €.':'';
  amount.setCustomValidity(validation?(window.OlLocale?.t(validation)||validation):'');
  if(!form.reportValidity()){
   tell(value===null||value<min||value>max?'Revisa la cantidad de tu aportación.':'Confirma que es una aportación voluntaria y de pago único.',true);return;
  }
  if(!terms.checked){tell('Confirma que es una aportación voluntaria y de pago único.',true);return;}
  busy=true;controls();tell('Preparando una aportación única de '+decimal(value)+' €…');
  let navigating=false;
  try{
   const account=await json('/api/account/me');
   if(typeof account?.csrf!=='string'||!account.csrf)throw new Error('No se ha podido verificar la sesión. Recarga la página antes de continuar.');
   const checkout=await json('/api/contributions/checkout',{
    method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':account.csrf},
    body:JSON.stringify({amount_cents:value,contributions_terms:true})
   });
   let destination;try{destination=new URL(checkout.url);}catch{throw new Error('No se ha podido confirmar un enlace de pago válido de Stripe.');}
   if(destination.protocol!=='https:'||destination.hostname!=='checkout.stripe.com'||destination.port||destination.username||destination.password){
    throw new Error('El enlace de pago recibido no pertenece al checkout seguro de Stripe.');
   }
   tell('Abriendo el pago único en Stripe…');window.location.assign(destination.href);navigating=true;
  }catch(error){
   if(error.status===503){available=false;retry.hidden=false;}
   tell(error.message||'No se ha podido abrir Stripe. Puedes volver a intentarlo.',true);
  }finally{
   if(!navigating){busy=false;controls();if(document.activeElement===document.body)submit.focus({preventScroll:true});}
  }
 });
 const returned=find('contribution-return'),result=new URLSearchParams(location.search).get('contribution');
 if(returned&&['processing','received','cancelled'].includes(result)){
  returned.hidden=false;
  returned.textContent=result==='cancelled'?'Has vuelto sin continuar en Stripe. Si realizaste un pago, comprueba su justificante.':'Has vuelto de Stripe. El pago se confirma en su justificante.';
 }
 window.addEventListener('pageshow',event=>{
  if(!event.persisted)return;
  busy=false;available=false;terms.checked=false;amount.setCustomValidity('');selected();controls();configuration();
 });
 selected();configuration();
})();
