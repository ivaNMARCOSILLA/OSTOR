'use strict';
await window.MaggySession.ready;
const storageKey = name => window.MaggySession ? window.MaggySession.key(name) : name;
const $ = id => document.getElementById(id);
function applyProfile(profile) {
  delete document.documentElement.dataset.ambience;
  $('profile-name').value = String(profile.name || '').slice(0, 40);
  $('space-status').textContent = profile.name ? `Bienvenido a tu estación, ${String(profile.name).slice(0, 40)}.` : 'Tu próximo descubrimiento empieza aquí.';
}
try { applyProfile(JSON.parse(localStorage.getItem(storageKey('maggy_profile_v1')) || '{}')); } catch { applyProfile({}); }
$('profile-form').addEventListener('submit', event => {
  event.preventDefault();
  if (window.MaggySession && !window.MaggySession.requireAccess()) return;
  const profile = { name: $('profile-name').value.trim() };
  applyProfile(profile);
  try { localStorage.setItem(storageKey('maggy_profile_v1'), JSON.stringify(profile)); } catch { $('space-status').textContent = 'El navegador no permite guardar tus preferencias.'; }
});
let installPrompt;
window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); installPrompt = event; $('install-app').classList.remove('hidden'); });
$('install-app').addEventListener('click', async () => { if (!installPrompt) return; await installPrompt.prompt(); await installPrompt.userChoice; installPrompt = null; $('install-app').classList.add('hidden'); });
fetch('/health').then(response => { if (!response.ok) throw new Error(); return response.json(); }).then(data => {
  $('provider-status').textContent = 'Fuentes musicales: Internet Archive, Audius y Mezcla (Commons y Radio Browser). La disponibilidad de audio depende de cada proveedor.';
}).catch(() => { $('provider-status').textContent = 'Sin conexión con el servidor. Comprueba tu conexión para buscar y reproducir.'; });
window.addEventListener('offline', () => { $('provider-status').textContent = 'Estás sin conexión. Puedes consultar favoritos guardados; buscar y reproducir requiere internet.'; });

const CHANNEL_KEY = storageKey('maggy_channels_v1');
let channels = [];
try { const saved = JSON.parse(localStorage.getItem(CHANNEL_KEY) || '[]'); if (Array.isArray(saved)) channels = saved.filter(x => typeof x.name === 'string' && Array.isArray(x.tracks)).slice(0, 20); } catch { /* Empty local space */ }
function saveChannels() {
  try { localStorage.setItem(CHANNEL_KEY, JSON.stringify(channels)); return true; }
  catch { $('channel-status').textContent = 'No se pudo guardar: almacenamiento lleno o no disponible.'; return false; }
}
const channelAvailable = track => ['ARCHIVE', 'AUDIUS', 'COMMONS', 'RADIO'].includes(track?.source);
function renderChannels() {
  $('channels-list').replaceChildren();
  for (const channel of channels) {
    const availableTracks = channel.tracks.filter(channelAvailable);
    const card = document.createElement('article'); card.className = 'channel-card';
    const title = document.createElement('h4'); title.textContent = channel.name;
    const count = document.createElement('p'); count.textContent = `${availableTracks.length} pistas · Solo en este navegador`;
    const play = document.createElement('button'); play.type = 'button'; play.className = 'ghost-button'; play.textContent = '▶ Escuchar canal'; play.disabled = availableTracks.length === 0;
    play.addEventListener('click', () => window.dispatchEvent(new CustomEvent('maggy:play', { detail: availableTracks })));
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'ghost-button'; remove.textContent = 'Eliminar';
    remove.setAttribute('aria-label', `Eliminar canal ${channel.name}`);
    remove.addEventListener('click', () => { if (window.MaggySession && !window.MaggySession.requireAccess()) return; const previous = channels; channels = channels.filter(x => x !== channel); if (saveChannels()) renderChannels(); else channels = previous; });
    card.append(title, count, play, remove); $('channels-list').append(card);
  }
  if (!channels.length) $('channels-list').textContent = 'Aún no tienes canales. Marca canciones con ♡ y crea el primero.';
}
$('channel-form').addEventListener('submit', event => {
  event.preventDefault();
  if (window.MaggySession && !window.MaggySession.requireAccess()) return;
  if (channels.length >= 20) { $('channel-status').textContent = 'Puedes guardar hasta 20 canales en este navegador.'; return; }
  let tracks = [];
  try { const saved = JSON.parse(localStorage.getItem(storageKey('electronicama_v7_favorites')) || '[]'); if (Array.isArray(saved)) tracks = saved.filter(x => x && typeof x.id === 'string' && typeof x.title === 'string').slice(0, 160); } catch { /* No saved favorites */ }
  tracks = tracks.filter(channelAvailable);
  if (!tracks.length) { $('channel-status').textContent = 'Primero guarda alguna canción con el corazón ♡.'; return; }
  const name = $('channel-name').value.trim().slice(0, 60);
  if (!name) return;
  channels.push({ name, tracks });
  if (saveChannels()) { renderChannels(); $('channel-form').reset(); $('channel-status').textContent = `Canal «${name}» guardado en este navegador.`; } else channels.pop();
});
renderChannels();

