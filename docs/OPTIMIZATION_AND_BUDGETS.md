# Optimization and budgets

**Goal:** Query budgets per critical view, N+1 detection, cache invalidation documented, frontend asset size budgets, critical-path performance tests.

## Query budgets

- **Critical views:** Login, dashboard load, runtime resolution, tenant list, billing page, report generation. For each: add select_related/prefetch_related where needed; target max queries (e.g. &lt;20) per view where feasible.
- **Tests:** Add per-view query count tests for critical paths (e.g. assert num_queries &lt; N for dashboard or login). Use Django TestCase with assertNumQueries or similar.
- **N+1:** Run with django-debug-toolbar or test that asserts max queries; fix N+1 in list/detail views.

## Cache

- **Where we cache:** Runtime cache (platform_runtime.cache), tenant_cache_key for tenant-scoped cache; session; view caching where used.
- **Invalidation:** Document invalidation on policy change, tenant change, blueprint apply. TTL and keys in code or config; document in runbook if operators need to clear cache.

## Frontend assets

- **Marketing bundle:** Keep marketing CSS/JS minimal; document or add CI step for bundle size (e.g. marketing bundle &lt; X KB).
- **App bundles:** See docs/CSS_RATIONALIZATION.md; consolidate where possible.

## Performance tests

- Add one or more performance tests: e.g. login or dashboard load under a time threshold, or max queries for a critical view. Run in CI or nightly.

## References

- apps/platform_runtime/cache.py
- docs/CSS_RATIONALIZATION.md
- Django assertNumQueries, django-debug-toolbar
