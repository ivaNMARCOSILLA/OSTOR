/* Repair known navigation aliases only; never submit forms or activate paid access. */
(()=>{
 let availability={premiere:document.body.classList.contains('ol-live-premiere-only'),admin:false},timer;
 const aliases={'#register':'#credentials','#create-account':'#credentials','#register-form':'#credentials','#login':'#login-form','#my-space':'#mi-espacio'};
 const livePaths=new Set(['/live','/streamers']);
 const reports=[];
 function visibleTarget(id){const target=document.getElementById(id);if(!target)return null;for(let p=target.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;return target;}
 function focusTarget(target){target.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});if(!target.matches('input,button,a,select,textarea'))target.setAttribute('tabindex','-1');target.focus({preventScroll:true});}
 function scan(){
  let repaired=0;const broken=[];
  document.querySelectorAll('a[href]').forEach(link=>{
   const raw=link.dataset.olOriginalHref||link.getAttribute('href');if(!raw||raw.startsWith('mailto:')||raw.startsWith('tel:'))return;
   let url;try{url=new URL(raw,location.href);}catch{broken.push('enlace no válido');return;}if(url.origin!==location.origin)return;
   let next=raw,label=null;
   if(url.pathname==='/streamers'&&!raw.startsWith('#'))next='/live'+url.search+url.hash;
   if(aliases[url.hash]&&((url.pathname===location.pathname&&!document.getElementById(url.hash.slice(1)))||url.pathname==='/account'))next=url.pathname+url.search+aliases[url.hash];
   if(availability.premiere&&!availability.admin&&livePaths.has(url.pathname)&&['#live-catalogue','#creator-panel','#stream-studio'].includes(url.hash)){next='/live#ol-live-premiere';label=url.hash==='#live-catalogue'?'Próximo estreno':'Ol Livis · en preparación';}
   if(next!==raw){if(!link.dataset.olOriginalHref){link.dataset.olOriginalHref=raw;link.dataset.olOriginalText=link.textContent;}if(link.getAttribute('href')!==next){link.setAttribute('href',next);repaired++;}if(label){const spans=link.querySelectorAll('span');if(spans.length>1)spans[spans.length-1].textContent=label;else link.textContent=label;}}
   else if(link.dataset.olOriginalHref){link.setAttribute('href',raw);link.textContent=link.dataset.olOriginalText;delete link.dataset.olOriginalHref;delete link.dataset.olOriginalText;}
   const actual=new URL(link.href,location.href);if(actual.pathname===location.pathname&&actual.hash){try{if(!document.getElementById(decodeURIComponent(actual.hash.slice(1))))broken.push(actual.pathname+actual.hash);}catch{broken.push('fragmento no válido');}}
  });
  const record={at:new Date().toISOString(),repaired,broken:[...new Set(broken)]};reports.push(record);if(reports.length>12)reports.shift();
  const summary=document.getElementById('navigation-check-status');if(summary)summary.textContent=record.broken.length?record.broken.length+' destinos pendientes de revisar.': 'Enlaces comprobados. '+record.repaired+' ajustes de destinos conocidos en esta revisión.';
  window.dispatchEvent(new CustomEvent('ol:navigation-checked',{detail:record}));return record;
 }
 document.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const link=event.target.closest('a[href]');if(!link)return;scan();const url=new URL(link.href,location.href);
  if(url.origin!==location.origin||url.pathname!==location.pathname||url.search!==location.search||!url.hash)return;
  let id;try{id=decodeURIComponent(url.hash.slice(1));}catch{return;}const target=visibleTarget(id);if(!target)return;
  if(!target.getClientRects().length)return;event.preventDefault();history.pushState(null,'',url.hash);focusTarget(target);
 });
 window.addEventListener('ol:availability',event=>{availability=event.detail;scan();if(availability.premiere&&!availability.admin&&livePaths.has(location.pathname)&&['#live-catalogue','#creator-panel','#stream-studio'].includes(location.hash)){history.replaceState(null,'','#ol-live-premiere');const target=document.getElementById('ol-live-premiere');if(target)focusTarget(target);}});
 document.getElementById('navigation-check-now')?.addEventListener('click',scan);
 window.OlNavigation={check:scan,get recent(){return reports.slice();}};
 function periodic(){clearTimeout(timer);if(!document.hidden)scan();timer=setTimeout(periodic,300000);}
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)scan();});periodic();
})();
