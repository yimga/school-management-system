# Config & Hardcoded Values Audit — Prioritized Action List

**Scan date:** 2026-01-24
**Scope:** repo-wide scan for hardcoded UI placeholders, numeric literals used for TTL/thresholds, inline cache keys, external URLs/CDNs, and migration conflicts.

---

## Executive summary ✅
- Tests: Full test run failed with a **migration conflict (multiple leaf nodes)** in `apps.siteconfig.migrations` (see `0017_...` and `0018_...`). This blocks test DB creation and is the highest-priority fix (P0).
- Configuration issues (P1): Several behavioral values are hardcoded (cache TTLs, dedupe TTLs, rate-limit windows) that should be admin-configurable or centrally defined.
- UI/text defaults (P2): Template strings like `"N/A"` and numeric placeholders like `0.00` are used in a few places; these should be replaced with site-configured fallbacks or translatable defaults.
- External resources (P2): CDNs and absolute URLs are embedded in templates and docs — should be configurable (CDN base or local static) for resilience.

---

## Immediate blocking issue (P0)
1) Migration conflict — `siteconfig`
- Symptom (test output):
  - Command error: `Conflicting migrations detected; multiple leaf nodes in the migration graph: (0017_dashboardwidget_dashboarduserpreference_widgetdata, 0018_sitesettings_admin_portal_stats_config in siteconfig). To fix them run 'python manage.py makemigrations --merge'`
- Files involved:
  - `apps/siteconfig/migrations/0017_dashboardwidget_dashboarduserpreference_widgetdata.py`
  - `apps/siteconfig/migrations/0018_sitesettings_admin_portal_stats_config.py`
- Recommended actions:
  - Option A (quick): Run `python manage.py makemigrations --merge` locally, inspect generated merge migration, run test suite. Commit merge migration.
  - Option B (safe review): Manually inspect 0017/0018 for overlapping operations (field additions, renames). If both add fields, create a merge migration that contains both AddField ops in a single new migration, ensure defaults are safe for get_or_create singleton patterns.
  - Add a short test (or CI check) that ensures migrations graph has a single head per app (fail early).
- Why P0: Blocks test DB creation and prevents progress on other fixes.

---

## High-priority configuration improvements (P1)
These affect behavior, reliability, and observability.

A) Dedupe/TTL and Rate-limits
- Examples found:
  - `apps/compliance/alerts.py` — `cache.set(dedupe_key, True, 60)` (hard TTL)
  - `apps/siteconfig/geoip_service.py` — `cache.set(cache_key, result, GeoIPService.CACHE_TIMEOUT)` (constant in code)
  - `apps/portal/views_ai_copilot.py` — `cache.set(key, events, RATE_LIMIT_WINDOW)` and hard keys like `'ai_copilot_usage_total'`
  - Also found `cache.set(..., 86400)` and `cache.set(..., 5 * 60)` in docs/examples
- Recommendation:
  - Centralize TTLs and flags in `SiteSettings` (or `django-constance`) with explicit names: `compliance_alert_dedupe_ttl`, `geoip_cache_ttl`, `ai_copilot_rate_window`.
  - Create small helper functions to build cache keys (e.g., `cache_key('audit_alert_sent', id)`), preventing key collisions and providing a single place to mutate key format.
  - Add admin UI help text documenting purpose and safe ranges.

B) Cache keys (naming & naming collisions)
- Examples: `'ai_copilot_usage_total'`, `'ai_copilot_last_success_ts'` literals scattered.
- Recommendation: Wrap key names in a small module `apps/siteconfig/cache_keys.py` and reference constants to make refactors safe.

C) Feature toggles
- Hard-coded features: `ai_copilot` usage flags, dashboard widgets, analytics inclusion.
- Recommendation: Add admin toggles (booleans) to control experimental features (e.g., `enable_ai_copilot`). Use flags in views to short-circuit behavior in tests.

---

## Medium priority UI & localizable defaults (P2)
A) Template placeholders & defaults
- Examples:
  - `N/A` used in `apps/finance/api_views.py` and report rendering code.
  - Numeric placeholders like `Decimal('0.00')` in finance models (normal for DB defaults — but display should use localized formatting and site-configured currency formatting).
- Recommendation:
  - Provide a template filter: `{{ value|display_or_site_default }}` which uses `SiteSettings.value_default_text` or translation fallback.
  - Use `localize`/`format` for currency display; add `site.currency_symbol` to `SiteSettings`.

B) External CDN links in templates
- Examples: `https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css` found in older templates.
- Recommendation:
  - Use local static assets or a setting `CDN_BASE_URL` to allow swapping CDN or using local files in offline environments.

---

## Low priority / housekeeping (P3)
- TODOs in templates and code (`TODO`, `FIXME`) — track in a project board and assign small tickets.
- Doc links / environment URLs in `WEB_APP Work_note.txt` — move to `docs/DEPLOYMENT.md` and replace with environment variables in deployments.

---

## Tests & CI suggestions
- Add a CI job to run `python manage.py makemigrations --check --dry-run` and fail if migrations graph has multiple heads for any app.
- Add a quick audit test that ensures common behavioral TTLs are read from `SiteSettings` or `settings.py` and not hardcoded numbers within business logic files.

---

## Proposed rollout plan (phased)
1. Fix migration conflict and add a CI migration-health check (P0) — *ETA: <1 day*.
2. Make dedupe/rate TTLs configurable in `SiteSettings` and replace literal usages (P1) — *ETA: 1–2 days*.
3. Add admin UI/help text and unit tests for TTL boundaries (P1) — *ETA: 1 day*.
4. Replace template fallbacks with a template filter and add localization (P2) — *ETA: 1–2 days*.
5. Replace CDN absolute links with `CDN_BASE_URL` and local fallbacks (P2) — *ETA: 1 day*.
6. Create tracking tickets for low-priority TODOs and doc cleanup (P3) — *ETA: ongoing*.

---

## Next actions (I can take these for you):
- Create the migration merge file (or run `makemigrations --merge`) and run the test suite again to unblock CI.
- Implement `SiteSettings` fields for `compliance_alert_dedupe_ttl` and `ai_copilot_rate_window`, update code to read those values, and add tests.
- Generate a PR that performs the low-risk changes (detailed migrations + unit tests + admin forms + docs).

If you want, I can start by creating and committing the migration merge and re-running the test suite now.

---

*Report generated automatically by repo scan tools + manual verification.*
