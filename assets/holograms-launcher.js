// No camera, GPU scene or model downloads until Hologramas is opened.
(()=>{
 const panel=document.getElementById('hologram-viewer');if(!panel)return;
 const ui=document.getElementById('holo-ui'),status=document.getElementById('holo-status'),summary=panel.querySelector('summary');let revision=0,viewer=null;
 async function toggle(){const current=++revision;if(viewer){viewer.dispose();viewer=null;}ui.hidden=true;summary.textContent=panel.open?'Cerrar Hologramas':'Abrir Hologramas';if(!panel.open){status.textContent='Visor cerrado. Cámara y movimiento apagados.';return;}status.textContent='Preparando el visor 3D…';try{const module=await import('/assets/holograms.js?v=9.10.0');if(!panel.open||current!==revision)return;ui.hidden=false;viewer=module.createHolograms(panel);}catch{ui.hidden=true;status.textContent='No se pudo abrir el visor 3D. Comprueba la conexión o utiliza un navegador con WebGL. Puedes cerrar y volver a intentarlo.';}}
 panel.addEventListener('toggle',toggle);panel.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();panel.open=false;summary.focus();}});window.addEventListener('pageshow',event=>{if(event.persisted&&panel.open)toggle();});window.addEventListener('pagehide',()=>{revision++;viewer?.dispose();viewer=null;});
})();
