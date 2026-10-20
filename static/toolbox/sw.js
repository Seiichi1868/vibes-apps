/* Toolbox Service Worker */
const VERSION = "toolbox-v3";
const STATIC_CACHE = `${VERSION}-static`;
const PAGE_CACHE = `${VERSION}-pages`;
const OFFLINE_URL = "/toolbox/offline";
const STATIC_PREFIX = "/static/toolbox/";

// 将来オフライン対応するツールページをここに追加する（今は空）
// 例: ["/toolbox/timer", "/toolbox/random-pick", "/toolbox/random-seats"]
const OFFLINE_TOOL_PAGES = [];

// 絶対にキャッシュしない（認証、管理、API、録音・AI関連）
const NEVER_CACHE_PREFIXES = [
  "/toolbox/api/",
  "/toolbox/admin/",
  "/toolbox/login",
  "/toolbox/logout",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then((cache) => cache.add(OFFLINE_URL))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((k) => k.startsWith("toolbox-") && !k.startsWith(VERSION))
            .map((k) => caches.delete(k))
        )
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (NEVER_CACHE_PREFIXES.some((p) => url.pathname.startsWith(p))) return;

  if (url.pathname.startsWith(STATIC_PREFIX)) {
    if (isHashedAsset(url)) {
      event.respondWith(cacheFirst(req));
    } else if (url.pathname.endsWith(".js") || url.pathname.endsWith(".css") || url.pathname.endsWith(".mjs")) {
      event.respondWith(networkFirstStatic(req));
    } else {
      event.respondWith(staleWhileRevalidate(req));
    }
    return;
  }
  if (req.mode === "navigate") {
    event.respondWith(networkFirstPage(req, url));
  }
});

function isHashedAsset(url) {
  return /^[0-9a-f]{10}$/.test(url.searchParams.get("v") || "");
}

async function cacheFirst(req) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res && res.ok && res.type === "basic") cache.put(req, res.clone());
  return res;
}

async function networkFirstStatic(req) {
  const cache = await caches.open(STATIC_CACHE);
  try {
    const res = await fetch(req, { cache: "no-cache" });
    if (res && res.ok && res.type === "basic") cache.put(req, res.clone());
    return res;
  } catch (e) {
    const cached = await cache.match(req);
    if (cached) return cached;
    throw e;
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(req);
  const network = fetch(req)
    .then((res) => {
      if (res && res.status === 200 && res.type === "basic") cache.put(req, res.clone());
      return res;
    })
    .catch(() => cached);
  return cached || network;
}

async function networkFirstPage(req, url) {
  try {
    const res = await fetch(req);
    if (res && res.status === 200 && OFFLINE_TOOL_PAGES.includes(url.pathname)) {
      const cache = await caches.open(PAGE_CACHE);
      cache.put(req, res.clone());
    }
    return res;
  } catch (e) {
    const cache = await caches.open(PAGE_CACHE);
    const cachedPage = await cache.match(req);
    if (cachedPage) return cachedPage;
    const offline = await caches.match(OFFLINE_URL);
    return (
      offline ||
      new Response("オフラインです", {
        status: 503,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      })
    );
  }
}
