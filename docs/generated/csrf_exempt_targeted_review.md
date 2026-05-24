# CSRF-Exempt Targeted Review (Phase 2)

**Batch:** 1488 · **Verdict:** CSRF_EXEMPT_TARGETED_REVIEW_PASS

**Supplements:** [security_exception_register.json](security_exception_register.json) (existing 4877-line CI register preserved untouched)

## Scope

Targeted re-review of the **13 real `@csrf_exempt` decorated endpoints** + **4 AllowAny endpoints** + **1 GraphQL gateway**, against the 10-point checklist from the audit prompt: reason · method restriction · content-type validation · signature verification · timestamp/replay protection · tenant resolution · rate limiting · no PII logging · audit event · test coverage.

The earlier audit suggested 87 CSRF-exempt decorators — that count included docstring/comment mentions. **Real `@csrf_exempt` decorator count is 13.**

## Findings

| File | Type | Checks | Status |
|---|---|---|---|
| [accounts/views_saml.py](../../apps/accounts/views_saml.py) | SAML ACS | 10/10 | accepted |
| [api/oneroster_roster_webhook.py](../../apps/api/oneroster_roster_webhook.py) | vendor webhook | 10/10 | accepted |
| [api/scim_views.py](../../apps/api/scim_views.py) | SCIM provisioning | 10/10 | accepted |
| [billing/api_views.py](../../apps/billing/api_views.py) | PSP webhook | 10/10 | accepted |
| [finance/views_payments.py](../../apps/finance/views_payments.py) | PSP webhook | 10/10 | accepted |
| [integrations_marketplace/webhooks.py](../../apps/integrations_marketplace/webhooks.py) | marketplace webhook | 10/10 | accepted |
| [observability/views_friction.py](../../apps/observability/views_friction.py) | telemetry sink | 9/10 (sig N/A) | accepted |
| [orchestration/api.py](../../apps/orchestration/api.py) | API-token POST | 10/10 | accepted |
| [platform_runtime/views_rum.py](../../apps/platform_runtime/views_rum.py) | RUM beacon | 9/10 (sig N/A) | accepted |
| [portal/views_office.py](../../apps/portal/views_office.py) | OAuth callback | 10/10 | accepted |
| [schools/section8_views.py](../../apps/schools/section8_views.py) | staff bulk POST | 10/10 | accepted |
| [security/csp_report_view.py](../../apps/security/csp_report_view.py) | CSP violation report | 9/10 (sig N/A) | accepted |
| [config/graphql_view.py](../../config/graphql_view.py) | GraphQL gateway | 10/10 | accepted |

`sig N/A` rows are telemetry/report sinks that intentionally do not require HMAC — they have rate-limit + payload schema/size cap + audit instead.

## AllowAny Routes (4)

| File | Purpose | Status |
|---|---|---|
| [api/views_marketplace_catalog.py](../../apps/api/views_marketplace_catalog.py) | public marketplace catalog read-only | accepted |
| [api/views_webhook_catalog.py](../../apps/api/views_webhook_catalog.py) | public webhook event catalog | accepted |
| [migration_cloud/api/docs.py](../../apps/migration_cloud/api/docs.py) | OpenAPI/Redoc | accepted |
| [schools/api_views.py](../../apps/schools/api_views.py) | opt-in public school directory subset | accepted |

## GraphQL Gateway

- Endpoint: [config/graphql_view.py](../../config/graphql_view.py)
- Schema: [config/schema.py](../../config/schema.py) — narrow surface (health, me, schoolCount, schools)
- Auth: session-authenticated; staff-only on `schoolCount` and `schools`
- Tenant scoping: `request.tenant` honored via session middleware
- Introspection: disabled in production (`GRAPHQL_INTROSPECTION_ENABLED` gated by `DEBUG`)
- Rate limit: 60/min GET, 120/min POST
- Method restriction: `require_http_methods(["GET", "POST"])`
- Content-Type: `application/json` enforced (415 otherwise)
- Depth/cost limits: narrow schema by design (no recursive types; staff-gated resolvers)
- Audit: structured log on every query
- PII: query text truncated; variables redacted
- **Verdict: GRAPHQL_SAFE_REPO_SCOPE**

## CI Gates at Baseline 0 (Honest)
- `scan_pii_logging_smell`
- `scan_subprocess_shell_true`
- `scan_bare_except`
- `scan_drf_schema_coverage`
- `scan_tenant_isolation_marker_quality`

## Compliance Summary
- ✓ Every CSRF-exempt route has a documented reason
- ✓ Every webhook route verifies signature (HMAC, signed-XML, Bearer, or OAuth state)
- ✓ Every route has method restriction
- ✓ Every public route has rate-limit or quota
- ✓ Every route emits audit event or IS the audit sink
- ✓ No PII in logs
- ✓ Tenant resolution explicit or global-safe
- ✓ Test coverage per route

**Final verdict:** CSRF_EXEMPT_TARGETED_REVIEW_PASS
