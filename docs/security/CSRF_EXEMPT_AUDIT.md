# CSRF-exempt endpoints audit

All endpoints that use `@csrf_exempt` or `csrf_exempt` must be justified and documented. Review each for: reason for exemption, auth model, signature or verification, method restrictions, rate limits, and audit logging. Prefer token auth or signed webhook verification over blanket exemption.

**Enforcement:** `python scripts/lint_csrf_exempt_usage.py` with `scripts/allowlists/csrf_exempt_allowlist.json`.

## Current inventory

| File | Location | Reason for exemption | Auth model | Signature / verification | Method restrictions | Verdict |
|------|----------|----------------------|------------|--------------------------|---------------------|---------|
| apps/finance/views.py | L1736 | Payment webhook | Webhook signature | Verify signature | POST only | Keep with strong verification |
| apps/schools/section8_views.py | L565, L622, L659, L701, L823 | Cross-origin LTI callbacks and service APIs | Tool auth and signed state | Tool-specific auth checks | Restricted to LTI callback and service methods | Keep while external-tool flows remain server-to-server |
| config/graphql_view.py | L15 | GraphQL token flow | Token | N/A | POST | Keep if token auth |
| apps/api/government_views.py | Import only | None | None | None | None | Check usage |
| apps/billing/api_views.py | L59 | Billing webhook | Signature | Verify | POST | Keep with verification |
| apps/api/scim_views.py | L191, L287, L384 | SCIM provisioning mutation and detail flows | Bearer token | SCIM bearer validation | Restricted to SCIM methods | Keep while external IdP provisioning stays non-browser |
| apps/accounts/views_saml.py | L171 | SAML SSO callback | SAML assertion | SAML validation | POST | Keep with validation |
| apps/api/lead_capture_api.py | L58 | Lead capture public form | None or optional | Cache-based | POST only; rate limit 30/IP and 200/school per 15 min | Keep with rate limit |

## Completed in this hardening pass

- `apps/siteconfig/views_verify.py` no longer uses `@csrf_exempt`; it remains GET-only and rate-limited without requiring an exemption.
- `apps/api/views_v1.py` no longer uses `@csrf_exempt`; the public enrollment alias now requires CSRF like other browser-facing POST flows.
- `apps/schools/signup_views.py` no longer exempts browser-owned trial signup and brand-import POSTs; they now rely on normal CSRF protection.
- `apps/api/ceds_views.py`, `apps/api/edfi_views.py`, and `apps/api/oneroster_views.py` no longer exempt GET-only machine reads.
- `apps/api/scim_views.py` and `apps/schools/section8_views.py` no longer exempt GET-only discovery/read endpoints where CSRF never applied.

## Required remediation

1. `apps/finance/views.py` and `apps/billing/api_views.py`: verify webhook signatures, log payload hash and verification result.
2. `apps/schools/section8_views.py`: keep only the cross-origin LTI callback/service exemptions, and document each auth boundary.
3. `config/graphql_view.py`: require auth for mutations; if exemption remains, add token and rate limits.
4. `apps/api/scim_views.py`: keep bearer auth, enforce SCIM method set, and add stronger request logging.
5. `apps/accounts/views_saml.py`: keep replay protection and full assertion validation in place.
6. `apps/api/lead_capture_api.py`: keep rate limits, consider honeypot or signed token, log submissions.
