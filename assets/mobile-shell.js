/* One account and the same destinations, with navigation designed for touch. */
(()=>{
 if(document.getElementById('mobile-dock'))return;
 const dock=document.createElement('nav');dock.id='mobile-dock';dock.setAttribute('aria-label','Navegación principal móvil');
 const destinations=[['/#inicio','Inicio','home'],['/#library','Música','music'],['/live#live-catalogue','Ol Livis','live'],['/#hologramas','Hologramas','holograms'],['/account','Mi cuenta','account']];
 const drawings={home:'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',music:'M9 18V5l11-2v13M9 7l11-2M9 18c0 2-6 3-6 0s6-3 6 0M20 16c0 2-6 3-6 0s6-3 6 0',live:'M8 3h8l5 5v8l-5 5H8l-5-5V8Z M10 8l7 4-7 4Z',holograms:'m12 2 10 10-10 10L2 12Z M12 2v20M2 12h20',account:'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-3c0-6 16-6 16 0v3'};
 for(const [href,title,key] of destinations){
  const link=document.createElement('a');link.href=href;link.dataset.mobileDestination=key;
  const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('aria-hidden','true');icon.setAttribute('focusable','false');
  const path=document.createElementNS(icon.namespaceURI,'path');path.setAttribute('d',drawings[key]);icon.append(path);
  const label=document.createElement('span');label.textContent=title;link.append(icon,label);dock.append(link);
 }
 document.body.append(dock);
 function current(){
  const path=location.pathname,hash=location.hash;
  const key=path==='/account'?'account':['/live','/streamers'].includes(path)?'live':path==='/'?(hash==='#library'?'music':hash==='#hologramas'?'holograms':'home'):null;
  for(const link of dock.children){if(link.dataset.mobileDestination===key)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');}
 }
 current();window.addEventListener('hashchange',current);window.addEventListener('popstate',current);
 document.addEventListener('click',event=>{if(event.target.closest('#mobile-dock a'))setTimeout(current,0);});
 const header=document.querySelector('.content>.topbar'),menu=document.getElementById('mobile-nav');
 if(!header||!menu)return;
 const language=header.querySelector('.site-language'),marker=document.createComment('desktop language position');
 if(language)language.before(marker);
 const search=document.createElement('a');search.className='mobile-quick-search';search.href='#library';search.textContent='Buscar';search.setAttribute('aria-label','Buscar música');header.append(search);
 search.addEventListener('click',()=>{requestAnimationFrame(()=>document.getElementById('search-input')?.focus({preventScroll:true}));});
 const mobile=matchMedia('(max-width:800px)');
 function measure(){if(mobile.matches)document.documentElement.style.setProperty('--mobile-header-edge',Math.ceil(header.getBoundingClientRect().bottom)+'px');}
 function layout(){
  if(language){if(mobile.matches)menu.insertBefore(language,document.getElementById('cookie-settings'));else marker.after(language);}
  if(!mobile.matches){menu.classList.add('hidden');const button=document.getElementById('mobile-menu');button.setAttribute('aria-expanded','false');button.setAttribute('aria-label','Abrir menú de navegación');document.getElementById('mobile-menu-label').textContent='Menú';}
  measure();
 }
 layout();mobile.addEventListener('change',layout);
 new ResizeObserver(measure).observe(header);
 document.getElementById('mobile-menu').addEventListener('click',measure);
})();
