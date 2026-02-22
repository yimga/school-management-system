# Phase I: Multi-Region (Phase 5) and Deploy

This document covers **Phase 5** items from the Global Powerhouse Roadmap: regional S3, tenant mapping, CDN/edge, L10n pipeline, regional payment gateways, global MFA, and latency-aware sync. It also documents the **deploy health check** and optional Docker entrypoint for schema-per-tenant.

---

## 1. Deploy health check (after migrate, before Gunicorn)

**Goal:** Run a lightweight DB check after migrations so the orchestrator only routes traffic when the DB is ready.

**Implemented:**
- **Management command:** `python manage.py db_health_check` — runs one `SELECT 1` and exits 0 on success, 1 on failure.
- **Script:** `scripts/release/run_health_check.sh` — invokes the command; used at the end of `scripts/release/render_predeploy.sh`.
- **Render:** Predeploy already runs migrate, seeds, then `run_health_check.sh`, then the service starts (Gunicorn). No change needed for Render beyond the added script call.

**When using django-tenants (USE_DJANGO_TENANTS=1):**  
In your release/entrypoint, run in order:
1. `migrate_schemas --shared`
2. Optionally `migrate_schemas --tenant` (or per-tenant)
3. `python manage.py db_health_check`
4. Start Gunicorn (or uWSGI).

Example **Docker entrypoint** (optional):

```bash
#!/usr/bin/env bash
set -e
if [[ "${USE_DJANGO_TENANTS}" == "1" ]]; then
  python manage.py migrate_schemas --shared
  python manage.py migrate_schemas --tenant  # or loop over tenants
fi
python manage.py db_health_check
exec gunicorn -c config/gunicorn.conf.py config.wsgi:application
```

---

## 2. Tenant → region mapping

**Goal:** Store each tenant’s region (e.g. country or region_id) so you can route storage, CDN, and data residency by region.

**Current:** `School.default_region` (FK to `siteconfig.RegionConfig`) and `School` lives in public schema. RegionConfig holds country-level defaults (currency, timezone, grading).

**Phase 5 actions:**
- Use **School.default_region_id** (or add **School.region_id** / **country_code** if you need an explicit region for routing) as the tenant’s region.
- In shared schema (or config), maintain a **region → endpoint/bucket** map, e.g.:
  - `EU` → S3 bucket `bucket-eu`, API base `https://api-eu.example.com`
  - `US` → S3 bucket `bucket-us`, API base `https://api-us.example.com`
- When serving a request, resolve `request.school` (or `request.tenant.school`), then `school.default_region` (or region_id), then choose storage bucket and optional API base from that map.

**No code change required for “mapping” itself** — the field exists. Add **documentation** and, when you add multi-region infra, a small **TenantRegionRouter** (or config dict) that returns bucket and base URL from `school.default_region.code` (or similar).

---

## 3. Regional S3 and tenant-prefixed storage

**Goal:** Per-tenant and optionally per-region file storage so data residency (e.g. GDPR/FERPA) can be met.

**Current:** `MEDIA_ROOT` and `DEFAULT_FILE_STORAGE` are global. Plan: prefix all tenant uploads with **tenants/{school_id}/** (or `tenants/{schema_name}/` when using django-tenants).

**Phase 5 actions:**
- **Settings:** Document or add a custom storage backend that uses `upload_to = "tenants/%(school_id)s/..."` (or equivalent) for FileField/ImageField in tenant-scoped models. If using S3, set `AWS_STORAGE_BUCKET_NAME` per region when you have multiple buckets (e.g. via env or a region→bucket map).
- **Regional buckets:** When you introduce regional cells, configure one bucket per region (e.g. `bucket-eu`, `bucket-us`) and set `DEFAULT_FILE_STORAGE` (or the backend’s bucket name) from the tenant’s region so that a school in France uses the EU bucket.
- **Reference:** See roadmap “Tenant media: prefix tenants/{school_id}/ in DEFAULT_FILE_STORAGE and upload_to”.

---

## 4. CDN and edge

**Goal:** Use a CDN (e.g. Cloudflare, Azure Front Door) for static assets and optionally for read-only API/edge so low-bandwidth and global users get low latency.

**Phase 5 actions:**
- **Static:** Already using Whitenoise; for scale, put a CDN in front and set `STATIC_URL` (or CDN base URL) so static files are served from the edge.
- **Edge routing:** Document that platform probes and health can hit the CDN; origin remains Django. For “route by region”, use **Anycast** or geo-based DNS so users hit the nearest edge; origin can stay single or be regional (multi-region DB/cells).
- **Caching:** Cache read-only shared data (countries, plan prices, education templates) at the edge (e.g. Cloudflare Workers) so schools in distant regions get fast responses without hitting Django for every request.

---

## 5. L10n pipeline

**Goal:** Systematic i18n for UI and app-store-style copy across regions and dialects.

**Current:** Django i18n; `LOCALE_PATHS`; `region_settings` and user preferences for language/region; template filters for date/currency/number.

**Phase 5 actions:**
- Use **django’s gettext** and **phrase/translation pipeline** (or similar) for UI strings.
- Ensure all user-facing strings are in message files; no hardcoded copy in templates or JS.
- Document the workflow: extract → upload to Phrase (or equivalent) → translate → download → compile; run as part of release.

---

## 6. Regional payment gateways and global MFA

**Goal:** Support regional gateways (e.g. M-Pesa, Pix) alongside Stripe, and enforce MFA globally.

**Current:** Finance and payment logic in `apps.finance`; **django_otp** is installed and MFA middleware exists.

**Phase 5 actions:**
- **Payments:** Document where to plug in regional gateways (e.g. M-Pesa, Pix) as additional payment methods per region; keep Stripe for international. No single “phase I” code change — extend payment backend interface and config per region when you add gateways.
- **MFA:** Ensure **RequireMFAMiddleware** and MFA enrollment flows are enabled for all staff (or per-role) so global MFA is in place; document any region-specific MFA requirements (e.g. stricter in EU).

---

## 7. Latency-aware sync and edge routing

**Goal:** For offline/sync and low-bandwidth regions (2G/3G, high latency), use compression and edge routing.

**Phase 5 actions:**
- **Compression:** Gzip/Brotli for sync payloads (already mentioned in roadmap); enable in Django (e.g. GZipMiddleware for JSON sync endpoints) or at reverse proxy.
- **Edge routing:** When using multi-region, route sync (and optionally auth) to the **nearest regional endpoint** (e.g. Africa → Cape Town, Europe → Frankfurt) so sync is faster and more reliable.
- **Document:** Add a short “Sync and multi-region” section to this doc or to the main deploy doc: “When regional cells exist, configure sync endpoint URL per region (or use geo-DNS) so clients in that region hit the nearest API.”

---

## 8. Summary checklist (Phase 5)

| Item | Status | Notes |
|------|--------|--------|
| Deploy health check | Done | `db_health_check` command + `run_health_check.sh` in predeploy. |
| Tenant → region mapping | Doc + existing field | Use `School.default_region`; add region→bucket/endpoint map when scaling. |
| Regional S3 | Documented | Tenant prefix `tenants/{school_id}/`; regional buckets when multi-region. |
| CDN/edge | Documented | Static + optional edge cache for read-only data; Anycast/geo-DNS. |
| L10n pipeline | Documented | gettext + phrase/translation workflow. |
| Regional payments | Documented | Plug M-Pesa, Pix, etc. per region when added. |
| Global MFA | In place | django_otp + RequireMFAMiddleware. |
| Latency-aware sync | Documented | Compression + edge routing when regional cells exist. |
