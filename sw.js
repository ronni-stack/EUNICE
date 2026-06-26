const CACHE_NAME = 'eunice-cache-v1';
const URLS_TO_CACHE = [
    '/',
    '/client.html'  // or whatever your actual file is served as
];

self.addEventListener('install', event => {
    self.skipWaiting();
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(URLS_TO_CACHE))
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', event => {
    // Only cache GET requests
    if (event.request.method !== 'GET') return;
    
    event.respondWith(
        caches.match(event.request).then(cached => {
            // Return cached immediately, but also fetch fresh in background
            const fetchPromise = fetch(event.request)
                .then(networkResp => {
                    if (networkResp.ok) {
                        caches.open(CACHE_NAME).then(cache => {
                            cache.put(event.request, networkResp.clone());
                        });
                    }
                    return networkResp;
                })
                .catch(() => cached); // If network fails, we already have cached
            
            return cached || fetchPromise;
        })
    );
});