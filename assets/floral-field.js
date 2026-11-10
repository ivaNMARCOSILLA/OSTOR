/* A thousand quiet, freely scattered daisies share one reusable SVG drawing. */
(()=>{
 'use strict';
 const body=document.body;
 if(!body?.classList.contains('electronicama-theme')||document.getElementById('floral-field'))return;
 const NS='http://www.w3.org/2000/svg',COUNT=1000;
 const palette=['#fffdfa','#ff82c9','#df79ef','#ae9aff','#72b9ff','#75e2eb','#ff788c','#ffad75','#fff18b','#bfe990'];
 const make=(tag,attributes={})=>{
  const node=document.createElementNS(NS,tag);
  for(const [key,value] of Object.entries(attributes))node.setAttribute(key,String(value));
  return node;
 };
 const field=make('svg',{
  id:'floral-field','aria-hidden':'true',role:'presentation',focusable:'false',
  tabindex:'-1',inert:'','data-flower-count':COUNT,preserveAspectRatio:'none'
 });
 const defs=make('defs');
 const roundedPetals=[
  'M-4-5C-11-15-7-26 0-24C7-22 6-12 3-5Z',
  'M2-6C3-18 12-24 17-19C23-12 13-5 6-2Z',
  'M6-3C15-9 26-6 24 1C23 9 14 8 6 3Z',
  'M6 2C18 3 24 14 18 19C11 23 5 13 2 6Z',
  'M4 6C9 17 3 26-3 23C-10 21-6 12-3 5Z',
  'M-2 6C-5 18-16 23-20 16C-23 10-13 4-6 2Z',
  'M-6 3C-17 9-26 4-24-3C-21-10-12-7-5-3Z',
  'M-6-2C-17-5-23-16-16-20C-10-23-4-13-2-6Z'
 ];
 const slimmerPetals=[
  'M-3-6C-9-16-5-25 0-24C5-23 5-14 3-6Z',
  'M1-6C0-17 6-25 11-21C16-17 10-9 5-4Z',
  'M5-5C11-17 21-19 23-13C25-7 16-3 7-1Z',
  'M7-2C18-8 27-1 23 4C20 10 13 6 6 3Z',
  'M6 2C18 4 23 15 17 18C11 22 7 13 3 6Z',
  'M3 6C11 15 6 25 0 24C-5 23-3 14-3 6Z',
  'M-1 7C-1 20-11 24-15 19C-20 14-10 7-6 3Z',
  'M-5 5C-13 17-23 14-24 8C-25 2-15 1-7 0Z',
  'M-7 0C-19 3-26-6-21-11C-16-16-9-8-4-4Z',
  'M-5-4C-16-10-15-23-9-23C-3-23-2-13-1-6Z'
 ];
 for(const [name,petals] of [['open',roundedPetals],['soft',slimmerPetals]]){
  const symbol=make('symbol',{id:'floral-field-daisy-'+name,viewBox:'-26 -26 52 52'});
  const bloom=make('g',{fill:'currentColor',stroke:'currentColor','stroke-width':'.35','stroke-linejoin':'round'});
  for(const shape of petals)bloom.append(make('path',{d:shape}));
  symbol.append(bloom,make('circle',{r:6.1,fill:'#ffce40',stroke:'#fff0a6','stroke-width':'.9'}));
  for(const [cx,cy,r] of [[-2.2,-1.9,.65],[1.8,-2.1,.8],[.1,.2,.7],[-2.1,2,.8],[2.2,1.7,.6]]){
   symbol.append(make('circle',{cx,cy,r,fill:'#9b780f',opacity:'.72'}));
  }
  defs.append(symbol);
 }
 field.append(defs);
 const flowers=[],fragment=document.createDocumentFragment();
 let seed=0x56a7b31d;
 const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
 for(let index=0;index<COUNT;index++){
  const data={u:random(),v:random(),size:11+random()*18,angle:random()*360};
  const node=make('use',{
   href:'#floral-field-daisy-'+(index%3?'open':'soft'),
   x:-26,y:-26,width:52,height:52,
   class:'floral-field-flower',color:palette[index%palette.length],opacity:(.55+random()*.45).toFixed(2)
  });
  flowers.push({node,...data});fragment.append(node);
 }
 field.append(fragment);body.prepend(field);
 let frame=null,lastWidth=0,lastHeight=0;
 function layout(){
  frame=null;
  if(!field.isConnected)return;
  // Use the actual containing box: legal pages have a narrower, padded body.
  // Measuring the absolute SVG avoids counting its own drawing as page height.
  const box=field.getBoundingClientRect(),width=Math.round(box.width),height=Math.round(box.height);
  if(width<1||height<1||width===lastWidth&&height===lastHeight)return;
  lastWidth=width;lastHeight=height;
  field.setAttribute('viewBox',`0 0 ${width} ${height}`);
  for(const {node,u,v,size,angle} of flowers){
   const radius=size*.72;
   const x=Math.min(width/2,radius)+u*Math.max(0,width-radius*2);
   const y=Math.min(height/2,radius)+v*Math.max(0,height-radius*2);
   node.setAttribute('transform',`translate(${x.toFixed(2)} ${y.toFixed(2)}) rotate(${angle.toFixed(2)}) scale(${(size/52).toFixed(4)})`);
  }
 }
 function schedule(){if(frame===null)frame=requestAnimationFrame(layout);}
 if('ResizeObserver' in window)new ResizeObserver(schedule).observe(body);
 window.addEventListener('resize',schedule,{passive:true});
 window.addEventListener('pageshow',schedule);
 window.addEventListener('afterprint',schedule);
 const forcedColours=window.matchMedia?.('(forced-colors: active)');
 if(forcedColours?.addEventListener)forcedColours.addEventListener('change',schedule);
 else forcedColours?.addListener?.(schedule);
 window.addEventListener('pagehide',()=>{if(frame!==null){cancelAnimationFrame(frame);frame=null;}});
 schedule();
})();
