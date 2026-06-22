// sw.js — Eskom Grid Recovery Tracker service worker
const CACHE_NAME = "eskom-grid-v1";
const STATIC_ASSETS = [
  "/eskom-grid-tracker/",
  "/eskom-grid-tracker/index.html",
  "/eskom-grid-tracker/manifest.json",
  "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js",
];

// Install — cache static assets
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Activate — clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

// Fetch — network first, fall back to cache
self.addEventListener("fetch", (event) => {
  // Always go network-first for Supabase API calls
  if (event.request.url.includes("supabase.co")) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({ error: "Offline — showing cached data" }),
          { headers: { "Content-Type": "application/json" } }
        );
      })
    );
    return;
  }

  // Network first for everything else, cache as fallback
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// Push notifications (for future alert integration)
self.addEventListener("push", (event) => {
  const data = event.data?.json() ?? {};
  const title = data.title || "Eskom Grid Alert";
  const options = {
    body: data.body || "Check the dashboard for the latest update.",
    icon: "/eskom-grid-tracker/icons/icon-192.png",
    badge: "/eskom-grid-tracker/icons/icon-192.png",
    tag: "grid-alert",
    renotify: true,
    data: { url: "/eskom-grid-tracker/" },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

// Notification click — open dashboard
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data?.url || "/eskom-grid-tracker/")
  );
});
