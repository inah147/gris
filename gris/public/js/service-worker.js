// Service Worker para GRIS PWA
const CACHE_NAME = 'gris-cache-v2';
const urlsToCache = [
  '/assets/gris/manifest.json',
  '/assets/gris/images/icons/ios/32.png',
  '/assets/gris/images/icons/ios/180.png',
  '/assets/gris/js/pwa-init.js'
];

async function cacheStaticAssets(cache) {
  await Promise.all(
    urlsToCache.map(async (url) => {
      try {
        await cache.add(url);
      } catch (error) {
        console.warn(`[Service Worker] Failed to cache ${url}:`, error);
      }
    })
  );
}

// Instalação do Service Worker
self.addEventListener('install', event => {
  console.log('[Service Worker] Installing...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async cache => {
        console.log('[Service Worker] Caching app shell');
        await cacheStaticAssets(cache);
      })
      .catch(err => {
        console.log('[Service Worker] Cache failed:', err);
      })
  );
  self.skipWaiting();
});

// Ativação do Service Worker
self.addEventListener('activate', event => {
  console.log('[Service Worker] Activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  return self.clients.claim();
});

// Estratégia de cache: Network First, fallback para Cache
self.addEventListener('fetch', event => {
  // Ignora requisições que não sejam GET
  if (event.request.method !== 'GET') {
    return;
  }

  // Ignora requisições de API
  if (event.request.url.includes('/api/')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Se a resposta for válida, clone e adicione ao cache
        if (response && response.status === 200 && response.type === 'basic') {
          const responseToCache = response.clone();
          caches.open(CACHE_NAME)
            .then(cache => {
              cache.put(event.request, responseToCache);
            });
        }
        return response;
      })
      .catch(() => {
        // Se falhar, tente buscar do cache
        return caches.match(event.request)
          .then(response => {
            if (response) {
              return response;
            }
            // Se não encontrar no cache, retorne uma página offline customizada
            if (event.request.mode === 'navigate') {
              return caches.match('/inicio');
            }
          });
      })
  );
});

// Listener para mensagens do cliente
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
