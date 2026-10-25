/**
 * Ol PRO 8.3.0 · Frontend modular sin compilación ni dependencias.
 * Edición y mantenimiento: Iván Marcos Illa · 2026-10-24.
 * © 2026 Iván Marcos Illa sobre las aportaciones originales de esta edición.
 * Audius, Internet Archive y sus contenidos pertenecen a sus titulares.
 */
'use strict';
await window.MaggySession.ready;
const storageKey = name => window.MaggySession ? window.MaggySession.key(name) : name;

const VERSION = '9.1.0';
const KEY = Object.freeze({ favorites: storageKey('electronicama_v7_favorites'), history: storageKey('electronicama_v7_history'), ads: storageKey('electronicama_ads_consent_v1') });
const MAX_FAVORITES = 160;
const MAX_HISTORY = 75;
const SEARCH_TARGET = 120;
const AUTO_SEARCH_PAGES = 4;
const SOURCE_NAMES = { AUDIUS: 'AUDIUS', ARCHIVE: 'ARCHIVE', COMMONS: 'MEZCLA · COMMONS', RADIO: 'MEZCLA · RADIO EN DIRECTO' };
const byId = id => document.getElementById(id);

const supportedTrack = track => ['ARCHIVE', 'AUDIUS', 'COMMONS', 'RADIO'].includes(track?.source);

const state = {
  view: 'discover', source: 'ALL', query: 'electronic music', page: 1,
  results: [], favorites: readList(KEY.favorites), history: readList(KEY.history),
  mixResults: [], mixQuery: 'piano', mixPage: 1, mixLoading: false, mixRequest: null, mixLoaded: false,
  loading: false, request: null, currentTrack: null, queue: [], currentIndex: -1,
  audio: null, playSerial: 0
};

