// Service worker: precaches the app shell so the app works offline.
//
// Strategy: cache-first. When online, each cached file is also refreshed in the
// background, so a new deploy reaches the device on the next open. Bump VERSION
// whenever the list of files changes. Only the app's own static files are
// fetched; your data is never sent anywhere.

const VERSION = 'v2';
const CACHE = `cycle-app-${VERSION}`;
const SHELL = [
  './',
  './index.html',
  './manifest.json',
  './css/style.css',
  './js/ui.js',
  './js/model.js',
  './js/storage.js',
  './js/csv.js',
  './js/ics.js',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(SHELL.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k.startsWith('cycle-app-') && k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

async function refreshInBackground(request, cacheKey) {
  try {
    const response = await fetch(request, { cache: 'no-cache' });
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(cacheKey, response);
    }
  } catch {
    // offline: keep the cached copy
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Every navigation inside the app gets the cached index.html.
  const cacheKey = request.mode === 'navigate' ? new URL('./index.html', self.registration.scope).href : request;

  event.respondWith((async () => {
    const cached = await caches.match(cacheKey, { ignoreSearch: true });
    if (cached) {
      event.waitUntil(refreshInBackground(request.mode === 'navigate' ? cacheKey : request, cacheKey));
      return cached;
    }
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      cache.put(cacheKey, response.clone());
    }
    return response;
  })());
});
