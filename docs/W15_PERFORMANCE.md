# W15 — Performance (Wave 15)

Wave 15 covers **Redis/tenant-config cache** and **high-traffic hardening**. This doc records what exists and how to use it.

## W15-1: Redis and tenant-config cache

### Current setup

- **Config:** `config/settings.py`
  - `CACHES["default"]`: uses `LocMemCache` when `REDIS_URL` is unset; when `REDIS_URL` is set, uses `django_redis.cache.RedisCache` with that URL.
  - `SESSION_ENGINE`: when `REDIS_URL` is set, sessions use `django.contrib.sessions.backends.cache` (shared across workers).
  - `RATELIMIT_USE_CACHE = 'default'`: rate limiting uses the same cache backend.
- **Existing cache usage:**
  - `apps/siteconfig/middleware/maintenance_mode.py`: caches `SiteSettings` maintenance flag under key `site_settings_v1` with TTL 60s to avoid hitting the DB on every request.

### Tenant-config cache pattern

To cache per-tenant (school) or site config:

1. **Key:** `tenant_config:{school_id}:v1` or `site_settings_v1` (global). Include a version or timestamp if you need invalidation.
2. **TTL:** 60–300 seconds for settings that change rarely.
3. **Invalidation:** On save of `SiteSettings` or school-related config, call `cache.delete(key)` or bump the key version. `SiteSettings` has `_refresh_site_settings_cache` (see `apps/siteconfig/models.py`).
4. **Example:**

```python
from django.core.cache import cache

def get_school_settings_cached(school_id, ttl=300):
    key = f"tenant_config:{school_id}:v1"
    data = cache.get(key)
    if data is not None:
        return data
    # ... load from DB ...
    cache.set(key, data, ttl)
    return data
```

Using this pattern for heavy reads (e.g. feature flags, grading rules) reduces DB load under high traffic.

---

## W15-2: High-traffic hardening

### Checklist (documentation / runbook)

| Item | Notes |
|------|--------|
| **Redis** | Set `REDIS_URL` in production so cache and sessions are shared across workers. |
| **DB** | Use connection pooling (e.g. PgBouncer) and consider read replicas for reporting. |
| **Static / media** | Serve static and media via CDN or separate domain; use `STATIC_ROOT` and `MEDIA_URL`. |
| **Rate limiting** | `RATELIMIT_USE_CACHE` and rate-limit decorators/middleware on auth and public APIs. |
| **Async** | Heavy exports/reports can be offloaded to Celery; return job ID and poll for result. |
| **N+1** | Use `select_related()` / `prefetch_related()` on list views and APIs. |
| **Health** | `/api/health/` and readiness endpoints for load balancers; keep them lightweight. |

### Verification

- Set `REDIS_URL` and confirm cache backend: `python manage.py shell` → `from django.core.cache import cache; cache.set("w15_test", 1); assert cache.get("w15_test") == 1`.
- Confirm maintenance middleware uses cache: `CACHE_KEY` in `apps/siteconfig/middleware/maintenance_mode.py`.

---

## Code refs

- `config/settings.py` — `CACHES`, `REDIS_URL`, `SESSION_ENGINE`, `RATELIMIT_USE_CACHE`.
- `apps/siteconfig/middleware/maintenance_mode.py` — `CACHE_KEY`, `CACHE_TTL`, cache get/set for maintenance flag.
