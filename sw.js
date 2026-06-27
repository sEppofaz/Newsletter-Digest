const CACHE = 'newsletter-v1';

const SHELL = [
  '/newsletter/',
  '/newsletter/manifest.json',
  '/newsletter/icon-192.png',
  '/newsletter/icon-512.png',
  '/newsletter/apple-touch-icon.png',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/newsletter/api/')) return;
  if (e.request.destination === 'document') {
    e.respondWith(fetch(e.request).catch(() => caches.match('/newsletter/')));
    return;
  }
  e.respondWith(caches.match(e.request).then(c => c || fetch(e.request)));
});
