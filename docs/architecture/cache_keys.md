# Tenant-scoped cache keys (World Engine §8)

When using a **shared** cache backend (e.g. Redis) across tenants, every key that stores **tenant-specific** data must include a tenant identifier (e.g. `tenant:schema_name` or `school:id`) to avoid cross-tenant leakage.

## Helpers

- **apps.siteconfig.cache_utils.get_tenant_cache_prefix(request=None)**  
  Returns a string like `tenant:<schema_name>` (when `connection.tenant` is set) or `school:<id>` (when `request.school` is set), or `public` when neither is available. Use for building tenant-scoped keys. The optional PostgreSQL **`current_setting('app.current_school_id', true)`** probe for RLS-aware prefixing is delegated to **`apps.siteconfig.repositories.rls_session_repository`** (one of **six** §2.4 allowlisted repository modules; **`cache_utils`** has no local `cursor.execute`).

- **apps.siteconfig.cache_utils.tenant_cache_key(base_key, request=None)**  
  Returns `{prefix}:{base_key}`. Use in views when you have `request` so RLS mode gets `school:id`.

## Where tenant prefix is used

| Area | Location | Key pattern / note |
|------|----------|--------------------|
| **Evals** | apps/evals/caching.py, ranking.py | `get_tenant_cache_prefix(None)` in key; connection.tenant in schema-per-tenant. |
| **Dashboard** | apps/dashboard/admin_context.py | `_widget_cache_key` uses `get_tenant_cache_prefix(request)`. |
| **Portal** | apps/portal/services.py, views_ai_copilot.py, views.py | Prefix in parent_dashboard_widgets, performance_overview, analytics_insights, pass_mark; `tenant_cache_key(..., request)` for AI copilot and badge_verify. |
| **Reports** | apps/reports/services.py, bi_services.py | `get_tenant_cache_prefix(None)` in report_block_sms, exec_*, enrollment_trends, ReportCacheManager; invalidate_report_cache uses prefix in pattern. |
| **Compliance** | apps/compliance/views_dashboard.py, access_control.py, alerts.py, signals.py | Dashboard: prefix; IP/country access: `_access_control_prefix()`; audit alert dedupe: prefix; access_rules_version: tenant-scoped. |
| **Observability** | apps/observability/views.py, templatetags/admin_extras.py | Weather cache key prefixed in `_resolve_weather_payload(..., request)`; AI copilot metrics read via `tenant_cache_key(..., request)`; admin counts use `_admin_cache_prefix(context)`. |
| **Backend status** | apps/accounts/views.py | `tenant_cache_key(BACKEND_STATUS_FRAGMENT_CACHE_KEY, request)`. |
| **Policy** | apps/policies/resolver.py | `policy:{school_id}` (already school-scoped). |
| **Feature control** | apps/siteconfig/views_feature_control.py | `tenant_cache_key(FEATURE_CONTROL_LAST_SAVED_KEY, request)`. |
| **Security health** | apps/accounts/security_health.py | `{prefix}:security_strength:{user.pk}` (prefix from school or get_tenant_cache_prefix). |
| **Finance idempotency** | apps/finance/api_views.py | `tenant_cache_key("offline_payment_idempotency:...", request)`. |

## Keys intentionally global

- **evals/grading.py** `score_convert:*` — scale conversion is not tenant-specific.
- **siteconfig/middleware/maintenance_mode.py** `site_settings_v1` — platform maintenance flag.
- **geoip_service** `geoip:*`, `region_config:*` — global GeoIP/region data.
- **Observability health check** — test key for cache backend health.

## RLS mode

When `USE_DJANGO_TENANTS=0`, there is no `connection.tenant`. Pass `request` into `get_tenant_cache_prefix(request)` or `tenant_cache_key(base, request)` wherever possible so the prefix becomes `school:{request.school.id}`. When `request` is not available (e.g. in signals or background tasks), `get_tenant_cache_prefix(None)` returns `public`; ensure those keys do not hold tenant-specific data or use another way to attach school/tenant (e.g. from the model instance).
