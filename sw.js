const CACHE = 'ticketflow-v2';
const STATIC_ASSETS = [
  './index.html',
  './manifest.json',
  'https://cdn.jsdelivr.net/npm/chart.js',
];

// 설치
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// 활성화: 이전 캐시 전부 삭제
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

// 요청 처리
self.addEventListener('fetch', e => {
  const url = e.request.url;

  // schedule.json: 캐시 완전 무시, 항상 네트워크
  if (url.includes('schedule.json')) {
    e.respondWith(
      fetch(e.request.url + '?t=' + Date.now(), { cache: 'no-store' })
        .catch(() => new Response('{"games":[],"standings":[]}', {
          headers: { 'Content-Type': 'application/json' }
        }))
    );
    return;
  }

  // index.html: 네트워크 우선, 실패 시 캐시
  if (url.includes('index.html') || url.endsWith('/')) {
    e.respondWith(
      fetch(e.request)
        .then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
        .catch(() => caches.match('./index.html'))
    );
    return;
  }

  // 나머지 정적 파일: 캐시 우선
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(res => {
        if (res && res.status === 200) {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return res;
      });
    })
  );
});
