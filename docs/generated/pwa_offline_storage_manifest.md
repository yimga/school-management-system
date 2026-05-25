# PWA Offline Storage Manifest (Batch 1506)

| Cache bucket | Naming pattern |
| --- | --- |
| Static app shell | `sw-cache-static-{version}` |
| Offline fallback | `sw-cache-offline-{version}` |
| Runtime assets | `sw-cache-runtime-{version}` |

| IndexedDB database | Stores | Purpose |
| --- | --- | --- |
| `rmc-offline-queue` | request_queue, attempted_replays, checkpoint | Offline request replay |
| `rmc-portal-cache` | docs, user_prefs | Portal session-local cache |

## Skip-cache routes (never cached)

- `/admin/*`
- `/api/v1/auth/*`
- `/accounts/login/*`
- `/accounts/logout/*`
- `/accounts/mfa/*`
- `/super/migration/audit/*`

## Tenant cache safety

- Cache keys scoped to tenant host + role
- Logout purges tenant caches via `rmc-service-worker-registration.js`
- Service worker refuses cross-tenant fetches

## Honest limitations

- Install-prompt success rate cannot be browser-proven from this batch
- Offline write-queue replay live rate awaits Lane 2 browser harness
