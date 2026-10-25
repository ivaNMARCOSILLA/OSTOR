'use strict';
const $ = id => document.getElementById(id);
let csrf = '', current = null, members = [], payments = [];
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
  if (!current) return;
  $('member-title').textContent = `Tu cuenta · ${current.username}`;
  $('access-status').textContent = current.role === 'admin' ? 'Administrador: acceso de gestión activo en todos tus dispositivos.' : current.active ? `Acceso activo hasta ${date(current.access_until)}.` : 'Acceso musical bloqueado. Se requiere un pago comprobado para activar o renovar tu cuenta.';
  $('enter-maggy').classList.toggle('hidden', !current.active);
  $('welcome-plan').classList.toggle('hidden', Boolean(current.welcome_used));
  $('next-payment').textContent = current.role === 'admin' ? 'Tu cuenta de gestión no tiene vencimiento de cliente.' : current.access_until ? `Vencimiento: ${date(current.access_until)}. Para continuar: 6 € por un mes; sin cargo automático.` : 'Primer acceso: 1 € por 14 días. Comienza cuando se confirme el pago.';
  $('my-payments').replaceChildren();
  for (const payment of data.payments) {
    const row = document.createElement('tr');
    for (const value of [payment.plan === 'welcome' ? 'Bienvenida' : 'Mensual', `${(payment.amount_cents/100).toFixed(2)} €`, date(payment.starts_at), date(payment.ends_at), date(payment.verified_at)]) row.append(text('td', value));
    $('my-payments').append(row);
  }
  if (current.role === 'admin') await loadAdmin();
}
async function loadAdmin() {
  const data = await api('/api/admin/members'); members = data.members; payments = data.payments;
  $('payment-member').replaceChildren(); $('admin-members').replaceChildren();
  for (const member of members) {
    if (member.role !== 'admin') { const option = text('option', member.username); option.value = member.id; $('payment-member').append(option); }
    const row = document.createElement('tr');
    for (const value of [member.username, member.role === 'admin' ? 'Administrador' : 'Cliente', member.active ? 'Activo' : 'Sin acceso', date(member.access_until)]) row.append(text('td', value));
    const actions = document.createElement('td');
    if (member.role !== 'admin') {
      const revoke = text('button', 'Revocar acceso'); revoke.type='button';
      revoke.addEventListener('click', async () => { if (!confirm(`¿Revocar el acceso de ${member.username}?`)) return; try { await api('/api/admin/revoke', {member_id:member.id}); await refresh(); status('Acceso revocado y sesiones cerradas.'); } catch(error){status(error.message);} }); actions.append(revoke);
    }
    row.append(actions); $('admin-members').append(row);
  }
  $('admin-payments').replaceChildren();
  for (const payment of payments) {
    const row=document.createElement('tr');
    for (const value of [payment.username, payment.plan==='welcome'?'Bienvenida':'Mensual',`${(payment.amount_cents/100).toFixed(2)} €`,payment.reference,date(payment.verified_at),date(payment.ends_at)]) row.append(text('td',value));
    $('admin-payments').append(row);
  }
  renderCalendar();
}
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
      if (!member.access_until || member.role==='admin') continue;
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
  $(id).addEventListener('submit',async event=>{event.preventDefault(); const button=$(id).querySelector('button');button.disabled=true; try {const data=Object.fromEntries(new FormData($(id)));if(endpoint==='accept-invite')data.token=inviteToken;await api(`/api/account/${endpoint}`,data);if(endpoint==='accept-invite'){location.assign('/account');return;}$(id).reset();await refresh();status('Sesión iniciada.');}catch(error){status(error.message);}finally{button.disabled=false;}});
}
$('logout').addEventListener('click',async()=>{try{await api('/api/account/logout',{});location.assign('/account');}catch(error){status(error.message);}});
$('create-invite').addEventListener('submit',async event=>{event.preventDefault();try{const result=await api('/api/admin/invite',Object.fromEntries(new FormData(event.target)));const link=text('a',`${location.origin}${result.path}`);link.href=result.path;$('invite-result').replaceChildren(text('span','Comparte esta invitación privada con tu amigo (48 horas): '),link);event.target.reset();await loadAdmin();}catch(error){status(error.message);}});
$('payment-form').addEventListener('submit',async event=>{event.preventDefault();const button=event.target.querySelector('button');button.disabled=true;try{const result=await api('/api/admin/confirm-payment',Object.fromEntries(new FormData(event.target)));status(`Pago registrado. Acceso hasta ${date(result.access_until)}.`);event.target.reset();await refresh();}catch(error){status(error.message);}finally{button.disabled=false;}});
refresh().catch(error=>status(error.message));

if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(()=>{});
