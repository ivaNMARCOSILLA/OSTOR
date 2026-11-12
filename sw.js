/* ELECTRONICAMA PRO 9.31.0 · caché de interfaz, NO de música ni APIs.
   © 2026 Iván Marcos Illa, edición de esta aplicación. */
const CACHE = 'electronicama-shell-v9-31-0';
const STATIC = ['/assets/registration-fee.css?v=9.31.0', '/assets/registration-fee.js?v=9.31.0', '/assets/access-help.js?v=9.31.0', '/assets/contributions.css?v=9.31.0', '/assets/contributions.js?v=9.31.0', '/assets/videos.css?v=9.31.0', '/assets/videos.js?v=9.31.0', '/assets/participants.css?v=9.31.0', '/assets/participants.js?v=9.31.0', '/assets/floral-field.js?v=9.31.0', '/assets/floral-field.css?v=9.31.0', '/assets/founder-fish.css?v=9.31.0', '/assets/founder-fish.svg?v=9.31.0', '/assets/botanical-leaf-border.svg?v=9.31.0', '/assets/botanical-leaves.css?v=9.31.0', '/assets/botanical-leaf.svg?v=9.31.0', '/assets/reading-copy.css?v=9.31.0', '/assets/music-memory.css?v=9.31.0', '/assets/radio-visualizer.css?v=9.31.0', '/assets/radio-visualizer.js?v=9.31.0', '/assets/botanical-interface.css?v=9.31.0', '/assets/botanical-interface.js?v=9.31.0', '/assets/botanical-flower.svg?v=9.31.0', '/assets/mobile-shell.css?v=9.31.0', '/assets/mobile-shell.js?v=9.31.0', '/assets/platform-theme.css?v=9.31.0', '/assets/session.js?v=9.31.0', '/assets/styles.css?v=9.31.0', '/assets/ol-theme.css?v=9.31.0', '/assets/app.js?v=9.31.0', '/manifest.webmanifest', '/assets/favicon.svg', '/assets/app-icon-192.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('electronicama-shell-') && key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith('/api/') || url.pathname === '/health' || url.pathname.startsWith('/_vercel/')) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => new Response('<!doctype html><html lang=es><meta name=viewport content=width=device-width><title>Ol sin conexión</title><h1>Ol necesita conexión</h1><p>Conéctate para verificar tu acceso y escuchar música.</p><a href=/account>Mi cuenta</a></html>', {status:503,headers:{'Content-Type':'text/html; charset=utf-8'}})));
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});
