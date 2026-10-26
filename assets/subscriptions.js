/* Creator subscriptions: explicit agreement, managed checkout, legacy receipts. */
const $=id=>document.getElementById(id);
const node=(tag,value)=>{const e=document.createElement(tag);e.textContent=value;return e;};
const money=c=>new Intl.NumberFormat('es-ES',{style:'currency',currency:'EUR'}).format(c/100);
const period=p=>p==='month'?'un mes, renovación manual':'pago único al creador';
const date=v=>v?new Date(v).toLocaleDateString('es-ES'):'Sin vencimiento';
let reviewer=null,reviewPage=1,creator=null,memberPage=1;
async function api(path,data){
 let options={};
 if(data!==undefined){const r=await fetch('/api/account/me',{cache:'no-store'});if(!r.ok)throw Error('No se pudo comprobar la sesión.');const auth=await r.json();options={method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':auth.csrf},body:JSON.stringify(data)};}
 const r=await fetch(path,options),d=await r.json();if(!r.ok)throw Error(d.error||'No se pudo completar la operación.');return d;
}
function cents(v){const value=String(v).trim().replace(',','.');if(!/^\d{1,6}(?:\.\d{1,2})?$/.test(value))throw Error('Indica euros con hasta dos decimales.');return Math.round(Number(value)*100);}
function card(a,benefits){const e=node('article','');e.className='subscription-agreement-card';e.append(node('h3',(a.title||'Canal')+' · '+(a.creator_name||'')),node('strong','Versión '+a.version+' · '+money(a.price_cents)+' · '+period(a.period)),node('p',a.benefits.map(b=>benefits[b]||b).join(' · ')),node('p','Creador: '+(a.approvals.creator?'aprobado':'pendiente')+' · Administración: '+(a.approvals.admin?'aprobado':'pendiente')+' · Gref: '+(a.approvals.moderator?'aprobado':'pendiente')));if(a.payout_account)e.append(node('p','Gestor y destinatario: Stripe · '+a.payout_account));return e;}
export async function openSubscription(id){
 const dialog=$('creator-subscription-dialog');if(!dialog)return;dialog.showModal();$('creator-subscription-details').replaceChildren();$('creator-subscription-status').textContent='Comprobando el acuerdo…';
 try{const d=await api('/api/channel-subscriptions/'+encodeURIComponent(id));$('creator-subscription-title').textContent='Suscripción · '+d.title;const target=$('creator-subscription-details');target.append(node('p',d.subscriber_count+' suscriptores activos'),node('p','Suscripción opcional, distinta del acceso de 25 € a Ol Live. El gestor confirma el pago al creador y descuenta sus comisiones. Ol no añade comisión. La renovación mensual es manual.'));
 if(!d.agreement){$('creator-subscription-status').textContent='No hay precio aprobado por las tres partes. No se ofrecen pagos.';return;}
 target.append(card(d.agreement,d.benefits));if(d.mine.length)target.append(node('p','Tus beneficios: '+d.mine.map(b=>d.benefits[b]).join(' · ')));
 if(d.checkout_available){const button=node('button','Pago seguro · '+money(d.agreement.price_cents));button.type='button';button.addEventListener('click',async()=>{button.disabled=true;try{const result=await api('/api/payments/checkout',{channel_id:id});location.assign(result.url);}catch(e){$('creator-subscription-status').textContent=e.message;button.disabled=false;}});target.append(button);$('creator-subscription-status').textContent='Revisa precio, periodo y beneficios antes de confirmar en el gestor. Volver a Ol no activa el acceso: debe confirmarse el cobro.';}
 else $('creator-subscription-status').textContent='Los pagos no están disponibles para tu cuenta o mientras el vídeo no esté habilitado. Los beneficios adquiridos conservan su periodo.';
 }catch(e){$('creator-subscription-status').textContent=e.message;}
}
$('creator-subscription-close')?.addEventListener('click',()=>$('creator-subscription-dialog').close());
async function reviewStatus(){
 if(!$('subscription-review-panel'))return;
 try{reviewer=await api('/api/channel-subscriptions/reviewer');$('subscription-review-panel').classList.toggle('hidden',!reviewer.admin&&!reviewer.moderator&&!reviewer.supervisor);$('subscription-moderator-admin').classList.toggle('hidden',!reviewer.admin);
 if(reviewer.admin)$('subscription-moderator-status').textContent=reviewer.assigned?'Gref · '+(reviewer.assigned.activated?'cuenta activada y designada':'designado, pendiente de activar su cuenta con la invitación privada'):'Gref todavía no está designado.';
 if(reviewer.admin){$('moderator-review').checked=reviewer.permissions.includes('review_agreements');$('moderator-approve').checked=reviewer.permissions.includes('approve_agreements');}
 if(reviewer.moderator||reviewer.supervisor)$('subscription-review-panel').open=true;if($('subscription-review-panel').open)await review();
 }catch(e){$('subscription-review-status').textContent=e.message;}
}
async function review(){
 try{const d=await api('/api/channel-subscriptions/review?page='+reviewPage);$('subscription-review-list').replaceChildren();$('subscription-review-page').textContent='Página '+d.page+' de '+d.pages+' · '+d.total+' acuerdos';$('subscription-review-prev').disabled=d.page<=1;$('subscription-review-next').disabled=d.page>=d.pages;
 if(!d.agreements.length)$('subscription-review-list').append(node('p','Todavía no hay propuestas.'));
 for(const a of d.agreements){const e=card(a,d.benefits),b=node('button','Aprobar como '+(d.party==='admin'?'administración':d.party==='supervisor'?'supervisión · solo lectura':'Gref'));b.type='button';b.disabled=d.party==='supervisor'||a.approvals[d.party]||a.creator_id===reviewer?.member_id||(d.party==='moderator'&&!reviewer.permissions.includes('approve_agreements'));
 b.addEventListener('click',async()=>{b.disabled=true;try{const r=await api('/api/channel-subscriptions/approve',{agreement_id:a.id,party:d.party});$('subscription-review-status').textContent=r.agreement_activated?'Las tres partes han aprobado. Los términos están publicados; cobrar requiere vídeo y pagos habilitados.':'Tu aprobación está guardada. Faltan las demás partes.';await review();}catch(error){$('subscription-review-status').textContent=error.message;b.disabled=false;}});
 e.append(b);$('subscription-review-list').append(e);}
 }catch(e){$('subscription-review-status').textContent=e.message;}
}
$('subscription-review-panel')?.addEventListener('toggle',()=>{if($('subscription-review-panel').open)review();});
$('subscription-review-refresh')?.addEventListener('click',reviewStatus);
$('subscription-assign-gref')?.addEventListener('click',async()=>{const b=$('subscription-assign-gref');b.disabled=true;try{await api('/api/admin/subscription-moderator',{username:'Gref'});await reviewStatus();}catch(e){$('subscription-review-status').textContent=e.message;}finally{b.disabled=false;}});
$('subscription-review-prev')?.addEventListener('click',()=>{reviewPage=Math.max(1,reviewPage-1);review();});$('subscription-review-next')?.addEventListener('click',()=>{reviewPage++;review();});
async function creatorStatus(){
 if(!$('creator-subscriptions'))return;
 try{await window.MaggySession?.ready;if(!window.MaggySession?.authenticated){$('creator-subscriptions').classList.add('hidden');return;}
 const d=await api('/api/channel-subscriptions/creator');creator=d.channel;$('creator-subscriptions').classList.toggle('hidden',!creator);if(!creator)return;
 $('creator-subscriber-count').textContent=creator.subscriber_count+' suscriptores activos · '+money(creator.gross_confirmed_cents||0)+' en ingresos confirmados. No es un saldo bancario ni el neto después de comisiones.';$('creator-agreement-current').replaceChildren();
 if(d.latest){$('creator-agreement-current').append(card(d.latest,d.benefits));$('creator-offer-approve').classList.toggle('hidden',d.latest.approvals.creator);$('creator-offer-approve').dataset.agreement=d.latest.id;}
 else{$('creator-agreement-current').append(node('p','Propón un precio y sus beneficios. Aún no hay tarifa.'));$('creator-offer-approve').classList.add('hidden');}
 $('creator-chat-exclusive').checked=Boolean(d.settings.subscriber_chat);$('creator-live-exclusive').checked=Boolean(d.settings.exclusive_live);
 }catch(e){$('creator-offer-status').textContent=e.message;}
}
$('creator-offer-form')?.addEventListener('submit',async e=>{e.preventDefault();const b=e.target.querySelector('button');b.disabled=true;try{await api('/api/channel-subscriptions/propose',{price_cents:cents($('creator-offer-price').value),period:$('creator-offer-period').value,benefits:[...document.querySelectorAll('[name=creator-benefit]:checked')].map(i=>i.value)});$('creator-offer-status').textContent='Propuesta guardada. Cada parte debe aprobar esta versión expresamente.';await creatorStatus();}catch(error){$('creator-offer-status').textContent=error.message;}finally{b.disabled=false;}});
$('creator-offer-approve')?.addEventListener('click',async()=>{try{await api('/api/channel-subscriptions/approve',{agreement_id:$('creator-offer-approve').dataset.agreement,party:'creator'});await creatorStatus();$('creator-offer-status').textContent='Tu aprobación está guardada. Faltan administración y Gref.';}catch(e){$('creator-offer-status').textContent=e.message;}});
$('creator-exclusive-form')?.addEventListener('submit',async e=>{e.preventDefault();try{await api('/api/channel-subscriptions/'+creator.id+'/mode',{subscriber_chat:$('creator-chat-exclusive').checked,exclusive_live:$('creator-live-exclusive').checked});$('creator-offer-status').textContent='Modos del canal guardados.';}catch(error){$('creator-offer-status').textContent=error.message;}});
async function members(){if(!creator)return;try{const d=await api('/api/channel-subscriptions/'+creator.id+'/members?page='+memberPage);$('creator-subscribers-rows').replaceChildren(...d.members.map(m=>node('p',m.username+' · '+money(m.amount_cents)+' · '+date(m.starts_at)+' → '+date(m.ends_at))));$('creator-subscribers-page').textContent='Página '+d.page+' de '+d.pages+' · '+d.total+' registros';$('creator-subscribers-prev').disabled=d.page<=1;$('creator-subscribers-next').disabled=d.page>=d.pages;}catch(e){$('creator-offer-status').textContent=e.message;}}
$('creator-subscribers-list')?.addEventListener('toggle',()=>{if($('creator-subscribers-list').open)members();});$('creator-subscribers-prev')?.addEventListener('click',()=>{memberPage=Math.max(1,memberPage-1);members();});$('creator-subscribers-next')?.addEventListener('click',()=>{memberPage++;members();});
window.addEventListener('ol:account-refreshed',reviewStatus);window.addEventListener('ol:channel-saved',creatorStatus);
await(window.MaggySession?.ready||window.OlAccountReady);reviewStatus();creatorStatus();

async function saveModeratorPermissions(permissions){try{await api('/api/admin/moderator-permissions',{permissions});await reviewStatus();$('moderator-permissions-status').textContent=permissions.length?'Permisos guardados.':'Todos los permisos retirados.';}catch(e){$('moderator-permissions-status').textContent=e.message;}}
$('moderator-permissions-form')?.addEventListener('submit',e=>{e.preventDefault();saveModeratorPermissions([$ ('moderator-review').checked?'review_agreements':null,$('moderator-approve').checked?'approve_agreements':null].filter(Boolean));});
$('moderator-revoke-all')?.addEventListener('click',()=>saveModeratorPermissions([]));
$('moderator-approve')?.addEventListener('change',()=>{if($('moderator-approve').checked)$('moderator-review').checked=true;});
$('moderator-review')?.addEventListener('change',()=>{if(!$('moderator-review').checked)$('moderator-approve').checked=false;});
