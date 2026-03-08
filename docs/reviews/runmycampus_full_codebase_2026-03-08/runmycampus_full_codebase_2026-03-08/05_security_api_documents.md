# Security, API, and Documents

Date: 2026-03-08

## Summary

Security and API maturity are mixed. There are good defensive pieces in place, but there are also unnecessary exposures, inconsistent enforcement paths, and production-visible stub surfaces.

## 1. MFA and Passkeys

Observed:

- `apps/accounts/middleware.py:373-389` counts passkeys as MFA-capable
- `apps/accounts/views_security.py:75-100` previously did not

Risk:

- different parts of the product disagree on what counts as configured MFA

Status:

- fixed in this review
- verified by `apps/accounts/tests/test_security_export_mfa.py`

## 2. Public School Config Exposure

Observed:

- `apps/schools/api_views.py:27` uses `AllowAny`
- `apps/schools/api_views.py:34-40` returns global offline and feature payload for no-school requests
- `apps/schools/api_views.py:45-51` returns tenant branding plus `features` and `offlineEnabled`

Risk:

- unauthenticated clients can enumerate feature posture and branding metadata
- this may be acceptable for a thin public bootstrap endpoint, but it should be intentionally minimized

Required action:

- return only the minimum public bootstrap contract
- keep entitlement-like details authenticated or signed if mobile clients need them

## 3. Search Surface

Observed:

- `apps/api/search_api.py:272-285` now scopes subject search by school and serializes existing fields only
- `apps/api/search_api.py:256-270` classroom search is school-scoped but not role-constrained

Risk:

- search is a cross-cutting data surface and should be treated like an access boundary, not just a convenience endpoint

## 4. Compliance Middleware Boundaries

Observed:

- `apps/compliance/middleware.py:255-271` bypasses a wide path set including `/super/`
- `apps/compliance/middleware.py:332-334` and `apps/compliance/middleware.py:442-444` return inline HTML strings for 403s

Risk:

- bypasses should be justified individually, not accumulated casually
- inline HTML response bodies reduce consistency and make policy handling harder to test and reuse

## 5. Roadmap and Stub Endpoints in Production API Space

Observed:

- `apps/api/urls.py:185-214` exposes many `/api/roadmap/*` endpoints
- `apps/api/roadmap_extended_views.py:37-47`, `56-112`, `133-243` openly return `"status": "stub"` or backlog language

Risk:

- the production API namespace is carrying roadmap communication duties
- clients, docs, and security reviews must reason about endpoints that are not genuine product capabilities

Recommended boundary:

- keep production API for supported capabilities
- move roadmap and maturity-status endpoints behind manager/control-plane scope or documentation pages

## 6. Document and Compliance Surface Mismatch

Observed:

- the architecture index advertises strong document lifecycle and search architecture completion at `docs/architecture/README.md:21-29`
- runtime enforcement still uses mixed middleware patterns, hardcoded fallbacks, and incomplete generalized document/nav behavior

Assessment:

- the document/governance model is not empty
- but the docs currently read as more complete than the behavior they describe

## Security/API Verdict

The immediate security priority is not adding more controls. It is reducing inconsistency:

1. one MFA definition
2. one search visibility model
3. one error response contract
4. one public bootstrap contract
5. one clear boundary between supported APIs and roadmap placeholders
