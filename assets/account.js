'use strict';
const $ = id => document.getElementById(id);
let csrf = '', current = null, members = [], payments = [],memberPage=1,invitationPage=1;
const requestedReturn=new URLSearchParams(location.search).get('next')?.replace(/^\/live(?=#|$)/,'/streamers');
const streamReturn=(['/streamers','/streamers#stream-studio','/streamers#creator-panel','/streamers#live-catalogue','/streamers#founders'].includes(requestedReturn)||/^\/streamers#canal-[a-f0-9]{32}$/.test(requestedReturn||''))?requestedReturn.replace(/^\/streamers/,'/live'):null;
const inviteToken = new URLSearchParams(location.hash.slice(1)).get('invite');
if (inviteToken) { history.replaceState(null, '', '/account'); $('invitation').classList.remove('hidden'); $('credentials').classList.add('hidden'); }
const date = value => value && new Date(value).getUTCFullYear()>9000 ? 'Sin vencimiento' : value ? new Date(value).toLocaleString('es-ES', {dateStyle:'medium',timeStyle:'short'}) : 'Sin activar';
const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
function status(value) { $('account-status').textContent = value; }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok){const error=new Error(result.error||'No se pudo completar la operación.');error.code=result.code;throw error;}
  return result;
}
async function refresh() {
  const data = await api('/api/account/me'); csrf = data.csrf; current = data.user;
  $('credentials').classList.toggle('hidden', Boolean(current) || Boolean(inviteToken));
  $('member-panel').classList.toggle('hidden', !current);
  $('admin-panel').classList.toggle('hidden', current?.role !== 'admin');
  window.dispatchEvent(new Event('ol:account-refreshed'));
  const videoReady=Boolean(data.live_video_ready)&&!data.live_premiere;
  document.querySelectorAll('[data-stripe-setup]').forEach(el=>el.hidden=current?.role!=='admin');
  $('premium-availability').textContent=videoReady?'Ol del bueno: siete días de prueba y, después, 25 € en un único pago si decides continuar.':'El vídeo aún se está preparando. Tu prueba de siete días todavía no empieza y no se solicita ningún pago.';
  $('trial-start').disabled=!videoReady||Boolean(current?.live_trial_until||current?.live_lifetime||current?.complimentary);
  $('trial-start').textContent=data.live_premiere?'Próximo estreno · Ol Live':current?.trial_active?'Prueba activa hasta '+date(current.live_trial_until):current?.live_trial_until?'Prueba ya utilizada':'Iniciar mis siete días';
  if (!current) return;
  $('member-title').textContent = `Tu cuenta · ${current.username}${current.founder_number?' · Fundador n.º '+current.founder_number:''}`;
  $('access-status').textContent=current.role==='admin'?'Administrador: acceso de gestión activo en todos tus dispositivos.':current.founder_active?'Plaza n.º '+current.founder_number+': '+(data.founder_reservation?.confirmed?'pago único confirmado.':'reservada durante la prueba de siete días; después, continuar cuesta 25 €.')+' Consulta tu progreso abajo.':current.live_lifetime?'Ol Live completo: pago único confirmado, sin vencimiento.':current.trial_active?'Prueba de Ol Live activa hasta '+date(current.live_trial_until):data.founder_last_release?'Tu prueba terminó y la plaza n.º '+data.founder_last_release.number+' ha quedado disponible. Puedes continuar con 25 € en un pago único, pero el número anterior no está garantizado.':current.complimentary?'Acceso especial por invitación de administración.':current.active?'Ol Live activo hasta '+date(current.access_until):'Música y biblioteca gratuitas. Puedes probar Ol Live durante siete días cuando el vídeo esté disponible.';
  $('enter-maggy').classList.remove('hidden');
  $('enter-streamers').classList.remove('hidden');
  $('enter-streamers').textContent=current.streamer_active?'Entrar a mi estudio ↗':'Explorar Ol Live ↗';
  $('enter-streamers').href=current.streamer_active?'/live#stream-studio':'/live#live-catalogue';
  $('pricing').classList.toggle('hidden',Boolean(current.complimentary||current.role==='admin'));
  $('next-payment').textContent=current.role==='admin'?'Tu cuenta de gestión no tiene vencimiento.':current.live_lifetime?'Pago único confirmado. No tienes próximas cuotas.':current.founder_active?'Plaza reservada hasta '+(data.founder_reservation?.payment_due_at?date(data.founder_reservation.payment_due_at):'la activación real de Ol Live y siete días de prueba')+'. Para conservarla se deben confirmar los 25 €. Sin pago, vuelve a estar disponible.':current.complimentary?'Invitación gratuita de administración, hasta su retirada.':current.live_trial_until?'Prueba hasta '+date(current.live_trial_until)+'. Después puedes continuar con 25 € en un único pago; sin pago se libera tu plaza. Nunca se cobra automáticamente.':'Siete días de prueba cuando el vídeo esté disponible. Después, 25 € en un único pago si decides continuar.';
  if(data.founder_reservation&&!data.founder_reservation.confirmed&&data.founder_reservation.payment_due_at){$('next-payment').textContent='Prueba hasta '+date(data.founder_reservation.trial_until)+'. Confirma los mismos 25 € antes de '+date(data.founder_reservation.payment_due_at)+' para conservar tu número. Al terminar la prueba, continuar cuesta 25 € en un único pago. Los cobros aún no están disponibles. Sin pago se libera la plaza.';}
  $('my-payments').replaceChildren();
  for (const payment of data.payments) {
    const row = document.createElement('tr');
    for (const value of [payment.plan==='lifetime'?'Ol Live · pago único':'Periodo anterior de Ol Live', `${(payment.amount_cents/100).toFixed(2)} €`, date(payment.starts_at), date(payment.ends_at), date(payment.verified_at)]) row.append(text('td', value));
    $('my-payments').append(row);
  }
  if (current.role === 'admin') await loadAdmin();
}
async function loadAdmin() {
  const data = await api('/api/admin/members'); members = data.members; payments = data.payments;
  renderMembers();
  if($('invitation-history').open)await loadInvitations();
  $('admin-payments').replaceChildren();
  for (const payment of payments) {
    const row=document.createElement('tr');
    for (const value of [payment.username, payment.plan==='lifetime'?'Ol Live · pago único':'Periodo anterior de Ol Live',`${(payment.amount_cents/100).toFixed(2)} €`,payment.reference,date(payment.verified_at),date(payment.ends_at)]) row.append(text('td',value));
    $('admin-payments').append(row);
  }
  renderCalendar();
  await loadStatistics();
}
function renderMembers(){
  const clients=members.filter(member=>member.role!=='admin');
  $('admin-counters').textContent=`${clients.length} clientes · ${clients.filter(member=>member.active).length} con Ol Live · ${clients.filter(member=>member.complimentary).length} amigos con Ol Live gratuito`;
  const query=$('admin-member-search').value.trim().toLowerCase();const matches=members.filter(member=>member.username.toLowerCase().includes(query));
  const pages=Math.max(1,Math.ceil(matches.length/25));memberPage=Math.min(memberPage,pages);
  $('member-page').textContent=`Página ${memberPage} de ${pages} · ${matches.length} cuentas`;
  $('members-prev').disabled=memberPage===1;$('members-next').disabled=memberPage===pages;
  $('admin-members').replaceChildren();
  for (const member of matches.slice((memberPage-1)*25,memberPage*25)) {
    const row = document.createElement('tr');
    for (const value of [member.username, member.role === 'admin' ? 'Administrador' : member.founder_active ? 'Fundador n.º '+member.founder_number : member.complimentary ? 'Amigo · gratuito' : member.streamer_active ? 'Ol Live Creador' : 'Cliente', member.active ? 'Ol Live activo' : 'Cuenta gratuita', member.founder_active ? 'Fundador · actividad requerida' : member.live_lifetime ? 'Sin vencimiento · pago único' : member.trial_active ? 'Prueba hasta '+date(member.live_trial_until) : member.complimentary ? 'Sin vencimiento · invitación gratuita' : member.streamer_until ? `Ol: ${date(member.access_until)} · Ol Live Creador: ${date(member.streamer_until)}` : date(member.access_until)]) row.append(text('td', value));
    const actions = document.createElement('td');
    if (member.role !== 'admin') {
      const friend=text('button',member.complimentary?'Retirar acceso gratuito':'Dar acceso gratuito');friend.type='button';
      friend.addEventListener('click',async()=>{friend.disabled=true;try{await api('/api/admin/friend-access',{member_id:member.id,active:!member.complimentary});await refresh();status(member.complimentary?'Acceso gratuito retirado. Se conserva cualquier periodo ya pagado.':'Acceso gratuito concedido sin registrar ningún pago.');}catch(error){status(error.message);}finally{friend.disabled=false;}});actions.append(friend);
      const revoke = text('button', 'Revocar Ol Live'); revoke.type='button';
      revoke.addEventListener('click', async () => { if (!confirm(`¿Revocar Ol Live de ${member.username}?`)) return; try { await api('/api/admin/revoke', {member_id:member.id}); await refresh(); status('Ol Live revocado y sesiones cerradas. La música sigue siendo gratuita.'); } catch(error){status(error.message);} }); actions.append(revoke);
    }
    row.append(actions); $('admin-members').append(row);
  }
 }
async function loadInvitations(){
 const data=await api('/api/admin/invitations?page='+invitationPage);invitationPage=data.page;
 $('invitation-count').textContent=`${data.total} invitaciones registradas. Mostrando hasta 25 por página.`;
 $('invitation-page').textContent=`Página ${data.page} de ${data.pages}`;
 $('invitations-prev').disabled=data.page===1;$('invitations-next').disabled=data.page===data.pages;
 $('admin-invitations').replaceChildren();
 for(const invitation of data.invitations){const row=document.createElement('tr');const pending=!invitation.used_at&&new Date(invitation.expires_at)>new Date();for(const value of [invitation.username,invitation.used_at?'Aceptada':pending?'Pendiente':'Caducada',date(invitation.expires_at)])row.append(text('td',value));const action=document.createElement('td');const button=text('button',pending?'Cancelar invitación':'Borrar registro');button.type='button';button.addEventListener('click',async()=>{if(pending&&!confirm('¿Cancelar esta invitación? Su enlace dejará de funcionar.'))return;button.disabled=true;try{await api('/api/admin/invitations/clear',{member_id:invitation.member_id});await loadInvitations();status('Invitación eliminada. La cuenta y los pagos se conservan.');}catch(error){status(error.message);}finally{button.disabled=false;}});action.append(button);row.append(action);$('admin-invitations').append(row);}
}
$('admin-member-search').addEventListener('input',()=>{memberPage=1;renderMembers();});
$('members-prev').addEventListener('click',()=>{memberPage-=1;renderMembers();});$('members-next').addEventListener('click',()=>{memberPage+=1;renderMembers();});
$('invitation-history').addEventListener('toggle',()=>{if($('invitation-history').open)loadInvitations().catch(error=>status(error.message));});
$('invitations-prev').addEventListener('click',()=>{invitationPage-=1;loadInvitations().catch(error=>status(error.message));});$('invitations-next').addEventListener('click',()=>{invitationPage+=1;loadInvitations().catch(error=>status(error.message));});
$('clear-invitations').addEventListener('click',async()=>{const button=$('clear-invitations');button.disabled=true;try{await api('/api/admin/invitations/clear',{completed:true});await loadInvitations();status('Historial usado y caducado eliminado. Se conservan las cuentas, el acceso y los pagos.');}catch(error){status(error.message);}finally{button.disabled=false;}});
let moderationPage=1;
async function loadModeration(){const data=await api('/api/admin/moderation?page='+moderationPage+'&flagged='+$('moderation-filter').value);moderationPage=data.page;$('moderation-count').textContent=`${data.total} registros · conservación: ${data.retention_days} días`;$('moderation-page').textContent=`Página ${data.page} de ${data.pages}`;$('moderation-prev').disabled=data.page===1;$('moderation-next').disabled=data.page===data.pages;$('admin-moderation').replaceChildren();const categories={insult:'Insulto',threat:'Amenaza',sexual_minors:'Menores / contenido sexual',illicit_trade:'Oferta ilegal',report:'Denuncia'};for(const record of data.records){const row=document.createElement('tr');for(const value of [date(record.created_at),record.username+' / '+record.channel,record.kind==='sticker'?'Sticker':record.kind==='transcript'?'Voz transcrita':record.kind==='report'?'Denuncia':'Comentario',categories[record.category]||'Sin detección',record.body])row.append(text('td',value));$('admin-moderation').append(row);}}
$('moderation-history').addEventListener('toggle',()=>{if($('moderation-history').open)loadModeration().catch(error=>status(error.message));});
$('moderation-filter').addEventListener('change',()=>{moderationPage=1;loadModeration().catch(error=>status(error.message));});
$('moderation-prev').addEventListener('click',()=>{moderationPage-=1;loadModeration().catch(error=>status(error.message));});$('moderation-next').addEventListener('click',()=>{moderationPage+=1;loadModeration().catch(error=>status(error.message));});
let notificationPage=1;
async function loadNotifications(){const data=await api('/api/admin/notifications?page='+notificationPage);notificationPage=data.page;$('mail-status').textContent=`Destino: ${data.recipient}. ${data.email_ready?'Servicio de correo configurado.':'Correo pendiente de configurar: añade OL_EMAIL_FROM y SMTP_HOST, SMTP_USER, SMTP_PASSWORD (o RESEND_API_KEY) como variables privadas en Vercel.'} ${data.pending} avisos pendientes de envío.`;$('notification-page').textContent=`Página ${data.page} de ${data.pages} · ${data.total} avisos`;$('notifications-prev').disabled=data.page===1;$('notifications-next').disabled=data.page===data.pages;$('retry-notifications').disabled=!data.email_ready;$('admin-notifications').replaceChildren();const states={sent:'Enviado al proveedor de correo',pending:'Pendiente',failed:'Envío fallido · pendiente de reintento',sending:'Enviando'};for(const notice of data.notifications){const card=document.createElement('article');card.append(text('h4',notice.title),text('p',notice.detail),text('small',date(notice.created_at)+' · '+(states[notice.status]||notice.status)));$('admin-notifications').append(card);}}
$('notification-history').addEventListener('toggle',()=>{if($('notification-history').open)loadNotifications().catch(error=>status(error.message));});
$('notifications-prev').addEventListener('click',()=>{notificationPage-=1;loadNotifications().catch(error=>status(error.message));});$('notifications-next').addEventListener('click',()=>{notificationPage+=1;loadNotifications().catch(error=>status(error.message));});
$('retry-notifications').addEventListener('click',async()=>{const button=$('retry-notifications');button.disabled=true;try{const result=await api('/api/admin/notifications/retry',{});status(`${result.sent} de ${result.attempted} correos entregados al proveedor de envío.`);await loadNotifications();}catch(error){status(error.message);}finally{button.disabled=false;}});
let stickerDesigns=[],stickerPage=1,stickerPages=1,stickerSearchTimer,stickerRequest=0;
function selectStickerDesign(){const item=stickerDesigns.find(item=>item.id===$('sticker-design-target').value);$('sticker-design-points').disabled=Boolean(item);$('sticker-design-points').value=item?.points||0;$('sticker-design-name').value=item?.name||'';}
async function loadStickerDesigns(){const revision=++stickerRequest;const params=new URLSearchParams({page:String(stickerPage),q:$('admin-sticker-search').value.trim(),series:$('admin-sticker-series').value});const data=await api('/api/admin/stickers?'+params);if(revision!==stickerRequest)return;const previousDesign=stickerDesigns.find(item=>item.id===$('sticker-design-target').value);stickerPage=data.page;stickerPages=data.pages;stickerDesigns=data.stickers;$('admin-sticker-page').textContent=`Página ${data.page} de ${data.pages} · ${data.filtered_total} diseños`;$('admin-sticker-prev').disabled=data.page<=1;$('admin-sticker-next').disabled=data.page>=data.pages;const filter=$('admin-sticker-series'),series=filter.value;if(filter.dataset.values!==data.series.join('|')){filter.replaceChildren(new Option('Todas las colecciones',''));for(const value of data.series)filter.append(new Option(value,value));filter.value=series;filter.dataset.values=data.series.join('|');}const selected=$('sticker-design-target').value;$('sticker-design-target').replaceChildren();const fresh=text('option','Crear un sticker nuevo');fresh.value='';$('sticker-design-target').append(fresh);$('admin-sticker-list').replaceChildren();for(const item of stickerDesigns){const option=text('option',`N.º ${item.number} · ${item.name} · ${item.points} puntos`);option.value=item.id;$('sticker-design-target').append(option);const card=document.createElement('article');card.className='collection-sticker unlocked';const img=document.createElement('img');img.src=item.image;img.alt=item.name;img.loading='lazy';const button=text('button','Editar diseño');button.type='button';button.addEventListener('click',()=>{$('sticker-design-target').value=item.id;selectStickerDesign();$('sticker-design-form').scrollIntoView({behavior:'smooth'});});const sound=text('button','♪ Escuchar frase');sound.type='button';sound.addEventListener('click',()=>window.OlStickerAudio?.play(item.id,sound,item.phrase));card.append(img,text('strong',`N.º ${item.number} · ${item.name}`),text('small',item.points===0?'Gratuito':item.points+' puntos'),sound,button);$('admin-sticker-list').append(card);}if(selected&&previousDesign&&!stickerDesigns.some(item=>item.id===selected)){const option=text('option','Editando · '+previousDesign.name);option.value=selected;$('sticker-design-target').append(option);stickerDesigns.push(previousDesign);}$('sticker-design-target').value=selected;}
$('admin-sticker-prev').addEventListener('click',()=>{stickerPage=Math.max(1,stickerPage-1);loadStickerDesigns().catch(error=>status(error.message));});$('admin-sticker-next').addEventListener('click',()=>{stickerPage=Math.min(stickerPages,stickerPage+1);loadStickerDesigns().catch(error=>status(error.message));});
$('admin-sticker-search').addEventListener('input',()=>{clearTimeout(stickerSearchTimer);stickerPage=1;stickerRequest+=1;stickerSearchTimer=setTimeout(()=>loadStickerDesigns().catch(error=>status(error.message)),300);});$('admin-sticker-series').addEventListener('change',()=>{stickerPage=1;loadStickerDesigns().catch(error=>status(error.message));});
$('sticker-sheets').addEventListener('toggle',async()=>{if(!$('sticker-sheets').open||$('sticker-sheet-gallery').children.length)return;try{const data=await api('/api/rewards/collections');for(const collection of data.collections){const link=document.createElement('a');link.href=collection.image;link.target='_blank';link.rel='noopener noreferrer';const image=document.createElement('img');image.src=collection.image;image.alt='Lámina de emojis disfrazados · '+collection.name;image.loading='lazy';link.append(image,text('strong',collection.name),text('small',collection.count+' stickers seleccionados'));$('sticker-sheet-gallery').append(link);}}catch(error){status(error.message);}});
$('sticker-manager').addEventListener('toggle',()=>{if($('sticker-manager').open)loadStickerDesigns().catch(error=>status(error.message));});
$('sticker-design-target').addEventListener('change',selectStickerDesign);
async function prepareStickerFile(){const file=$('sticker-design-file').files[0];if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10*1024*1024)throw new Error('Selecciona una imagen PNG, JPG o WebP de hasta 10 MB.');const bitmap=await createImageBitmap(file);try{const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const scale=Math.min(256/bitmap.width,256/bitmap.height);canvas.getContext('2d').drawImage(bitmap,(256-bitmap.width*scale)/2,(256-bitmap.height*scale)/2,bitmap.width*scale,bitmap.height*scale);let value=canvas.toDataURL('image/webp',0.82);if(value.split(',')[1].length>60000)value=canvas.toDataURL('image/webp',0.6);if(value.split(',')[1].length>60000)throw new Error('El diseño es demasiado complejo. Prueba una imagen más sencilla.');$('sticker-design-preview').src=value;$('sticker-design-preview').classList.remove('hidden');return value.split(',')[1];}finally{bitmap.close();}}
$('sticker-design-file').addEventListener('change',()=>{prepareStickerFile().catch(error=>{$('sticker-design-status').textContent=error.message;});});
$('sticker-design-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;$('sticker-design-status').textContent='Guardando diseño…';try{const image=await prepareStickerFile();const id=$('sticker-design-target').value;await api('/api/admin/stickers',{id,name:$('sticker-design-name').value,points:Number($('sticker-design-points').value),image});await loadStickerDesigns();$('sticker-design-status').textContent='Diseño guardado. Ya aparece en el álbum y en los comentarios para quienes lo tengan desbloqueado.';window.dispatchEvent(new Event('ol:designs-updated'));}catch(error){$('sticker-design-status').textContent=error.message;}finally{button.disabled=false;}});
let liveDirectoryPage=1;
async function loadLiveDirectory(){const data=await api('/api/admin/live-channels?page='+liveDirectoryPage);liveDirectoryPage=data.page;$('admin-live-page').textContent=`Página ${data.page} de ${data.pages} · ${data.total} canales`;$('admin-live-prev').disabled=data.page<=1;$('admin-live-next').disabled=data.page>=data.pages;$('admin-live-channels').replaceChildren();for(const channel of data.channels){const row=document.createElement('article');const button=text('button',channel.featured?'Quitar destacado':'Destacar canal');button.type='button';button.addEventListener('click',async()=>{button.disabled=true;try{await api('/api/admin/live-channels/feature',{channel_id:channel.id,featured:!channel.featured});await loadLiveDirectory();}catch(error){status(error.message);}finally{button.disabled=false;}});row.append(text('strong',channel.title+' · '+channel.username),text('p',(data.categories[channel.category]||'Entretenimiento')+' · '+(channel.live?'En directo':'Sin emisión')),button);$('admin-live-channels').append(row);}}
$('live-directory-admin').addEventListener('toggle',()=>{if($('live-directory-admin').open)loadLiveDirectory().catch(error=>status(error.message));});$('admin-live-prev').addEventListener('click',()=>{liveDirectoryPage-=1;loadLiveDirectory().catch(error=>status(error.message));});$('admin-live-next').addEventListener('click',()=>{liveDirectoryPage+=1;loadLiveDirectory().catch(error=>status(error.message));});
function renderCalendar() {
  const [year, month] = $('calendar-month').value.split('-').map(Number);
  if (!year || !month) return;
  const container = $('payment-calendar'); container.replaceChildren();
  for (const day of ['L','M','X','J','V','S','D']) {const label=text('div',day);label.className='day-heading';container.append(label);}
  const first = (new Date(year,month-1,1).getDay()+6)%7;
  for(let index=0; index<first; index++) container.append(document.createElement('div'));
  for(let day=1; day<=new Date(year,month,0).getDate(); day++) {
    const cell=text('div',String(day)); cell.className='day';
    for(const member of members) {
      if (!member.access_until || member.role==='admin' || member.complimentary) continue;
      if(member.streamer_until){const streamDue=new Date(member.streamer_until);if(streamDue.getFullYear()===year&&streamDue.getMonth()===month-1&&streamDue.getDate()===day){const label=text('span',`${member.username} · vence Ol Live Creador`);label.className='due';cell.append(label);}}
      const due=new Date(member.access_until);
      if(due.getFullYear()===year && due.getMonth()===month-1 && due.getDate()===day){const label=text('span',`${member.username} · vence`);label.className='due';cell.append(label);}
    }
    for (const payment of payments) {
      const paid=new Date(payment.verified_at);
      if(paid.getFullYear()===year && paid.getMonth()===month-1 && paid.getDate()===day){const label=text('span',`${payment.username} · ${(payment.amount_cents/100).toFixed(0)} € confirmado`);label.className='due paid';cell.append(label);}
    }
    container.append(cell);
  }
}
const today=new Date(); $('calendar-month').value=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}`;
$('calendar-month').addEventListener('change',renderCalendar);
for (const [id,endpoint] of [['login-form','login'],['register-form','register'],['invite-form','accept-invite']]) {
  $(id).addEventListener('submit',async event=>{event.preventDefault(); const button=$(id).querySelector('button');button.disabled=true; try {const data=Object.fromEntries(new FormData($(id)));if(endpoint==='accept-invite')data.token=inviteToken;await api(`/api/account/${endpoint}`,data);if(endpoint==='accept-invite'){location.assign('/account');return;}$(id).reset();await refresh();if((endpoint==='login'||endpoint==='register')&&streamReturn&&current){location.assign(streamReturn);return;}status('Sesión iniciada.');}catch(error){status(error.message);if(endpoint==='login'&&error.code==='two_factor_required'){$('login-second-factor').classList.remove('hidden');$('login-form').querySelector('[name=otp]').focus();}}finally{button.disabled=false;}});
}
$('logout').addEventListener('click',async()=>{try{await api('/api/account/logout',{});location.assign('/account');}catch(error){status(error.message);}});
$('create-invite').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/admin/invite',Object.fromEntries(new FormData(event.target)));const link=text('a',`${location.origin}${result.path}`);link.href=result.path;$('invite-result').replaceChildren(text('span','Acceso gratuito incluido. Comparte esta invitación privada con tu amigo (48 horas para aceptarla): '),link);event.target.reset();await loadAdmin();}catch(error){status(error.message);}});
window.OlAccountReady=refresh().then(()=>{if(streamReturn&&current)location.assign(streamReturn);}).catch(error=>status(error.message));

if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(()=>{});

async function loadStatistics(){
 if(current?.role!=='admin')return;
 const button=$('refresh-statistics');button.disabled=true;
 try{
  const d=await api('/api/admin/statistics'),money=n=>new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(n/100);
  const cards=[['En línea ahora',d.online.total],['Con cuenta en línea',d.online.members],['Visitantes en línea',d.online.guests],['Clientes registrados',d.accounts.registered],['Registros · últimos 7 días',d.accounts.new_week],['Periodos pagados vigentes',d.accounts.paid_active],['Amigos con acceso gratuito',d.friends],['Fundadores activos',d.founders],['Canales creados',d.channels],['Emisiones activas',d.live],['Pagos confirmados',d.payments.count],['Importe confirmado · total',money(d.payments.total_cents)],['Importe confirmado · mes UTC',money(d.payments.month_cents)],['Correos pendientes o fallidos',d.pending_notifications],['Presentación · mostrada',d.promotion?.shown||0],['Presentación · siguiente',d.promotion?.next||0],['Presentación · omitida',d.promotion?.skip||0],['Presentación · completada',d.promotion?.complete||0]];
  $('statistics-cards').replaceChildren(...cards.map(([label,value])=>{const card=text('article','');card.append(text('strong',String(value)),text('span',label));return card;}));
  $('statistics-days').replaceChildren(...d.days.map(day=>{const row=text('tr','');for(const value of [day.day,day.registrations,day.payments,money(day.cents)])row.append(text('td',String(value)));return row;}));
  $('statistics-status').textContent='Actualizado: '+date(d.updated_at)+'. En línea: actividad reciente de 90 segundos; cuentas únicas y visitantes por navegador. Las categorías de acceso pueden coincidir.';
 }catch(error){$('statistics-status').textContent='No se pudieron actualizar las estadísticas. '+error.message;}finally{button.disabled=false;}
}
$('refresh-statistics').addEventListener('click',loadStatistics);
setInterval(()=>{if(!document.hidden&&current?.role==='admin')loadStatistics();},60000);

$('trial-start').addEventListener('click',async()=>{if(!current){document.querySelector('#login-form input').focus();return;}if(!current.founder_number){document.getElementById('founders').scrollIntoView({behavior:'smooth'});if(window.OlFounders)await window.OlFounders.begin();else location.assign('/live#founders');return;}try{await api('/api/account/live-trial',{});await refresh();status('Tu prueba de siete días de Ol Live ya está activa y tu plaza está reservada.');}catch(error){status(error.message);}});

let founderActivityPage=1;
async function loadFounderActivity(){try{const d=await api('/api/admin/founders/activity?page='+founderActivityPage);$('founder-activity-page').textContent=`Página ${d.page} de ${d.pages} · ${d.total} plazas`;$('founder-activity-prev').disabled=d.page<=1;$('founder-activity-next').disabled=d.page>=d.pages;const list=$('admin-founder-activity');list.replaceChildren();if(!d.founders.length)list.append(text('p','Todavía no hay plazas reservadas.'));for(const f of d.founders){const a=f.activity,card=text('article','');card.className='founder-activity-card';card.append(text('strong',`N.º ${f.number} · ${f.username}`),text('p',`${f.revoked_at?'Desactivada':a.eligible?'En periodo inicial o con actividad suficiente':'Actividad pendiente de revisión'} · ${Math.floor(a.recent_seconds/60)}/120 min en los últimos 30 días · primer directo: ${a.qualified?'completado':'pendiente'}`),text('p','Plazo inicial o ampliado: '+(a.qualification_until?date(a.qualification_until):'empieza al activarse realmente el vídeo de Ol Live')));if(!f.revoked_at){const b=text('button','Ampliar plazo por incidencia');b.type='button';b.addEventListener('click',async()=>{b.disabled=true;try{await api('/api/admin/founders/grace',{member_id:f.member_id,days:Number($('founder-grace-days').value)});await loadFounderActivity();$('founder-activity-status').textContent='Plazo de actividad ampliado. El vencimiento de pago de la plaza no cambia.';}catch(e){$('founder-activity-status').textContent=e.message;}finally{b.disabled=false;}});card.append(b);}list.append(card);}}catch(e){$('founder-activity-status').textContent=e.message;}}
$('founder-activity-admin').addEventListener('toggle',()=>{if($('founder-activity-admin').open)loadFounderActivity();});
$('founder-activity-prev').addEventListener('click',()=>{founderActivityPage=Math.max(1,founderActivityPage-1);loadFounderActivity();});
$('founder-activity-next').addEventListener('click',()=>{founderActivityPage++;loadFounderActivity();});

let slotHistoryPage=1;
async function loadSlotHistory(){try{const d=await api('/api/admin/founders/history?page='+slotHistoryPage);$('slot-history-page').textContent=`Página ${d.page} de ${d.pages} · ${d.total} liberaciones`;$('slot-history-prev').disabled=d.page<=1;$('slot-history-next').disabled=d.page>=d.pages;$('slot-history-list').replaceChildren();if(!d.history.length)$('slot-history-list').append(text('p','Todavía no hay plazas liberadas.'));for(const h of d.history)$('slot-history-list').append(text('p',`N.º ${h.number} · ${h.username} · prueba vencida ${date(h.trial_until)} · liberada ${date(h.released_at)} por falta de pago confirmado.`));}catch(e){$('slot-history-list').textContent=e.message;}}
$('founder-slot-history').addEventListener('toggle',()=>{if($('founder-slot-history').open)loadSlotHistory();});
$('slot-history-prev').addEventListener('click',()=>{slotHistoryPage=Math.max(1,slotHistoryPage-1);loadSlotHistory();});
$('slot-history-next').addEventListener('click',()=>{slotHistoryPage++;loadSlotHistory();});
