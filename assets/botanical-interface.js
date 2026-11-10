/* Twenty decorative flowers share the ordinary page flow, never live controls. */
(()=>{
 const path=location.pathname;
 const home=path==='/',live=['/live','/streamers'].includes(path),account=path==='/account';
 if(!home&&!live&&!account)return;
 const flowerCount=20;
 const slots=home?[
  ['#hero'],['#library'],['#momentos'],['.mix-section'],['#ol-collection'],
  ['#hologramas'],['#founders'],['#planes'],['#public-visit-registry'],['.site-footer']
 ]:live?[
  ['.platform-content>.intro','.account-shell .intro'],['#live-catalogue'],
  ['#founders'],['.discovery','#ol-collection'],['footer']
 ]:[
  ['#account-welcome'],['#credentials','#member-panel','#invitation'],
  ['#founders'],['#pricing','#admin-panel'],['footer']
 ];
 let pending=null,lastHosts=[];
 const visible=element=>Boolean(element&&!element.closest('[hidden],.hidden')&&element.getClientRects().length&&getComputedStyle(element).visibility!=='hidden');
 function rebuild(){
  const hosts=[],used=new Set();
  for(const choices of slots){
   const host=choices.map(selector=>document.querySelector(selector)).find(element=>visible(element)&&!used.has(element));
   if(host){used.add(host);hosts.push(host);}
  }
  if(hosts.length===lastHosts.length&&hosts.every((host,index)=>host===lastHosts[index])&&document.querySelectorAll('.botanical-flower').length===(hosts.length?flowerCount:0))return;
  document.querySelectorAll('.botanical-interface').forEach(group=>group.remove());
  document.querySelectorAll('.botanical-caption-host').forEach(host=>host.classList.remove('botanical-caption-host'));
  lastHosts=hosts;
  if(!hosts.length)return;
  // Hidden account panels do not swallow flowers: spread their share over the
  // remaining visible anchors without adding anything to a video or a form.
  const base=Math.floor(flowerCount/hosts.length),extra=flowerCount%hosts.length;
  hosts.forEach((host,index)=>{
   const group=document.createElement('div');group.className='botanical-interface';
   group.dataset.botanicalAnchor=host.id||host.tagName.toLowerCase()+'-'+index;
   group.setAttribute('aria-hidden','true');group.setAttribute('role','presentation');
   for(let number=0;number<base+(index<extra?1:0);number++){
    const flower=document.createElement('img');flower.className='botanical-flower';
    if((index+number)%4===2)flower.classList.add('botanical-flower-rose');
    flower.src='/assets/botanical-flower.svg?v=9.29.10';flower.alt='';flower.width=24;flower.height=36;
    flower.draggable=false;flower.setAttribute('aria-hidden','true');flower.setAttribute('role','presentation');
    group.append(flower);
   }
   const caption=host.id==='hero'?host.querySelector('.entry-caption'):null;
   if(caption){caption.classList.add('botanical-caption-host');group.classList.add('botanical-interface-inline');caption.append(group);}
   else host.after(group);
  });
 }
 function schedule(){if(pending!==null)return;pending=requestAnimationFrame(()=>{pending=null;rebuild();});}
 for(const event of ['ol:account-refreshed','ol:interface-update','maggy:access-changed','pageshow','resize'])window.addEventListener(event,schedule);
 const visibility=new MutationObserver(schedule);
 for(const id of ['hero','live-stage']){const section=document.getElementById(id);if(section)visibility.observe(section,{attributes:true,attributeFilter:['class','hidden']});}
 rebuild();
})();
