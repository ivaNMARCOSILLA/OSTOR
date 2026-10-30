/* Shared operational state; public status is never a payment confirmation. */
const $=id=>document.getElementById(id);
async function api(path,data){let options={cache:'no-store'};if(data!==undefined){const r=await fetch('/api/account/me',{cache:'no-store',signal:AbortSignal.timeout(20000)}),a=await r.json();options={...options,method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':a.csrf},body:JSON.stringify(data)};}const r=await fetch(path,{...options,signal:AbortSignal.timeout(20000)}),d=await r.json();if(!r.ok)throw Error((d.error||'No se pudo completar la operación.')+(d.code?' (Referencia: '+d.code+')':'')+(d.diagnostic?' · Stripe: '+d.diagnostic:''));return d;}

// Creator linking must not wait for unrelated administrative diagnostics.
async function refreshCreatorConnection(){
 const button=$('creator-connect-stripe'),status=$('creator-processor-status');if(!button)return;
 try{const manager=await api('/api/payments/status');
 button.disabled=Boolean(manager.creator_connected);button.textContent=manager.creator_connected?'Stripe conectado':'Conectar Stripe de mi canal';
 status.textContent=manager.creator_connected?'Cuenta Stripe conectada. La verificación bancaria y los acuerdos deben estar completos para cobrar.':manager.connect_available?'Conecta tu propia cuenta Stripe para cobrar las suscripciones del canal.':(manager.connect_pending_reason||'Falta completar Stripe Connect en Production. Puedes volver a comprobarlo con este botón.');
 if(manager.play_distribution)button.hidden=true;
 }catch(error){button.disabled=false;button.textContent='Reintentar conexión con Stripe';status.textContent='No se pudo comprobar Stripe. '+error.message;}
}
refreshCreatorConnection();
window.addEventListener('ol:account-refreshed',refreshCreatorConnection);

let inspecting=false;
async function inspect(){if(inspecting)return;inspecting=true;try{await(window.OlAccountReady||window.MaggySession?.ready||Promise.resolve());
 const d=await api('/api/status');let banner=$('ol-maintenance-banner');if(!banner){banner=document.createElement('p');banner.id='ol-maintenance-banner';banner.setAttribute('role','status');document.body.prepend(banner);}banner.hidden=d.maintenance.scope==='off';banner.textContent=(d.maintenance.scope==='payments'?'Pagos de Ol Livis en preparación · ':d.maintenance.scope==='live'?'Ol Livis en preparación · ':'electronicama en mantenimiento · ')+d.maintenance.message;
 document.querySelectorAll('[data-premiere-state]').forEach(el=>el.textContent=d.live_premiere?'Próximo estreno · pronto compartiremos nuestro mejor momento.':'Ol Livis · consulta disponibilidad en tu cuenta.');
 const account=await api('/api/account/me'),admin=account.user?.role==='admin',manager=await api('/api/payments/status');
 if(document.querySelector('#planes a')&&account.user?.live_annual){const link=document.querySelector('#planes a');link.textContent='Tu estado actual · Ol Livis';link.href='/account#pricing';}
 if(account.user?.full_service&&d.live_premiere){document.querySelectorAll('[data-premiere-state]').forEach(el=>el.textContent='Emite con una cuenta y abre el directo con la otra en el segundo dispositivo. Sin pagos. El estreno público continúa cerrado.');const notice=$('ol-live-premiere');if(notice){const badge=notice.querySelector('.premiere-badge'),title=notice.querySelector('strong'),copy=notice.querySelector('p'),link=notice.querySelector('a');if(badge)badge.textContent='PRUEBA PRIVADA';if(title)title.textContent='Ol Livis · prueba entre dos dispositivos';if(copy)copy.textContent='1. Crea tu canal y pulsa Iniciar directo. 2. En el otro dispositivo, entra con la otra cuenta y abre Ver directos.';if(link){link.href=['/live','/streamers'].includes(location.pathname)?'#creator-panel':'/live#creator-panel';link.textContent='Preparar emisión ↗';}}}
 window.dispatchEvent(new CustomEvent('ol:availability',{detail:{premiere:d.live_premiere,admin,preview:Boolean(account.user?.full_service)}}));
 if(d.live_premiere){const trial=$('trial-start');if(trial&&account.user){trial.textContent='Consultar acceso a Ol Livis';}const pricing=$('pricing');if(pricing&&!admin)pricing.classList.add('hidden');}
 document.querySelectorAll('[data-stripe-setup]').forEach(el=>el.hidden=!admin);
 if($('maintenance-form')&&admin){$('maintenance-scope').value=d.maintenance.scope;$('maintenance-message').value=d.maintenance.message;}
 if($('fan-alias-panel')){$('fan-alias-panel').classList.toggle('hidden',!account.user);if(account.user){const fan=await api('/api/account/fan-alias');$('fan-alias').value=fan.alias;}}
 if(admin&&$('email-delivery-health')){const mail=await api('/api/admin/email-health');$('email-delivery-health').textContent=mail.customer_sender_configured?'Remitente para clientes configurado: '+mail.sender_domain+'. Comprueba la entrega real con tu correo.':mail.configured?'Resend necesita un remitente de dominio propio verificado. Gmail y resend.dev no sirven como remitentes públicos de electronicama.':'Falta configurar el remitente y el servicio de correo.';}
 if(admin&&manager.provider==='stripe'&&$('stripe-test-status')){const test=await api('/api/admin/payments/test-status');$('stripe-test-checkout').disabled=!test.configured;$('stripe-test-status').textContent=test.configured?'Sandbox configurado. Ningún pago de prueba activa funciones reales.':'Configura STRIPE_TEST_SECRET_KEY y STRIPE_TEST_WEBHOOK_SECRET en Vercel; la clave pública no basta para crear la sesión.';}
 if(admin&&$('launch-readiness-status')){const launch=await api('/api/admin/launch-readiness');$('launch-readiness-status').textContent=(launch.stripe_test_confirmed?'Stripe de prueba: pago confirmado. ':'Stripe de prueba: falta completar el recorrido. ')+(launch.video_configuration_complete?'Datos de vídeo presentes; falta comprobar la emisión. ':'Ol Livis pendiente de configurar en '+(launch.environment==='production'?'Production':'este entorno')+'. ')+(launch.live_payments_enabled?'Cobros reales habilitados.':'Cobros reales desactivados.');const list=$('launch-readiness-checks');list.replaceChildren();for(const [group,checks] of Object.entries(launch.checks)){if(group!=='video'&&manager.provider!=='stripe')continue;for(const [name,ok] of Object.entries(checks)){const row=document.createElement('li');row.textContent=(group==='video'?'Vídeo · ':'Pagos reales · ')+name+': '+(ok?'presente':'pendiente');list.append(row);}}}
 if($('trial-start')){$('trial-start').disabled=Boolean(account.user?.complimentary||account.user?.live_lifetime||account.user?.role==='admin'||(account.user?.live_annual&&new Date(account.user.access_until).getTime()-Date.now()>30*86400000));if(!account.user)$('trial-start').textContent='Crear cuenta o entrar para contratar';if(!manager.enabled&&account.user&&!account.user.live_annual&&$('premium-availability'))$('premium-availability').textContent=manager.pending_reason;}
 if($('payment-manager-status')&&admin)$('payment-manager-status').textContent=manager.enabled?'Stripe configurado; cobros disponibles cuando corresponda a cada cuenta.':manager.pending_reason;

 if(manager.play_distribution){$('pay-lifetime')?.setAttribute('hidden','');$('creator-connect-stripe')?.setAttribute('hidden','');}
 const receipts=$('creator-receipt-form');if(receipts)receipts.closest('details').hidden=manager.provider==='stripe';
 }catch(error){if($('operations-status'))$('operations-status').textContent=error.message;}finally{inspecting=false;}}
$('maintenance-form')?.addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/admin/maintenance',{scope:$('maintenance-scope').value,message:$('maintenance-message').value});$('operations-status').textContent='Estado guardado para web y aplicación.';await inspect();}catch(error){$('operations-status').textContent=error.message;}});
$('creator-connect-stripe')?.addEventListener('click',async e=>{const button=e.currentTarget;button.disabled=true;button.textContent='Conectando con Stripe…';$('creator-processor-status').textContent='Solicitando autorización segura a Stripe…';try{const d=await api('/api/payments/connect',{});if(!d.url)throw Error('No se recibió la dirección de autorización.');location.assign(d.url);}catch(error){$('creator-processor-status').textContent=error.name==='TimeoutError'?'Stripe está tardando demasiado. Vuelve a intentarlo.':error.message;button.disabled=false;button.textContent='Reintentar conexión con Stripe';}});
// Decorative motion always has an explicit pause and respects OS reduced motion.
let paused=false;try{paused=localStorage.getItem('ol_sticker_motion')==='off';}catch{}
document.documentElement.dataset.stickerMotion=paused?'off':'on';
const collection=$('ol-collection');if(collection){const button=document.createElement('button');button.type='button';button.className='sticker-motion-control';const label=()=>{button.textContent=paused?'Activar movimiento de stickers':'Pausar movimiento de stickers';button.setAttribute('aria-pressed',String(paused));};label();button.addEventListener('click',()=>{paused=!paused;document.documentElement.dataset.stickerMotion=paused?'off':'on';try{localStorage.setItem('ol_sticker_motion',paused?'off':'on');}catch{}label();});collection.append(button);}
window.addEventListener('ol:account-refreshed',inspect);window.addEventListener('maggy:access-changed',inspect);if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',inspect,{once:true});else inspect();setInterval(()=>{if(!document.hidden)inspect();},60000);

$('fan-alias-form')?.addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/account/fan-alias',{alias:$('fan-alias').value});$('fan-alias-status').textContent='Apodo guardado. Tu usuario de acceso no cambia.';}catch(error){$('fan-alias-status').textContent=error.message;}});

$('stripe-test-checkout')?.addEventListener('click',async e=>{e.target.disabled=true;try{const d=await api('/api/admin/payments/test-checkout',{});location.assign(d.url);}catch(error){$('stripe-test-status').textContent=error.message;e.target.disabled=false;}});

// Read-only administrative diagnostics. No background work for public visitors.
let maintenanceBusy=false,maintenanceLast=null,maintenanceTimer=null,maintenanceConfigured=false,maintenancePreferencesKey=null,maintenanceNextAt=0,maintenanceLastAt=0;
const maintenanceHistory=[];
const maintenanceLabels={ok:'Correcto',pending:'Pendiente',error:'Error'};
const maintenanceTrace=[];
function maintenanceScheduleStatus(){
 if(!$('maintenance-check-now'))return;
 let note=$('maintenance-bot-schedule');if(!note){note=document.createElement('p');note.id='maintenance-bot-schedule';note.setAttribute('role','status');$('maintenance-check-now').after(note);}
 const last=maintenanceLastAt?'Última revisión: '+new Date(maintenanceLastAt).toLocaleString('es-ES')+'. ':'Aún no hay revisión completada en esta página. ';
 note.textContent='Bot de revisión · '+last+(maintenanceNextAt?'Próxima revisión: '+new Date(maintenanceNextAt).toLocaleString('es-ES')+'. ':'Solo revisión manual. ')+'Funciona con este panel abierto y visible; al volver, revisa si hay una comprobación pendiente. No hay vigilancia permanente del servidor ni reparaciones de datos automáticas.';
}
function scheduleMaintenance(){
 clearTimeout(maintenanceTimer);maintenanceTimer=null;
 const minutes=Number($('maintenance-frequency')?.value||0);
 if(!maintenanceConfigured||!minutes){maintenanceNextAt=0;maintenanceScheduleStatus();return;}
 maintenanceNextAt=Date.now()+minutes*60000;maintenanceScheduleStatus();
 maintenanceTimer=setTimeout(()=>{maintenanceTimer=null;if(!document.hidden)reviewMaintenance('automática');},minutes*60000);
}

function traceMaintenance(message){
 const terminal=$('maintenance-terminal');if(!terminal)return;
 const line='['+new Date().toLocaleTimeString('es-ES')+'] '+message;
 maintenanceTrace.push(line);if(maintenanceTrace.length>200)maintenanceTrace.splice(0,maintenanceTrace.length-200);
 const row=document.createElement('span');row.textContent=line+'\n';terminal.append(row);
 while(terminal.children.length>200)terminal.firstElementChild.remove();
 if($('maintenance-terminal-follow')?.checked)terminal.scrollTop=terminal.scrollHeight;
}
function downloadMaintenanceTrace(){
 const url=URL.createObjectURL(new Blob([maintenanceTrace.join('\n')+'\n'],{type:'text/plain;charset=utf-8'}));
 const link=document.createElement('a');link.href=url;link.download='ol-terminal-mantenimiento.txt';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
$('maintenance-terminal-download')?.addEventListener('click',downloadMaintenanceTrace);
$('maintenance-terminal-clear')?.addEventListener('click',()=>{maintenanceTrace.length=0;$('maintenance-terminal')?.replaceChildren();traceMaintenance('Vista limpiada. Los datos y las revisiones externas se conservan.');});
window.addEventListener('ol:navigation-checked',event=>{
 if(!maintenanceTimer&&!maintenanceBusy)return;
 const record=event.detail;traceMaintenance('ENLACES · '+record.repaired+' ajustes conocidos · '+record.broken.length+' destinos pendientes.');
 for(const path of record.broken)traceMaintenance('PENDIENTE · Destino: '+path);
});
async function reviewMaintenance(source='manual'){
 if(maintenanceBusy||!$('maintenance-check-now'))return;
 maintenanceBusy=true;$('maintenance-check-now').disabled=true;
 traceMaintenance('INICIO · Revisión '+source+'.');
 traceMaintenance('CONSULTA · GET /api/admin/maintenance-report');
 $('maintenance-check-status').textContent='Revisando el sistema…';
 try{
  const report=await api('/api/admin/maintenance-report');
  traceMaintenance('SERVIDOR · Respuesta recibida · electronicama '+report.version);
  for(const row of report.checks)traceMaintenance(maintenanceLabels[row.status].toUpperCase()+' · '+row.name+' · '+row.detail);
  const navigation=$('maintenance-check-links')?.checked===false?null:window.OlNavigation?.check();
  if(navigation)report.checks.push({name:'Enlaces de esta página',status:navigation.broken.length?'error':'ok',detail:navigation.broken.length+' destinos pendientes; '+navigation.repaired+' ajustes de enlaces conocidos.'});
  const rgb=value=>(value.match(/[\d.]+/g)||[]).slice(0,3).map(Number);
  const luminance=values=>values.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
  const goldButtons=($('maintenance-check-colors')?.checked===false?[]:[...document.querySelectorAll('button,a.button')]).filter(e=>e.getClientRects().length).map(e=>({e,s:getComputedStyle(e)})).filter(({s})=>{const c=rgb(s.backgroundColor);return c.length===3&&c[0]>=180&&c[1]>=140&&c[2]>=60&&c[2]<210&&c[0]>c[2]*1.1;});
  const badGold=goldButtons.filter(({s})=>{const foreground=luminance(rgb(s.webkitTextFillColor||s.color)),background=luminance(rgb(s.backgroundColor));return (Math.max(foreground,background)+.05)/(Math.min(foreground,background)+.05)<4.5||s.animationName!=='none'||Number(s.opacity)<1;});
  report.checks.push({name:'Letras sobre botones dorados',status:badGold.length?'error':goldButtons.length?'ok':'pending',detail:goldButtons.length+' botones visibles comprobados; '+badGold.length+' con contraste o animación pendientes. No revisa imágenes ni pantallas ocultas.'});
  const sync=window.OlInterfaceSync;report.checks.push({name:'Actualización automática de esta página',status:sync?.lastCheck&&Date.now()-sync.lastCheck<45000?'ok':'pending',detail:sync?.lastCheck?'Última comprobación: '+new Date(sync.lastCheck).toLocaleTimeString('es-ES')+'. Fallos consecutivos: '+sync.failures+'.':'Aún no hay una comprobación de sincronización reciente.'});
  const activeVideo=[...document.querySelectorAll('#live-media video,#studio-screen video')].filter(e=>e.getClientRects().length&&e.srcObject);
  report.checks.push({name:'Controles nativos del vídeo',status:activeVideo.some(e=>e.controls)?'error':activeVideo.length?'ok':'pending',detail:activeVideo.length?'Vídeos activos revisados; el directo no debe mostrar pausa/reproducción nativos.':'No hay vídeo activo en esta página. Comprueba un directo en web y móvil.'});
  const player=$('live-player'),chat=$('community-panel'),controls=$('publisher-screen-controls');
  if(player&&chat&&player.getClientRects().length){
   const p=player.getBoundingClientRect(),c=chat.getBoundingClientRect();let blocked=false;
   if(controls&&controls.getClientRects().length){const b=controls.getBoundingClientRect();blocked=c.left<b.right&&c.right>b.left&&c.top<b.bottom&&c.bottom>b.top;}
   const inside=c.left>=p.left-1&&c.right<=p.right+1&&c.height<=p.height*.75+1;
   report.checks.push({name:'Chat y controles de esta pantalla',status:inside&&!blocked?'ok':'error',detail:inside&&!blocked?'Chat dentro del reproductor, con altura máxima del 75%, sin invadir los controles visibles.':'El chat puede superar sus límites o cruzar los controles visibles. Revisa el tamaño y la posición; el bot no cierra el directo.'});
  }else report.checks.push({name:'Chat y controles de esta pantalla',status:'pending',detail:'No hay reproductor visible. La geometría se comprueba únicamente en una pantalla de emisión activa; no se valida una cámara remota desde aquí.'});
  report.ok=!report.checks.some(row=>row.status==='error');
  maintenanceLast=report;maintenanceLastAt=Date.now();
  const date=new Date(report.at).toLocaleString('es-ES');
  const errors=report.checks.filter(row=>row.status==='error').length,pending=report.checks.filter(row=>row.status==='pending').length;
  const summary=date+' · '+errors+' errores · '+pending+' pendientes.';
  $('maintenance-check-status').textContent=summary;
  traceMaintenance('FIN · '+errors+' errores · '+pending+' pendientes.');
  $('maintenance-check-results').replaceChildren();
  for(const row of report.checks){const li=document.createElement('li');li.textContent=row.name+' · '+maintenanceLabels[row.status]+': '+row.detail;$('maintenance-check-results').append(li);}
  maintenanceHistory.unshift(summary);maintenanceHistory.splice(12);
  $('maintenance-check-history').replaceChildren(...maintenanceHistory.map(text=>{const li=document.createElement('li');li.textContent=text;return li;}));
  $('maintenance-download').disabled=false;
 }catch(error){$('maintenance-check-status').textContent='No se pudo completar la revisión: '+error.message;traceMaintenance('ERROR · '+error.message);traceMaintenance('FIN · Revisión incompleta. Puedes volver a intentarlo.');}
 finally{maintenanceBusy=false;$('maintenance-check-now').disabled=false;scheduleMaintenance();}
}
$('maintenance-check-now')?.addEventListener('click',()=>reviewMaintenance('manual'));
if($('maintenance-check-now')){const link=document.createElement('a');link.href='https://github.com/ivaNMARCOSILLA/OSTOR/actions/workflows/navigation-health.yml';link.target='_blank';link.rel='noopener noreferrer';link.textContent='Ver resultados del bot de rutas públicas · GitHub Actions';$('maintenance-check-now').after(link);}

$('maintenance-download')?.addEventListener('click',()=>{if(!maintenanceLast)return;const url=URL.createObjectURL(new Blob([JSON.stringify(maintenanceLast,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='ol-mantenimiento.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function startMaintenanceReviews(){
 if(!$('maintenance-check-now'))return;
 try{await(window.OlAccountReady||Promise.resolve());const account=await api('/api/account/me');if(account.user?.role!=='admin'){clearTimeout(maintenanceTimer);maintenanceTimer=null;maintenanceNextAt=0;maintenanceConfigured=false;maintenanceScheduleStatus();return;}if(maintenanceConfigured)return;maintenanceConfigured=true;
 const key='ol_admin_maintenance_v1_'+account.user.id;
 if(maintenancePreferencesKey!==key){maintenancePreferencesKey=key;try{const saved=JSON.parse(localStorage.getItem(key)||'null');if(saved){if([0,15,30,60].includes(saved.minutes))$('maintenance-frequency').value=String(saved.minutes);$('maintenance-check-colors').checked=saved.colors!==false;$('maintenance-check-links').checked=saved.links!==false;}}catch{}}
 const minutes=Number($('maintenance-frequency').value);traceMaintenance(minutes?'PROGRAMACIÓN · Diagnóstico cada '+minutes+' minutos con el panel visible.':'PROGRAMACIÓN · Solo revisión manual.');maintenanceScheduleStatus();await reviewMaintenance('inicial');}catch{}
}
window.addEventListener('ol:account-refreshed',startMaintenanceReviews);
startMaintenanceReviews();

$('youtube-check-now')?.addEventListener('click',async event=>{
 const button=event.currentTarget;button.disabled=true;
 $('youtube-check-status').textContent='Comprobando conexión con YouTube…';traceMaintenance('CONSULTA · Prueba de conexión con YouTube.');
 try{const result=await api('/api/admin/youtube-diagnostic');$('youtube-check-status').textContent=result.message+' Resultados: '+result.result_count+'.';traceMaintenance('CORRECTO · Conexión con YouTube · '+result.result_count+' resultados.');}
 catch(error){$('youtube-check-status').textContent=error.message;traceMaintenance('ERROR · YouTube · '+error.message);}
 finally{button.disabled=false;}
});

$('stripe-account-health')?.addEventListener('click',async()=>{const button=$('stripe-account-health'),status=$('stripe-account-health-status');button.disabled=true;status.textContent='Consultando el estado real de Stripe…';try{const d=await api('/api/admin/payments/account-health');status.textContent=`Conexión: correcta. Cobros en Stripe: ${d.charges_enabled?'habilitados':'pendientes'}. Transferencias al banco: ${d.payouts_enabled?'habilitadas':'pendientes'}. Requisitos pendientes: ${d.requirements_pending}; vencidos: ${d.requirements_overdue}. Cobros en electronicama: ${d.payments_enabled?'habilitados':'desactivados'}. Esta consulta no ha realizado ningún pago.`;}catch(error){status.textContent=error.message;}finally{button.disabled=false;}});

window.addEventListener('ol:interface-update',event=>{if(event.detail.public&&!document.hidden)inspect();});

for(const id of ['maintenance-frequency','maintenance-check-colors','maintenance-check-links'])$(id)?.addEventListener('change',()=>{if(maintenancePreferencesKey)try{localStorage.setItem(maintenancePreferencesKey,JSON.stringify({minutes:Number($('maintenance-frequency').value),colors:$('maintenance-check-colors').checked,links:$('maintenance-check-links').checked}));}catch{}clearTimeout(maintenanceTimer);maintenanceTimer=null;maintenanceConfigured=false;startMaintenanceReviews();});

// A suspended tab catches up once, rather than replaying every missed interval.
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&maintenanceConfigured&&!maintenanceBusy&&maintenanceNextAt&&Date.now()>=maintenanceNextAt)reviewMaintenance('automática al volver al panel');});
