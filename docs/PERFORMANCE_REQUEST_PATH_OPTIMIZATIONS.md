# Request-Path Performance Optimizations

Short doc for optimizations that reduce load on **every request** (middleware, context processors, runtime build).

## Implemented

### 1. `get_effective_site_settings()` cache (apps/platform_runtime/helpers.py)

- **Problem:** `SiteSettings.get_solo()` was called on every request (e.g. from context processors and views), causing a DB hit per page.
- **Change:**
  - **Request-scope:** First call in a request stores the result on `request._effective_site_settings_cached`; later calls in the same request reuse it (no extra DB).
  - **Cross-request:** Result is cached in Django cache for 60s, keyed by `platform_runtime:effective_site_settings:{school_id or 'platform'}`.
- **Effect:** Fewer DB queries for site settings; repeated use in the same request (e.g. context processor + view) does not hit DB at all.

### 2. Registry context cache in `build_tenant_runtime` (apps/platform_runtime/runtime_resolver.py)

- **Problem:** Step 3 of runtime build (`_step3_registry_context`) ran 7+ registry queries (Country, Currency, EducationLevel, EducationSystemType, InstitutionType, DocumentType, FeeCategory, GradeScale) on **every** tenant request.
- **Change:** The full `RegistryContext` is cached for 5 minutes, keyed by `platform_runtime:registry_context:{country_code or 'default'}`.
- **Effect:** First request for a country populates the cache; subsequent requests for the same country reuse it, avoiding all registry queries for that step.

## Existing (unchanged)

- **TenantRuntime:** Already request-scope cached in `build_tenant_runtime` via `get_cached_runtime_for_request` / `set_cached_runtime_for_request`, so the full runtime is built once per request.
- **Portal dashboard:** See `docs/PHASE_1_1_OPTIMIZATION.md` and `apps/portal/services.py` for batch loading and widget caching.
- **Admin dashboard widgets:** `apps/dashboard/admin_context.py` uses per-widget cache (TTL) for payloads.

## Optional follow-ups

- **Cache invalidation:** When SiteSettings or registry data is updated in admin, consider clearing the relevant cache keys so changes appear within 60s/5min instead of waiting for TTL.
- **Blueprint/workflows/dashboards (steps 4, 8, 9):** If profiling shows these steps are hot, add short-TTL caches keyed by `school_id` (and optionally policy version).
- **Template fragment caching:** For heavy, mostly-static fragments (e.g. footer, nav), use `{% load cache %}` and `{% cache 300 fragment_name %}...{% endcache %}` where appropriate.
