# CSRF-exempt endpoints audit

All endpoints that use `@csrf_exempt` or `csrf_exempt` must be justified and documented. Review each for: reason for exemption, auth model, signature or verification, method restrictions, rate limits, and audit logging. Prefer token auth or signed webhook verification over blanket exemption.

**Enforcement:** `python scripts/lint_csrf_exempt_usage.py` with `scripts/allowlists/csrf_exempt_allowlist.json`.

## Current inventory

| File | Location | Reason for exemption | Auth model | Signature / verification | Method restrictions | Verdict |
|------|----------|----------------------|------------|--------------------------|---------------------|---------|
| apps/schools/signup_views.py | L303, L425 | Signup or verify callbacks | Session or token | Review | POST only | Keep / refactor |
| apps/finance/views.py | L1736 | Payment webhook | Webhook signature | Verify signature | POST only | Keep with strong verification |
| apps/schools/section8_views.py | L37, L566, L623, L660, L702, L745, L789, L826 | External callbacks | Review | Review | Restrict | Audit each |
| config/graphql_view.py | L15 | GraphQL token flow | Token | N/A | POST | Keep if token auth |
| apps/api/government_views.py | Import only | None | None | None | None | Check usage |
| apps/api/ceds_views.py | L69, L90, L112 | CEDS integration | Review | Review | Restrict | Audit each |
| apps/api/edfi_views.py | L73, L94, L118 | Ed-Fi integration | Review | Review | Restrict | Audit each |
| apps/api/oneroster_views.py | L113, L139, L155, L172, L196 | OneRoster | OAuth or signature | Review | Restrict | Audit each |
| apps/billing/api_views.py | L59 | Billing webhook | Signature | Verify | POST | Keep with verification |
| apps/api/scim_views.py | L164, L192, L288, L372, L386 | SCIM provisioning | Token or bearer | Review | Restrict | Audit each |
| apps/accounts/views_saml.py | L171 | SAML SSO callback | SAML assertion | SAML validation | POST | Keep with validation |
| apps/api/lead_capture_api.py | L58 | Lead capture public form | None or optional | Cache-based | POST only; rate limit 30/IP and 200/school per 15 min | Keep with rate limit |

## Completed in this hardening pass

- `apps/siteconfig/views_verify.py` no longer uses `@csrf_exempt`; it remains GET-only and rate-limited without requiring an exemption.
- `apps/api/views_v1.py` no longer uses `@csrf_exempt`; the public enrollment alias now requires CSRF like other browser-facing POST flows.

## Required remediation

1. `apps/schools/signup_views.py`: ensure token-in-URL or signed link, add IP rate limiting, audit verification attempts.
2. `apps/finance/views.py` and `apps/billing/api_views.py`: verify webhook signatures, log payload hash and verification result.
3. `apps/schools/section8_views.py`, `apps/api/ceds_views.py`, `apps/api/edfi_views.py`, `apps/api/oneroster_views.py`: document auth, restrict methods, add rate limits.
4. `config/graphql_view.py`: require auth for mutations; if exemption remains, add token and rate limits.
5. `apps/api/scim_views.py`: require bearer auth, enforce SCIM method set, add rate limits.
6. `apps/accounts/views_saml.py`: keep replay protection and full assertion validation in place.
7. `apps/api/lead_capture_api.py`: keep rate limits, consider honeypot or signed token, log submissions.
