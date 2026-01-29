// Service Worker for PWA functionality
const CACHE_NAME = 'sms-v1.0.0';
const STATIC_CACHE = 'sms-static-v1.0.0';
const DYNAMIC_CACHE = 'sms-dynamic-v1.0.0';

// Resources to cache immediately
const STATIC_ASSETS = [
  '/',
  '/static/css/portal_theme.css',
  '/static/css/dashboard-responsive.css',
  '/static/css/site-settings-preview.css',
  '/static/js/command-palette.js',
  '/static/js/dashboard-layout.js',
  '/static/js/dashboard-customizer.js',
  '/static/js/site-settings-preview.js',
  '/static/images/logo.png',
  '/static/manifest.json',
  '/offline/'
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('Service Worker: Installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('Service Worker: Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('Service Worker: Activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== STATIC_CACHE && cacheName !== DYNAMIC_CACHE) {
            console.log('Service Worker: Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests and external requests
  if (request.method !== 'GET' || !url.origin.includes(self.location.origin)) {
    return;
  }

  // Handle API requests differently
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Cache successful API responses for offline use
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(DYNAMIC_CACHE).then(cache => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Return cached API response if available
          return caches.match(request).then(cachedResponse => {
            if (cachedResponse) {
              return cachedResponse;
            }
            // Return offline API response
            return new Response(JSON.stringify({
              error: 'Offline',
              message: 'This feature requires an internet connection'
            }), {
              status: 503,
              headers: { 'Content-Type': 'application/json' }
            });
          });
        })
    );
    return;
  }

  // Handle static assets and pages
  event.respondWith(
    caches.match(request)
      .then(cachedResponse => {
        if (cachedResponse) {
          return cachedResponse;
        }

        return fetch(request)
          .then(response => {
            // Don't cache non-successful responses
            if (!response.ok) {
              return response;
            }

            const responseClone = response.clone();

            // Cache static assets
            if (request.destination === 'style' ||
                request.destination === 'script' ||
                request.destination === 'image' ||
                request.url.includes('/static/')) {
              caches.open(STATIC_CACHE).then(cache => {
                cache.put(request, responseClone);
              });
            }

            return response;
          })
          .catch(() => {
            // Return offline page for navigation requests
            if (request.mode === 'navigate') {
              return caches.match('/offline/');
            }

            // Return generic offline response
            return new Response('Offline', { status: 503 });
          });
      })
  );
});

// Background sync for offline data
self.addEventListener('sync', event => {
  console.log('Service Worker: Background sync triggered');

  if (event.tag === 'attendance-sync') {
    event.waitUntil(syncAttendanceData());
  }

  if (event.tag === 'grade-sync') {
    event.waitUntil(syncGradeData());
  }
});

// Sync attendance data
async function syncAttendanceData() {
  try {
    const attendanceData = await getStoredAttendanceData();

    for (const record of attendanceData) {
      await fetch('/api/attendance/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record)
      });
    }

    // Clear stored data after successful sync
    await clearStoredAttendanceData();
    console.log('Attendance data synced successfully');
  } catch (error) {
    console.error('Failed to sync attendance data:', error);
  }
}

// Sync grade data
async function syncGradeData() {
  try {
    const gradeData = await getStoredGradeData();

    for (const record of gradeData) {
      await fetch('/api/evaluations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(record)
      });
    }

    // Clear stored data after successful sync
    await clearStoredGradeData();
    console.log('Grade data synced successfully');
  } catch (error) {
    console.error('Failed to sync grade data:', error);
  }
}

// Helper functions for data storage (would use IndexedDB in production)
async function getStoredAttendanceData() {
  // Implementation would use IndexedDB
  return [];
}

async function getStoredGradeData() {
  // Implementation would use IndexedDB
  return [];
}

async function clearStoredAttendanceData() {
  // Implementation would clear IndexedDB
}

async function clearStoredGradeData() {
  // Implementation would clear IndexedDB
}
