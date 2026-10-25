'use strict';
const $ = id => document.getElementById(id);
let csrf = '', current = null, members = [], payments = [],memberPage=1,invitationPage=1;
const requestedReturn=new URLSearchParams(location.search).get('next');
const streamReturn=(['/streamers','/streamers#stream-studio','/streamers#creator-panel','/streamers#live-catalogue'].includes(requestedReturn)||/^\/streamers#canal-[a-f0-9]{32}$/.test(requestedReturn||''))?requestedReturn:null;
const inviteToken = new URLSearchParams(location.hash.slice(1)).get('invite');
if (inviteToken) { history.replaceState(null, '', '/account'); $('invitation').classList.remove('hidden'); $('credentials').classList.add('hidden'); }
const date = value => value ? new Date(value).toLocaleString('es-ES', {dateStyle:'medium',timeStyle:'short'}) : 'Sin activar';
const text = (tag, value) => { const node = document.createElement(tag); node.textContent = value; return node; };
function status(value) { $('account-status').textContent = value; }
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'No se pudo completar la operación.');
  return result;
}
async function refresh() {
  const data = await api('/api/account/me'); csrf = data.csrf; current = data.user;
  $('credentials').classList.toggle('hidden', Boolean(current) || Boolean(inviteToken));
  $('member-panel').classList.toggle('hidden', !current);
  $('admin-panel').classList.toggle('hidden', current?.role !== 'admin');
  const streamReady=Boolean(data.streamer_available);
  $('streamer-availability').textContent=streamReady?'8 € por un mes de emisión y funciones de Ol. Empieza al confirmar el pago; sin renovación automática.':'El plan Streamer todavía no está disponible para contratar. No se cobran los 8 € hasta activar las emisiones.';
  $('pay-streamer').classList.toggle('hidden',!streamReady);
  if(streamReady)$('pay-streamer').href='https://paypal.me/IMarcosIlla/8EUR';else $('pay-streamer').removeAttribute('href');
  $('streamer-plan-option').disabled=!streamReady;
  $('streamer-plan-option').textContent=streamReady?'8 € · Streamer · Un mes':'8 € · Streamer · pendiente de activar emisión';
  if (!current) return;
  $('member-title').textContent = `Tu cuenta · ${current.username}`;
  $('access-status').textContent = current.role === 'admin' ? 'Administrador: acceso de gestión activo en todos tus dispositivos.' : current.complimentary ? 'Invitado por administración: acceso gratuito. No necesitas pagar para escuchar música.' : current.active ? `Acceso activo hasta ${date(current.access_until)}.` : 'Acceso musical bloqueado. Se requiere un pago comprobado para activar o renovar tu cuenta.';
  $('enter-maggy').classList.toggle('hidden', !current.active);
  $('enter-streamers').classList.toggle('hidden',!current.active);
  $('enter-streamers').textContent=current.streamer_active?'Entrar a mi estudio ↗':'Ver directos ↗';
  $('enter-streamers').href=current.streamer_active?'/streamers#stream-studio':'/streamers#live-catalogue';
  $('pricing').classList.toggle('hidden',Boolean(current.complimentary));
  $('welcome-plan').classList.toggle('hidden', Boolean(current.welcome_used));
  $('next-payment').textContent = current.role === 'admin' ? 'Tu cuenta de gestión no tiene vencimiento de cliente.' : current.complimentary ? 'Acceso gratuito sin vencimiento, hasta que el administrador lo retire. No tienes un próximo pago obligatorio. Streamer y los servicios externos conservan sus condiciones propias.' : current.access_until ? `Vencimiento de Ol: ${date(current.access_until)}. ${current.streamer_until ? 'Streamer hasta '+date(current.streamer_until)+'. Renovación Streamer: 8 € por un mes; Ol normal: 6 €.' : 'Para continuar: 6 € por un mes.'} Sin cargo automático.` : 'Primer acceso: 1 € por 14 días. Comienza cuando se confirme el pago.';
  $('my-payments').replaceChildren();
  for (const payment of data.payments) {
    const row = document.createElement('tr');
    for (const value of [payment.plan === 'welcome' ? 'Bienvenida' : payment.plan === 'streamer' ? 'Streamer' : 'Mensual', `${(payment.amount_cents/100).toFixed(2)} €`, date(payment.starts_at), date(payment.ends_at), date(payment.verified_at)]) row.append(text('td', value));
    $('my-payments').append(row);
  }
  if (current.role === 'admin') await loadAdmin();
}
async function loadAdmin() {
  const data = await api('/api/admin/members'); members = data.members; payments = data.payments;
  $('payment-member').replaceChildren();
  for(const member of members){if(member.role!=='admin'){const option=text('option',member.username);option.value=member.id;$('payment-member').append(option);}}
  renderMembers();
  if($('invitation-history').open)await loadInvitations();
  $('admin-payments').replaceChildren();
  for (const payment of payments) {
    const row=document.createElement('tr');
    for (const value of [payment.username, payment.plan==='welcome'?'Bienvenida':payment.plan==='streamer'?'Streamer':'Mensual',`${(payment.amount_cents/100).toFixed(2)} €`,payment.reference,date(payment.verified_at),date(payment.ends_at)]) row.append(text('td',value));
    $('admin-payments').append(row);
  }
  renderCalendar();
}
function renderMembers(){
  const clients=members.filter(member=>member.role!=='admin');
  $('admin-counters').textContent=`${clients.length} clientes · ${clients.filter(member=>member.active).length} con acceso · ${clients.filter(member=>member.complimentary).length} amigos gratuitos`;
  const query=$('admin-member-search').value.trim().toLowerCase();const matches=members.filter(member=>member.username.toLowerCase().includes(query));
  const pages=Math.max(1,Math.ceil(matches.length/25));memberPage=Math.min(memberPage,pages);
  $('member-page').textContent=`Página ${memberPage} de ${pages} · ${matches.length} cuentas`;
  $('members-prev').disabled=memberPage===1;$('members-next').disabled=memberPage===pages;
  $('admin-members').replaceChildren();
  for (const member of matches.slice((memberPage-1)*25,memberPage*25)) {
    const row = document.createElement('tr');
    for (const value of [member.username, member.role === 'admin' ? 'Administrador' : member.complimentary ? 'Amigo · gratuito' : member.streamer_active ? 'Streamer' : 'Cliente', member.active ? 'Activo' : 'Sin acceso', member.complimentary ? 'Sin vencimiento · invitación gratuita' : member.streamer_until ? `Ol: ${date(member.access_until)} · Streamer: ${date(member.streamer_until)}` : date(member.access_until)]) row.append(text('td', value));
    const actions = document.createElement('td');
    if (member.role !== 'admin') {
      const friend=text('button',member.complimentary?'Retirar acceso gratuito':'Dar acceso gratuito');friend.type='button';
      friend.addEventListener('click',async()=>{friend.disabled=true;try{await api('/api/admin/friend-access',{member_id:member.id,active:!member.complimentary});await refresh();status(member.complimentary?'Acceso gratuito retirado. Se conserva cualquier periodo ya pagado.':'Acceso gratuito concedido sin registrar ningún pago.');}catch(error){status(error.message);}finally{friend.disabled=false;}});actions.append(friend);
      const revoke = text('button', 'Revocar acceso'); revoke.type='button';
      revoke.addEventListener('click', async () => { if (!confirm(`¿Revocar el acceso de ${member.username}?`)) return; try { await api('/api/admin/revoke', {member_id:member.id}); await refresh(); status('Acceso revocado y sesiones cerradas.'); } catch(error){status(error.message);} }); actions.append(revoke);
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
let stickerDesigns=[];
function selectStickerDesign(){const item=stickerDesigns.find(item=>item.id===$('sticker-design-target').value);$('sticker-design-points').disabled=Boolean(item);$('sticker-design-points').value=item?.points||0;$('sticker-design-name').value=item?.name||'';}
async function loadStickerDesigns(){const data=await api('/api/admin/stickers');stickerDesigns=data.stickers;const selected=$('sticker-design-target').value;$('sticker-design-target').replaceChildren();const fresh=text('option','Crear un sticker nuevo');fresh.value='';$('sticker-design-target').append(fresh);$('admin-sticker-list').replaceChildren();for(const item of stickerDesigns){const option=text('option',`N.º ${item.number} · ${item.name} · ${item.points} puntos`);option.value=item.id;$('sticker-design-target').append(option);const card=document.createElement('article');card.className='collection-sticker unlocked';const img=document.createElement('img');img.src=item.image;img.alt=item.name;img.loading='lazy';const button=text('button','Editar diseño');button.type='button';button.addEventListener('click',()=>{$('sticker-design-target').value=item.id;selectStickerDesign();$('sticker-design-form').scrollIntoView({behavior:'smooth'});});card.append(img,text('strong',`N.º ${item.number} · ${item.name}`),text('small',item.points===0?'Gratuito':item.points+' puntos'),button);$('admin-sticker-list').append(card);}$('sticker-design-target').value=selected;selectStickerDesign();}
$('sticker-manager').addEventListener('toggle',()=>{if($('sticker-manager').open)loadStickerDesigns().catch(error=>status(error.message));});
$('sticker-design-target').addEventListener('change',selectStickerDesign);
async function prepareStickerFile(){const file=$('sticker-design-file').files[0];if(!file||!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>10*1024*1024)throw new Error('Selecciona una imagen PNG, JPG o WebP de hasta 10 MB.');const bitmap=await createImageBitmap(file);try{const canvas=document.createElement('canvas');canvas.width=canvas.height=256;const scale=Math.min(256/bitmap.width,256/bitmap.height);canvas.getContext('2d').drawImage(bitmap,(256-bitmap.width*scale)/2,(256-bitmap.height*scale)/2,bitmap.width*scale,bitmap.height*scale);let value=canvas.toDataURL('image/webp',0.82);if(value.split(',')[1].length>60000)value=canvas.toDataURL('image/webp',0.6);if(value.split(',')[1].length>60000)throw new Error('El diseño es demasiado complejo. Prueba una imagen más sencilla.');$('sticker-design-preview').src=value;$('sticker-design-preview').classList.remove('hidden');return value.split(',')[1];}finally{bitmap.close();}}
$('sticker-design-file').addEventListener('change',()=>{prepareStickerFile().catch(error=>{$('sticker-design-status').textContent=error.message;});});
$('sticker-design-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;$('sticker-design-status').textContent='Guardando diseño…';try{const image=await prepareStickerFile();const id=$('sticker-design-target').value;await api('/api/admin/stickers',{id,name:$('sticker-design-name').value,points:Number($('sticker-design-points').value),image});await loadStickerDesigns();$('sticker-design-status').textContent='Diseño guardado. Ya aparece en el álbum y en los comentarios para quienes lo tengan desbloqueado.';window.dispatchEvent(new Event('ol:designs-updated'));}catch(error){$('sticker-design-status').textContent=error.message;}finally{button.disabled=false;}});
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
      if(member.streamer_until){const streamDue=new Date(member.streamer_until);if(streamDue.getFullYear()===year&&streamDue.getMonth()===month-1&&streamDue.getDate()===day){const label=text('span',`${member.username} · vence Streamer`);label.className='due';cell.append(label);}}
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
  $(id).addEventListener('submit',async event=>{event.preventDefault(); const button=$(id).querySelector('button');button.disabled=true; try {const data=Object.fromEntries(new FormData($(id)));if(endpoint==='accept-invite')data.token=inviteToken;await api(`/api/account/${endpoint}`,data);if(endpoint==='accept-invite'){location.assign('/account');return;}$(id).reset();await refresh();if(endpoint==='login'&&streamReturn&&current?.active){location.assign(streamReturn);return;}status('Sesión iniciada.');}catch(error){status(error.message);}finally{button.disabled=false;}});
}
$('logout').addEventListener('click',async()=>{try{await api('/api/account/logout',{});location.assign('/account');}catch(error){status(error.message);}});
$('create-invite').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/admin/invite',Object.fromEntries(new FormData(event.target)));const link=text('a',`${location.origin}${result.path}`);link.href=result.path;$('invite-result').replaceChildren(text('span','Acceso gratuito incluido. Comparte esta invitación privada con tu amigo (48 horas para aceptarla): '),link);event.target.reset();await loadAdmin();}catch(error){status(error.message);}});
$('payment-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{const result=await api('/api/admin/confirm-payment',Object.fromEntries(new FormData(event.target)));status(`Pago registrado. Acceso hasta ${date(result.access_until)}.`);event.target.reset();await refresh();}catch(error){status(error.message);}finally{button.disabled=false;}});
window.OlAccountReady=refresh().then(()=>{if(streamReturn&&current?.active)location.assign(streamReturn);}).catch(error=>status(error.message));

if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(()=>{});
