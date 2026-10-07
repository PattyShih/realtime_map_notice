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

// Web Push：後端送來的是 EventNotification JSON
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: '附近新事件', message: event.data ? event.data.text() : '' };
  }
  const title = data.title ? `📍 ${data.title}` : '📍 附近新事件';
  const body = [
    data.message,
    data.distance_meters != null ? `距離約 ${Math.round(data.distance_meters)} 公尺` : null,
  ]
    .filter(Boolean)
    .join(' — ');
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/icons/icon-192.png',
      badge: '/icons/icon-192.png',
      tag: data.event_id || 'event',
      renotify: true,
      data: { url: '/' },
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients
      .matchAll({ type: 'window', includeUncontrolled: true })
      .then((list) => {
        for (const client of list) {
          if ('focus' in client) return client.focus();
        }
        return self.clients.openWindow('/');
      })
  );
});
