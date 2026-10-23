/* 最小可用的 PWA Service Worker：快取應用程式外殼，讓手機可安裝、弱網可開啟。
   策略刻意保守：
   - 只處理同源 GET；地圖圖資（OSM）、後端 API、WebSocket 皆為跨域，一律直連不快取
   - 導航請求 network-first（有網路永遠拿最新版頁面），離線才回退快取
   - 其餘同源靜態資源 cache-first（Vite 產出的檔名帶 hash，內容變即網址變）
   - localhost（本機開發）只提供推播所需的最小註冊，不安裝快取也不攔截請求，
     避免干擾 Vite HMR 與開發時的即時程式碼 */
const CACHE = 'rmn-shell-v1';
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'];
const IS_DEV = ['localhost', '127.0.0.1'].includes(self.location.hostname);

self.addEventListener('install', (event) => {
  if (IS_DEV) {
    self.skipWaiting();
    return;
  }
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

if (!IS_DEV) {
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
}

// Web Push：後端送來的是 EventNotification JSON
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { title: '附近新事件', message: event.data ? event.data.text() : '' };
  }
  // 排版（iOS 第一行會被時間標籤壓縮）：
  // 第一行 = 地標（短，不截斷）；內文 = 完整事件標題＋描述＋距離（可換行不截斷）
  const title = data.location_label ? `📍 ${data.location_label}` : '📍 附近新事件';
  const body = [
    data.title,
    data.message && data.message !== '無詳細描述' ? data.message : null,
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
