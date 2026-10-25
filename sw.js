/* ELECTRONICAMA PRO 8.6.1 · caché de interfaz, NO de música ni APIs.
   © 2026 Iván Marcos Illa, edición de esta aplicación. */
const CACHE = 'electronicama-shell-v8-6-1';
const STATIC = ['/assets/session.js?v=8.6.1', '/assets/styles.css?v=8.6.1', '/assets/app.js?v=8.6.1', '/assets/maggy.js?v=8.6.1', '/manifest.webmanifest', '/assets/favicon.svg', '/assets/app-icon-192.png'];
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
    event.respondWith(fetch(request).catch(() => new Response('<!doctype html><html lang=es><meta name=viewport content=width=device-width><title>Maggy sin conexión</title><h1>Maggy necesita conexión</h1><p>Conéctate para verificar tu acceso y escuchar música.</p><a href=/account>Mi cuenta</a></html>', {status:503,headers:{'Content-Type':'text/html; charset=utf-8'}})));
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});
