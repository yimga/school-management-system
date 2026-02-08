# Phase 13 Security and Performance Notes

Date: 2026-02-08

## Scope
- Redirect safety checks for `next` parameters in high-traffic admin/support flows.
- Input hardening for request dashboard pagination.
- Query optimization for report card builder assignment previews.

## Findings and Fixes

1. Open redirect risk in multiple views using raw `next` values
- Risk:
  - External URLs from query/body parameters could be redirected to directly.
- Fixed in:
  - `apps/siteconfig/views.py`
  - `apps/accounts/views_mfa.py`
  - `apps/requests/views.py`
- Implementation:
  - Added URL safety helpers using `url_has_allowed_host_and_scheme`.
  - Redirects now allow only current-host or relative URLs.
  - Unsafe values fall back to deterministic internal routes.

2. Fragile pagination parsing in requests dashboard
- Risk:
  - Invalid `page_size` values caused `ValueError` and could return 500.
- Fixed in:
  - `apps/requests/views.py`
- Implementation:
  - Added `_safe_int(...)` parsing with bounds (`10..100`) and default fallback.

3. N+1 query pattern in report card builder sample lookup
- Risk:
  - One query per classroom assignment degraded performance as assignments scale.
- Fixed in:
  - `apps/siteconfig/views.py`
- Implementation:
  - Replaced per-assignment `first()` queries with a single ordered queryset.
  - Built a `classroom_id -> first student` map in memory.

## Regression Coverage Added
- `apps/siteconfig/tests/test_redirect_safety.py`
- `apps/requests/tests/test_views_security.py`
- `apps/accounts/tests/test_mfa_redirect_safety.py`

## Residual Notes
- Existing raw SQL in migrations/health checks remains intentionally scoped and not user-controlled.
- No user-controlled `filter(**request.GET)` pattern was identified in active request handlers during this pass.