function readList(key) {
  try {
    const list = JSON.parse(localStorage.getItem(key) || '[]');
    if (!Array.isArray(list)) return [];
    return list.filter(x => x && typeof x === 'object' && typeof x.id === 'string' && typeof x.title === 'string' && supportedTrack(x)).slice(0, 160);
  } catch { return []; }
}
function writeList(key, list) { try { localStorage.setItem(key, JSON.stringify(list)); } catch { message('El almacenamiento local no está disponible.'); } }
function safeImage(src) { try { const url = new URL(src); return url.protocol === 'https:' ? url.href : ''; } catch { return ''; } }
function filteredTracks() {
  const base = state.view === 'favorites' ? state.favorites : state.view === 'history' ? state.history : state.results;
  const available = base.filter(supportedTrack);
  if (state.source === 'MIX') return state.mixResults.filter(supportedTrack);
  return state.source === 'ALL' ? available : available.filter(track => track.source === state.source);
}
function isFavorite(id) { return state.favorites.some(track => track.id === id); }
function message(text) { byId('result-status').textContent = text; }
function setStatus(text) { byId('player-message').textContent = text || ''; }
function emptyNode(tag, className, text) { const node = document.createElement(tag); if (className) node.className = className; if (text !== undefined) node.textContent = String(text); return node; }
function compactTrack(track) {
  const result = {};
  for (const key of ['id', 'title', 'channel', 'description', 'source', 'thumbnail', 'url', 'stream_url', 'mime', 'license', 'license_url', 'attribution', 'page_url']) {
    if (typeof track[key] === 'string') result[key] = track[key].slice(0, 1200);
  }
  return result;
}
function rememberTrack(track) {
  state.history = [compactTrack(track), ...state.history.filter(x => x.id !== track.id)].slice(0, MAX_HISTORY);
  writeList(KEY.history, state.history);
}
function toggleFavorite(track) {
  if (window.MaggySession && !window.MaggySession.requireAccess()) return;
  state.favorites = isFavorite(track.id)
    ? state.favorites.filter(x => x.id !== track.id)
    : [compactTrack(track), ...state.favorites].slice(0, MAX_FAVORITES);
  writeList(KEY.favorites, state.favorites);
  byId('favorites-count').textContent = String(state.favorites.filter(supportedTrack).length);
  if (state.currentTrack) {
    const button = byId('player-favorite');
    button.textContent = isFavorite(state.currentTrack.id) ? '♥' : '♡';
    button.classList.toggle('saved', isFavorite(state.currentTrack.id));
    button.setAttribute('aria-label', isFavorite(state.currentTrack.id) ? 'Quitar de favoritos' : 'Guardar en favoritos');
  }
  render();
}
function maggyCover() {
  const img = document.createElement('img'); img.src = '/assets/app-icon-192.png?v=9.1.0'; img.alt = 'Logo de Ol'; img.loading = 'lazy';
  img.addEventListener('error', () => img.replaceWith(emptyNode('span', 'cover-fallback', 'Ol')), {once:true});
  return img;
}
function cover(src, alt) {
  if (!safeImage(src)) return maggyCover();
  const img = document.createElement('img'); img.src = safeImage(src); img.alt = alt; img.loading = 'lazy'; img.decoding = 'async';
  img.referrerPolicy = 'no-referrer'; img.addEventListener('error', () => img.replaceWith(maggyCover()), {once:true});
  return img;
}
function trackCard(track, list) {
  const card = emptyNode('article', 'track-card');
  const main = emptyNode('button', 'cover-button'); main.type = 'button';
  main.setAttribute('aria-label', `${window.MaggySession?.active === false ? 'Desbloquear' : 'Reproducir'} ${track.title} de ${track.channel || 'artista desconocido'}`);
  main.append(cover(track.thumbnail, `Portada de ${track.title}`), emptyNode('span', 'play-overlay', window.MaggySession?.active === false ? '🔒' : '▶'));
  main.addEventListener('click', () => playTrack(track, list));
  const details = emptyNode('div', 'track-body');
  const top = emptyNode('div', 'track-top');
  top.append(emptyNode('span', 'source-tag', SOURCE_NAMES[track.source] || 'MÚSICA'));
  const fav = emptyNode('button', `save-button${isFavorite(track.id) ? ' saved' : ''}`, window.MaggySession?.active === false ? '🔒' : isFavorite(track.id) ? '♥' : '♡');
  fav.type = 'button'; fav.title = 'Guardar / quitar de favoritos';
  fav.setAttribute('aria-label', isFavorite(track.id) ? `Quitar ${track.title} de favoritos` : `Guardar ${track.title} en favoritos`);
  fav.addEventListener('click', () => toggleFavorite(track));
  top.append(fav);
  if (safeImage(track.url)) { const link = emptyNode('a', 'track-origin', 'Fuente ↗'); link.href = safeImage(track.url); link.target = '_blank'; link.rel = 'noopener noreferrer'; details.append(link); }
  const title = emptyNode('button', 'track-title', track.title);
  title.type = 'button'; title.title = track.title;
  title.addEventListener('click', () => playTrack(track, list));
  const artist = emptyNode('p', 'track-artist', track.channel || 'Artista desconocido');
  details.append(top, title, artist);
  if (['COMMONS', 'RADIO'].includes(track.source)) {
    const credit = emptyNode('details', 'track-credit');
    credit.append(emptyNode('summary', '', track.source === 'RADIO' ? 'Emisora y fuente' : `Autor y licencia · ${track.license || 'Ver fuente'}`), emptyNode('p', '', track.attribution || track.channel));
    for (const [href, label] of [[track.page_url, 'Grabación original ↗'], [track.license_url, 'Licencia ↗']]) {
      if (!safeImage(href)) continue;
      const link = emptyNode('a', '', label); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; credit.append(link);
    }
    details.append(credit);
  }
  card.append(main, details);
  return card;
}
function render() {
  if (window.MaggySession?.active === false && state.view !== 'discover') state.view = 'discover';
  const list = filteredTracks();
  const grid = byId('track-grid');
  grid.replaceChildren();
  grid.classList.toggle('mix-list', state.source === 'MIX');
  byId('mix-intro').classList.toggle('hidden', state.source !== 'MIX');
  byId('play-mix').disabled = list.length === 0;
  const titles = {
    discover: ['Explora el ', 'sonido', 'Explora los sonidos que marcan tu ritmo.'],
    favorites: ['Tus ', 'favoritos', 'Guardados únicamente en este navegador.'],
    history: ['Tu ', 'historial', 'Tu música escuchada recientemente.']
  };
  const [first, emph, subtitle] = state.view === 'discover' && state.source === 'MIX' ? ['TU ', 'MEZCLA', 'Otras fuentes: grabaciones libres y radios en directo · solo audio.'] : titles[state.view];
  const heading = byId('section-title');
  heading.replaceChildren(document.createTextNode(first), emptyNode('em', '', emph));
  byId('section-subtitle').textContent = subtitle;
  byId('results-meta').textContent = `${list.length} ${list.length === 1 ? 'PISTA' : 'PISTAS'}`;
  byId('clear-history').classList.toggle('hidden', state.view !== 'history' || state.history.length === 0);
  byId('quick-searches').classList.toggle('hidden', state.view !== 'discover');
  byId('hero').classList.toggle('hidden', state.view !== 'discover');
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('active', button.dataset.view === state.view);
  });
  document.querySelectorAll('[data-source]').forEach(button => {
    button.classList.toggle('active', button.dataset.source === state.source);
    button.setAttribute('aria-pressed', String(button.dataset.source === state.source));
  });
  byId('result-status').classList.toggle('hidden', state.source === 'MIX');
  if (!list.length && !(state.source === 'MIX' ? state.mixLoading : state.loading)) {
    const empty = emptyNode('div', 'empty-state');
    const title = state.view === 'favorites' ? 'TODAVÍA NO HAY FAVORITOS' : state.view === 'history' ? 'TODAVÍA NO HAY HISTORIAL' : 'SIN RESULTADOS';
    empty.append(emptyNode('strong', '', title), emptyNode('p', '', state.view === 'discover' ? 'Prueba con otro artista, canción o estilo.' : 'Elige una canción y vuelve aquí.'));
    grid.append(empty);
  } else {
    const frag = document.createDocumentFragment();
    for (const track of list) frag.append(trackCard(track, list));
    grid.append(frag);
  }
  byId('load-more').classList.toggle('hidden', state.source === 'MIX' ? !list.length || state.mixPage >= 10 : state.view !== 'discover' || state.results.length === 0 || state.page >= 10);
  if (state.source === 'MIX') byId('load-more').disabled = state.mixLoading;
}
function goView(view) {
  if (!['discover', 'favorites', 'history'].includes(view)) return;
  if (view !== 'discover' && window.MaggySession && !window.MaggySession.requireAccess()) return;
  state.view = view;
  if (view !== 'discover' && state.source === 'MIX') state.source = 'ALL';
  byId('mobile-nav').classList.add('hidden');
  byId('mobile-menu').setAttribute('aria-expanded', 'false');
  message(view === 'favorites' ? 'Tus canciones guardadas en este dispositivo.' : view === 'history' ? 'Las últimas canciones que has escuchado.' : `Explorando: ${state.query}`);
  render();
  byId('library').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
function updateExternalSearch(query) {
  query = String(query || '').trim().replace(/\s+/g, ' ').slice(0, 90);
  const encoded = encodeURIComponent(query);
  const urls = {
    soundcloud: `https://soundcloud.com/search/sounds?q=${encoded}`,
    youtube: `https://www.youtube.com/results?search_query=${encoded}`,
    spotify: `https://open.spotify.com/search/${encoded}`,
    commons: `https://commons.wikimedia.org/w/index.php?title=Special:MediaSearch&type=audio&search=${encoded}`
  };
  document.querySelectorAll('[data-external-search]').forEach(link => {
    if (urls[link.dataset.externalSearch]) link.href = urls[link.dataset.externalSearch];
  });
  byId('directory-query').textContent = query ? `Búsqueda externa: «${query}». SoundCloud, YouTube, Spotify y Commons usarán estas palabras.` : 'Escribe un artista o canción para buscarlo en otras plataformas.';
}
const searchMemory = new Map();
async function requestSearch(query, append = false) {
  if (state.source === 'MIX') return requestMixSearch(query, append);
  query = String(query || '').trim().replace(/\s+/g, ' ').slice(0, 90);
  if (!query) { message('Escribe un artista o una canción.'); return; }
  state.request?.abort();
  const controller = new AbortController(); state.request = controller;
  state.view = 'discover';
  if (!append) { state.query = query; state.page = 1; state.results = []; state.source = state.source === 'MIX' ? 'MIX' : 'ALL'; }
  const page = state.page;
  state.loading = true;
  byId('search-button').disabled = true; byId('load-more').disabled = true;
  byId('search-input').value = query;
  updateExternalSearch(query);
  message(`Buscando «${query}»… Objetivo: al menos 120 coincidencias disponibles.`); render();
  const sources = ['AUDIUS', 'ARCHIVE'];
  let failures = 0, received = 0;
  const deadline = setTimeout(() => controller.abort(), 14000);
  await Promise.allSettled(sources.map(async source => {
    try {
      const key = `${query.toLowerCase()}:${page}:${source}`;
      let data = searchMemory.get(key);
      if (!data || Date.now() - data.time > 60000) {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&page=${page}&source=${source}`, {signal: controller.signal, headers: {Accept: 'application/json'}});
        if (!response.ok) throw new Error('Buscador no disponible');
        const raw = await response.json();
        if (!Array.isArray(raw)) throw new Error('Respuesta no válida');
        data = {time: Date.now(), tracks: raw.filter(supportedTrack)};
        if (data.tracks.length) searchMemory.set(key, data);
        if (searchMemory.size > 30) searchMemory.delete(searchMemory.keys().next().value);
      }
      if (state.request !== controller || controller.signal.aborted) return;
      const seen = new Set(state.results.map(item => item.id));
      const tracks = data.tracks.filter(item => typeof item.id === 'string' && typeof item.title === 'string');
      const fresh = tracks.filter(item => { if (seen.has(item.id)) return false; seen.add(item.id); return true; });
      state.results.push(...fresh);
      received += fresh.length;
      message(`${state.results.length} resultados para «${query}» · buscando al menos 120 coincidencias…`);
      render(); // The first available provider is visible immediately.
    } catch { failures += 1; }
  }));
  clearTimeout(deadline);
  if (state.request !== controller) return;
  state.loading = false; state.request = null;
  byId('search-button').disabled = false; byId('load-more').disabled = false;
  if (append && !received && !failures) state.page = 10;
  if (state.results.length < SEARCH_TARGET && received > 0 && !failures && state.page < AUTO_SEARCH_PAGES) {
    state.page += 1; return requestSearch(query, true);
  }
  message(`${state.results.length} resultados para «${query}»${failures ? '. Una plataforma no respondió; puedes volver a buscar.' : state.results.length < SEARCH_TARGET ? '. No se han encontrado 120 resultados disponibles; puedes ampliar la búsqueda.' : ''}`);
  render();
}

async function requestMixSearch(query = 'piano', append = false) {
  query = String(query).trim().replace(/\s+/g, ' ').slice(0, 90);
  if (!query) return;
  state.mixRequest?.abort();
  const controller = new AbortController(); state.mixRequest = controller;
  if (!append) { state.mixResults = []; state.mixPage = 1; state.mixQuery = query; }
  state.mixLoading = true; state.view = 'discover'; state.source = 'MIX';
  byId('mix-query').value = query; byId('search-input').value = query; updateExternalSearch(query);
  byId('mix-status').textContent = 'Buscando grabaciones libres y emisoras…';
  render();
  const deadline = setTimeout(() => controller.abort(), 14000);
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&page=${state.mixPage}&source=MIX`, {signal: controller.signal});
    if (!response.ok) throw new Error('No se pudo consultar esta fuente. Inténtalo de nuevo.');
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error('La fuente devolvió una respuesta no válida.');
    if (state.mixRequest !== controller) return;
    const seen = new Set(state.mixResults.map(track => track.id));
    const fresh = data.filter(track => { if (!['COMMONS', 'RADIO'].includes(track.source) || seen.has(track.id)) return false; seen.add(track.id); return true; });
    state.mixResults.push(...fresh);
    state.mixLoaded = true;
    if (append && !data.length) state.mixPage = 10;
    if (state.mixResults.filter(track => track.source === 'COMMONS').length < SEARCH_TARGET && fresh.some(track => track.source === 'COMMONS') && state.mixPage < AUTO_SEARCH_PAGES) {
      clearTimeout(deadline); state.mixPage += 1; return requestMixSearch(query, true);
    }
    byId('mix-status').textContent = state.mixResults.length ? `${state.mixResults.length} resultados para «${query}»: grabaciones y emisoras. Consulta la fuente de cada uno.` : 'No hay grabaciones compatibles para esta búsqueda. Prueba piano, Mozart o guitarra.';
  } catch (error) {
    if (state.mixRequest === controller) byId('mix-status').textContent = error.name === 'AbortError' ? 'La fuente tarda en responder. Vuelve a intentarlo.' : error.message;
  } finally {
    clearTimeout(deadline);
    if (state.mixRequest === controller) { state.mixLoading = false; state.mixRequest = null; render(); }
  }
}

let sleepDeadline = 0;
function updateSleepTimer() {
  if (!sleepDeadline) return;
  const remaining = sleepDeadline - Date.now();
  if (remaining <= 0) {
    sleepDeadline = 0;
    state.playSerial += 1; // Cancel a pending resolve so it cannot start after the deadline.
    state.audio?.pause();
    byId('sleep-timer').value = '0';
    byId('sleep-status').textContent = 'Temporizador terminado. Reproducción pausada.';
  } else byId('sleep-status').textContent = `Se pausará en ${Math.ceil(remaining / 60000)} min.`;
}
function seekAudio(offset, absolute = false) {
  const audio = state.audio;
  if (!audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
  audio.currentTime = Math.min(audio.duration, Math.max(0, absolute ? offset : audio.currentTime + offset));
  updateMediaPosition();
}
function updateMediaPosition() {
  const audio = state.audio;
  if (!navigator.mediaSession?.setPositionState || !audio || !Number.isFinite(audio.duration) || audio.duration <= 0) return;
  try { navigator.mediaSession.setPositionState({duration: audio.duration, playbackRate: audio.playbackRate, position: Math.min(audio.duration, Math.max(0, audio.currentTime))}); } catch { /* Optional browser support. */ }
}
function destroyMedia() {
  if (state.audio) { state.audio.pause(); state.audio.removeAttribute('src'); state.audio.load(); state.audio = null; }
  byId('player-media').replaceChildren();
  if ('mediaSession' in navigator) {
    try { navigator.mediaSession.playbackState = 'none'; navigator.mediaSession.metadata = null; navigator.mediaSession.setPositionState?.(); } catch { /* no compatible */ }
  }
}
function playTrack(track, queue = filteredTracks()) {
  if (!track || !track.id) return;
  if (!supportedTrack(track)) { message('Esta fuente ya no está disponible.'); return; }
  state.playSerial += 1;
  if (window.MaggySession && !window.MaggySession.requireAccess()) return;
  // Keep the same native element, and call play() in the tap event on iOS.
  // The paid /api/play endpoint checks access authoritatively on every track.
  state.audio?.pause();
  state.currentTrack = track;
  state.queue = queue.filter(supportedTrack);
  state.currentIndex = Math.max(0, state.queue.findIndex(x => x.id === track.id));
  byId('player').classList.remove('hidden');
  byId('player-title').textContent = track.title;
  byId('player-artist').textContent = `${track.channel || 'Artista'} · ${track.source}`;
  byId('player-art').replaceChildren(cover(track.thumbnail, `Portada de ${track.title}`));
  byId('previous-track').disabled = state.currentIndex <= 0;
  byId('next-track').disabled = state.currentIndex >= state.queue.length - 1;
  byId('player-favorite').textContent = isFavorite(track.id) ? '♥' : '♡';
  byId('player-favorite').classList.toggle('saved', isFavorite(track.id));
  byId('toggle-play').textContent = '▶';
  byId('toggle-play').setAttribute('aria-label', 'Reproducir');
  setStatus('Preparando el audio…');
  startAudio(`/api/play/${encodeURIComponent(track.id)}`);
  render();
}
function startAudio(url) {
  if (!url.startsWith('/api/play/')) { setStatus('Enlace de audio no válido.'); return; }
  let audio = state.audio;
  if (!audio) {
    audio = document.createElement('audio');
    audio.controls = true; audio.setAttribute('playsinline', ''); audio.preload = 'auto';
    audio.addEventListener('ended', () => { const expired = sleepDeadline && Date.now() >= sleepDeadline; updateSleepTimer(); if (!expired) playNext(); });
    audio.addEventListener('timeupdate', updateSleepTimer);
    for (const name of ['loadedmetadata', 'timeupdate', 'ratechange', 'seeked']) audio.addEventListener(name, updateMediaPosition);
    audio.addEventListener('playing', () => {
      byId('toggle-play').textContent = 'Ⅱ'; byId('toggle-play').setAttribute('aria-label', 'Pausar');
      if (state.currentTrack) rememberTrack(state.currentTrack);
      setStatus('Reproduciendo'); mediaSessionPlayback('playing');
    });
    audio.addEventListener('waiting', () => setStatus('Cargando audio…'));
    audio.addEventListener('pause', () => {
      byId('toggle-play').textContent = '▶'; byId('toggle-play').setAttribute('aria-label', 'Reproducir');
      mediaSessionPlayback('paused');
    });
    audio.addEventListener('error', async () => {
      if (state.audio !== audio || !state.currentTrack) return;
      if (!state.audioRetries) {
        state.audioRetries = 1;
        setStatus('Probando una conexión alternativa…');
        audio.src = `/api/play/${encodeURIComponent(state.currentTrack.id)}?retry=1`;
        audio.play().catch(playbackRejected);
        return;
      }
      const serial = state.playSerial;
      const active = await window.MaggySession.verifyAccess();
      if (serial === state.playSerial && active) setStatus('Esta pista no responde o no permite reproducción. Pulsa ▶ para reintentar o elige otra.');
    });
    state.audio = audio;
    byId('player-media').replaceChildren(audio);
  }
  state.audioRetries = 0;
  audio.src = url;
  setupAudioMediaSession(state.currentTrack);
  audio.play().catch(playbackRejected);
}
function playbackRejected(error) {
  if (error.name === 'NotAllowedError') setStatus('Safari necesita tu permiso: pulsa ▶ para escuchar.');
  // AbortError is expected when switching tracks quickly; media errors retry above.
}

/** Controles nativos del teléfono SOLO para streaming de Audius/Archive. */
function mediaSessionPlayback(value) {
  if (!('mediaSession' in navigator)) return;
  try { navigator.mediaSession.playbackState = value; } catch { /* no compatible */ }
}
function setupAudioMediaSession(track) {
  if (!track || !('mediaSession' in navigator)) return;
  try {
    const artwork = safeImage(track.thumbnail) ? [{src: safeImage(track.thumbnail), }] : [];
    if ('MediaMetadata' in window) navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title, artist: track.channel || 'Artista', album: 'Ol', artwork
    });
    for (const [name, fn] of [
      ['play', togglePlayFromSystem], ['pause', () => state.audio?.pause()],
      ['nexttrack', playNext], ['previoustrack', playPrevious],
      ['seekbackward', details => seekAudio(-(details.seekOffset || 15))],
      ['seekforward', details => seekAudio(details.seekOffset || 15)],
      ['seekto', details => { if (Number.isFinite(details.seekTime)) seekAudio(details.seekTime, true); }]
    ]) {
      try { navigator.mediaSession.setActionHandler(name, fn); } catch { /* no compatible */ }
    }
  } catch { /* media session opcional */ }
}
function playNext() { if (state.currentIndex < state.queue.length - 1) playTrack(state.queue[state.currentIndex + 1], state.queue); else setStatus('Fin de la lista.'); }
function playPrevious() { if (state.currentIndex > 0) playTrack(state.queue[state.currentIndex - 1], state.queue); }
function togglePlayFromSystem() { state.audio?.play().catch(() => setStatus('Pulsa reproducir en Ol para continuar.')); }
function togglePlay() {
  if (state.audio) {
    if (state.audio.error && state.currentTrack) startAudio(`/api/play/${encodeURIComponent(state.currentTrack.id)}?retry=1`);
    else if (state.audio.paused) state.audio.play().catch(playbackRejected);
    else state.audio.pause();
  }
}

function closePlayer() {
  state.playSerial += 1;
  destroyMedia(); state.currentTrack = null; state.queue = []; state.currentIndex = -1;
  byId('player').classList.add('hidden'); setStatus('');
  sleepDeadline = 0; byId('sleep-timer').value = '0'; byId('sleep-status').textContent = '';
}

function advertisingConsent(value) {
  let previous = null;
  try {
    previous = localStorage.getItem(KEY.ads);
    localStorage.setItem(KEY.ads, value ? 'accepted' : 'rejected');
  } catch { /* Si el navegador bloquea storage, prevalece denegación */ }

  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('consent', 'update', {
    ad_storage: value ? 'granted' : 'denied',
    ad_user_data: value ? 'granted' : 'denied',
    ad_personalization: value ? 'granted' : 'denied',
    analytics_storage: 'denied'
  });

  if (value && !document.getElementById('electronicama-ads-script')) {
    const script = document.createElement('script');
    script.id = 'electronicama-ads-script';
    script.async = true;
    script.src = 'https://www.googletagmanager.com/gtag/js?id=AW-18507562663';
    document.head.append(script);
    window.gtag('js', new Date());
    window.gtag('config', 'AW-18507562663');
  }
  byId('consent-dialog').classList.add('hidden');
  // Un script de terceros ya cargado no puede desinstalarse limpiamente:
  // al revocar consentimiento recargamos con el estado denegado almacenado.
  if (!value && previous === 'accepted') window.location.reload();
}
function consentInit() {
  window.dataLayer = window.dataLayer || [];
  window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
  window.gtag('consent', 'default', {
    ad_storage: 'denied', ad_user_data: 'denied',
    ad_personalization: 'denied', analytics_storage: 'denied', wait_for_update: 500
  });
  let stored = null;
  try { stored = localStorage.getItem(KEY.ads); } catch { /* Denegado por defecto */ }
  if (stored === 'accepted') advertisingConsent(true);
  else if (stored !== 'rejected') byId('consent-dialog').classList.remove('hidden');
}
function init() {
  byId('favorites-count').textContent = String(state.favorites.filter(supportedTrack).length);
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => goView(button.dataset.view)));
  document.querySelectorAll('[data-source]').forEach(button => button.addEventListener('click', () => { state.source = button.dataset.source; if (state.source === 'MIX') { state.view = 'discover'; if (!state.mixLoaded && !state.mixLoading) requestMixSearch(state.mixQuery); } render(); }));
  document.querySelectorAll('[data-query]').forEach(button => button.addEventListener('click', () => {
    byId('library').scrollIntoView({ behavior: 'smooth' });
    requestSearch(button.dataset.query);
  }));
  byId('mobile-menu').addEventListener('click', () => {
    const hidden = byId('mobile-nav').classList.toggle('hidden');
    byId('mobile-menu').setAttribute('aria-expanded', String(!hidden));
  });
  byId('search-input').addEventListener('input', event => updateExternalSearch(event.target.value));
  byId('search-form').addEventListener('submit', event => { event.preventDefault(); requestSearch(byId('search-input').value); });
  byId('mix-search-form').addEventListener('submit', event => { event.preventDefault(); requestMixSearch(byId('mix-query').value); });
  document.querySelectorAll('[data-mix-query]').forEach(button => button.addEventListener('click', () => requestMixSearch(button.dataset.mixQuery)));
  byId('load-more').addEventListener('click', () => { if (state.source === 'MIX') { if (!state.mixLoading) { state.mixPage += 1; requestMixSearch(state.mixQuery, true); } return; } if (!state.loading) { state.page += 1; requestSearch(state.query, true); } });
  byId('clear-history').addEventListener('click', () => {
    if (!window.confirm('¿Borrar el historial guardado en este navegador?')) return;
    state.history = []; writeList(KEY.history, []); render(); message('Historial borrado.');
  });
  byId('player-expand').addEventListener('click', () => {
    const expanded = byId('player').classList.toggle('expanded');
    byId('player-expand').setAttribute('aria-expanded', String(expanded));
    byId('player-expand').textContent = expanded ? 'Reducir reproductor ↓' : 'Ampliar reproductor ↑';
  });
  byId('seek-back').addEventListener('click', () => seekAudio(-15));
  byId('seek-forward').addEventListener('click', () => seekAudio(15));
  byId('sleep-timer').addEventListener('change', event => {
    sleepDeadline = Number(event.target.value) ? Date.now() + Number(event.target.value) * 60000 : 0;
    byId('sleep-status').textContent = ''; updateSleepTimer();
  });
  setInterval(updateSleepTimer, 1000);
  document.addEventListener('visibilitychange', updateSleepTimer);
  byId('play-mix').addEventListener('click', () => { const list = filteredTracks(); if (list.length) playTrack(list[0], list); });
  byId('previous-track').addEventListener('click', playPrevious);
  byId('next-track').addEventListener('click', playNext);
  byId('toggle-play').addEventListener('click', togglePlay);
  byId('player-close').addEventListener('click', closePlayer);
  byId('player-favorite').addEventListener('click', () => { if (state.currentTrack) toggleFavorite(state.currentTrack); });
  byId('privacy-button').addEventListener('click', () => byId('consent-dialog').classList.remove('hidden'));
  byId('cookie-settings').addEventListener('click', () => byId('consent-dialog').classList.remove('hidden'));
  byId('consent-decline').addEventListener('click', () => advertisingConsent(false));
  byId('consent-accept').addEventListener('click', () => advertisingConsent(true));
  document.addEventListener('keydown', e => { if (e.key !== 'Escape') return; if (!byId('consent-dialog').classList.contains('hidden')) advertisingConsent(false); else closePlayer(); });
  consentInit();
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    window.addEventListener('load', () => navigator.serviceWorker.register('/sw.js').catch(() => {}));
  }
  window.addEventListener('maggy:access-changed', event => { if (!event.detail.active) closePlayer(); render(); });
  render();
  requestSearch(state.query);
  console.info(`Ol PRO ${VERSION} · Edición Iván Marcos Illa`);
}
window.addEventListener('maggy:play', event => { const list = Array.isArray(event.detail) ? event.detail : [event.detail]; if (list[0]?.id && list[0]?.source) playTrack(list[0], list); });
init();
