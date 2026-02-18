const CACHE_NAME = 'nomadnet-v3';
const APP_SHELL = [
  '/',
  '/static/style.css',
  '/static/htmx.min.js',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

// Install: cache app shell
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(APP_SHELL);
    })
  );
  self.skipWaiting();
});

// Activate: clean up old caches
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.filter(function(name) {
          return name !== CACHE_NAME;
        }).map(function(name) {
          return caches.delete(name);
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch: cache-first for static, network-first for everything else
self.addEventListener('fetch', function(event) {
  var request = event.request;

  // Skip non-GET requests
  if (request.method !== 'GET') return;

  // Skip WebSocket requests
  if (request.url.indexOf('/ws') !== -1) return;

  // Cache-first for static assets
  if (request.url.indexOf('/static/') !== -1) {
    event.respondWith(
      caches.match(request).then(function(cached) {
        return cached || fetch(request).then(function(response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(request, clone);
          });
          return response;
        });
      })
    );
    return;
  }

  // Network-first with cache fallback for HTML/API
  event.respondWith(
    fetch(request).then(function(response) {
      var clone = response.clone();
      caches.open(CACHE_NAME).then(function(cache) {
        cache.put(request, clone);
      });
      return response;
    }).catch(function() {
      return caches.match(request);
    })
  );
});
