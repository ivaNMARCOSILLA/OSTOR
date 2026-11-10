/* A few loose floral accents share the page flow, outside live controls. */
(()=>{
 const path=location.pathname;
 const home=path==='/',live=['/live','/streamers'].includes(path),account=path==='/account';
 if(!home&&!live&&!account)return;
 // Uneven anchors and small, distinct compositions replace repeated flower rows.
 // Placement is stable: refreshing data never shuffles the user's page.
 const slots=home?[
  {hosts:['#music-memory','#library'],composition:'meadow',tones:['pink','blue']},
  {hosts:['#planes'],composition:'drift',tones:['violet']},
  {hosts:['.site-footer'],composition:'solo',tones:['lemon']}
 ]:live?[
  {hosts:['#live-catalogue'],composition:'drift',tones:['blue','pink']},
  {hosts:['footer'],composition:'solo',tones:['white']}
 ]:[
  {hosts:['#account-welcome'],composition:'solo',tones:['pink']},
  {hosts:['#admin-panel'],composition:'meadow',tones:['violet','lemon']},
  {hosts:['footer'],composition:'drift',tones:['white']}
 ];
 let pending=null,lastHosts=[];
 const visible=element=>Boolean(element&&!element.closest('[hidden],.hidden')&&element.getClientRects().length&&getComputedStyle(element).visibility!=='hidden');
 function rebuild(){
  const accents=[],used=new Set();
  for(const slot of slots){
   const host=slot.hosts.map(selector=>document.querySelector(selector)).find(element=>visible(element)&&!used.has(element));
   if(host){used.add(host);accents.push({host,...slot});}
  }
  const hosts=accents.map(accent=>accent.host),flowerCount=accents.reduce((total,accent)=>total+accent.tones.length,0);
  if(hosts.length===lastHosts.length&&hosts.every((host,index)=>host===lastHosts[index])&&document.querySelectorAll('.botanical-flower').length===flowerCount)return;
  document.querySelectorAll('.botanical-interface').forEach(group=>group.remove());
  document.querySelectorAll('.botanical-caption-host').forEach(host=>host.classList.remove('botanical-caption-host'));
  lastHosts=hosts;
  accents.forEach(({host,composition,tones},index)=>{
   const group=document.createElement('div');group.className='botanical-interface botanical-interface-free';
   group.dataset.botanicalAnchor=host.id||host.tagName.toLowerCase()+'-'+index;
   group.dataset.composition=composition;
   group.setAttribute('aria-hidden','true');group.setAttribute('role','presentation');
   tones.forEach((tone,number)=>{
    const flower=document.createElement('img');flower.className='botanical-flower';
    flower.dataset.flowerTone=tone;flower.dataset.flowerGesture=number?'lift':'lean';
    flower.src='/assets/botanical-flower.svg?v=9.29.11';flower.alt='';flower.width=32;flower.height=44;
    flower.draggable=false;flower.setAttribute('aria-hidden','true');flower.setAttribute('role','presentation');
    group.append(flower);
   });
   host.after(group);
  });
 }
 function schedule(){if(pending!==null)return;pending=requestAnimationFrame(()=>{pending=null;rebuild();});}
 for(const event of ['ol:account-refreshed','ol:interface-update','maggy:access-changed','pageshow','resize'])window.addEventListener(event,schedule);
 const visibility=new MutationObserver(schedule);
 for(const id of ['hero','live-stage']){const section=document.getElementById(id);if(section)visibility.observe(section,{attributes:true,attributeFilter:['class','hidden']});}
 rebuild();
})();
