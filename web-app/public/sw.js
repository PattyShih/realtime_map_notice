/* 最小可用的 PWA Service Worker：快取應用程式外殼，讓手機可安裝、弱網可開啟。
   策略刻意保守：
   - 只處理同源 GET；地圖圖資（OSM）、後端 API、WebSocket 皆為跨域，一律直連不快取
   - 導航請求 network-first（有網路永遠拿最新版頁面），離線才回退快取
   - 其餘同源靜態資源 cache-first（Vite 產出的檔名帶 hash，內容變即網址變） */
const CACHE = 'rmn-shell-v1';
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === 'navigate') {
    event.respondWith(fetch(request).catch(() => caches.match('/index.html')));
    return;
  }
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request).then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
          return res;
        })
    )
  );
});
