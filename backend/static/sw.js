const CACHE = 'alex-v26';
const SHELL = ['/style.css?v=25', '/app.js?v=33', '/manifest.json'];

self.addEventListener('install', function(e) {
  e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(SHELL); }));
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); }));
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  if (e.request.url.indexOf('/api/') !== -1) {
    e.respondWith(fetch(e.request));
    return;
  }
  // Always request the HTML shell again when the app is opened. The cached
  // copy remains available only when the device is offline.
  if (e.request.mode === 'navigate') {
    e.respondWith(
      fetch(e.request).then(function(response) {
        var copy = response.clone();
        caches.open(CACHE).then(function(cache) { cache.put(e.request, copy); });
        return response;
      }).catch(function() { return caches.match(e.request); })
    );
    return;
  }
  e.respondWith(
    caches.match(e.request).then(function(cached) { return cached || fetch(e.request); })
  );
});

self.addEventListener('push', function(e) {
  var data = { title: 'Alex', body: '' };
  try { data = e.data.json(); } catch (_) {}
  e.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/icon.png',
      badge: '/icon.png',
    })
  );
});

self.addEventListener('notificationclick', function(e) {
  e.notification.close();
  e.waitUntil(clients.openWindow('/'));
});
