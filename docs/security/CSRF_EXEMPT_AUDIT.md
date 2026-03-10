# CSRF-exempt endpoints audit

All endpoints that use `@csrf_exempt` or `csrf_exempt` must be justified and documented. Review each for: reason for exemption, auth model, signature/verification, method restrictions, rate limits, audit logging. Prefer token auth or signed webhook verification over blanket exemption.

| File | Location | Reason for exemption | Auth model | Signature / verification | Method restrictions | Verdict |
|------|----------|----------------------|------------|--------------------------|---------------------|---------|
| apps/schools/signup_views.py | L303, L425 | Signup/verify callbacks | Session or token | Review | POST only | Keep / refactor |
| apps/api/views_v1.py | L54, L613, L1238, L1333, L1454, L1505, L1604, L1719, L1829 | API machine-to-machine | API key / token | Review each | Restrict methods | Audit each |
| apps/finance/views.py | L1736 | Payment webhook | Webhook signature | Verify signature | POST only | Keep with strong verification |
| apps/schools/section8_views.py | L37, L566, L623, L660, L702, L745, L789, L826 | Section 8 / external | Review | Review | Restrict | Audit each |
| config/graphql_view.py | L15 | GraphQL (often token-based) | Token | N/A | POST | Keep if token auth |
| apps/api/government_views.py | Import only | — | — | — | — | Check usage |
| apps/api/ceds_views.py | L69, L90, L112 | CEDS integration | Review | Review | Restrict | Audit each |
| apps/api/edfi_views.py | L73, L94, L118 | Ed-Fi integration | Review | Review | Restrict | Audit each |
| apps/api/oneroster_views.py | L113, L139, L155, L172, L196 | OneRoster | OAuth/signature | Review | Restrict | Audit each |
| apps/billing/api_views.py | L59 | Billing webhook | Signature | Verify | POST | Keep with verification |
| apps/api/scim_views.py | L164, L192, L288, L372, L386 | SCIM provisioning | Token / bearer | Review | Restrict | Audit each |
| apps/accounts/views_saml.py | L171 | SAML SSO callback | SAML assertion | SAML validation | POST | Keep with validation |
| apps/api/lead_capture_api.py | L58 | Lead capture (public form) | None / optional | Cache-based | POST only; **rate limit 30/IP and 200/school per 15 min** | Keep with rate limit |
| apps/siteconfig/views_verify.py | L27 | Student ID verify (public) | Token in URL | rate_limit_verify(ip) | GET only; **rate limited** | Keep with token + rate limit |

**Actions:** For each row, confirm auth and signature; add rate limits and audit logs where missing; refactor or remove unjustified exemptions.

## Remediation next steps

1. **Signup/verify** — Ensure token-in-URL or signed link; rate limit by IP; audit log verification attempts.
2. **API views_v1** — Replace CSRF exempt with DRF token/session auth where possible; for machine-to-machine keep exempt but require API key header and rate limit.
3. **Finance webhook** — Confirm signature verification (e.g. Stripe webhook secret); log payload hash and result.
4. **Section 8 / CEDS / Ed-Fi / OneRoster** — Document required auth (OAuth, API key); add method restrictions (POST only where applicable); rate limit.
5. **GraphQL** — Ensure authentication required for mutations; if exempt for legacy client, add token and rate limit.
6. **Billing webhook** — Same as finance: verify signature, log.
7. **SCIM** — Bearer token required; restrict to POST/PATCH/DELETE as per SCIM spec; rate limit.
8. **SAML** — Keep; ensure SAML response validation and replay check.
9. **Lead capture** — Add rate limit (per-IP); consider honeypot or token; audit log submissions.
10. **views_verify** — Ensure token is single-use and expiry; rate limit.
11. Create a follow-up ticket per app to implement the above and re-audit.
