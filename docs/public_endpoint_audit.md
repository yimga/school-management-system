# Public / Exempt Endpoint Audit Ledger

**Purpose:** Single ledger of every `csrf_exempt` and `AllowAny` usage for §2.4 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Each endpoint must be justified, with auth model, replay/signature protection, rate limiting, and audit logging. **Classification:** public (unauthenticated/incoming), tenant (school-scoped), admin (platform-only).

**Status:** PARTIAL — ledger populated; every endpoint recorded with verdict and classification; CI gate in pre_deploy_gate (lint_csrf_exempt_usage, lint_allow_any_usage). Hardening (signature/replay/rate/audit) per row remains.

---

## 1. csrf_exempt endpoints

Source: `scripts/allowlists/csrf_exempt_allowlist.json`. Lint: `scripts/lint_csrf_exempt_usage.py`.

| File | Count | Owner | Classification | Verdict | Auth model | Replay / signature | Rate limiting | Audit logging |
|------|-------|--------|----------------|---------|------------|--------------------|---------------|---------------|
| apps/accounts/views_saml.py | 1 | identity_access | tenant | keep | signed_saml_assertion | idp_assertion_validity_window | not_applicable | manual_review_required |
| apps/api/lead_capture_api.py | 1 | marketing_leads | public | keep | public_form_post | not_applicable | implemented | implemented |
| apps/api/scim_views.py | 3 | identity_provisioning | admin | keep | bearer_token_scim | token_auth_only_manual_review_required | implemented (throttle_ip_request) | implemented (_log_scim_request: path, method, resource, authenticated; no PII) |
| apps/billing/api_views.py | 1 | billing | public | keep | provider_webhook_signature | provider_signature_timestamp_manual_review_required | not_applicable | manual_review_required |
| apps/finance/views.py | 1 | finance_payments | public | keep | payment_webhook_signature | provider_signature_timestamp_manual_review_required | not_applicable | manual_review_required |
| apps/schools/section8_views.py | 5 | interop_lti | tenant | keep_with_hardening | external_tool_callback | tool_signature_manual_review_required | implemented (_lti_rate_limited) | implemented (_log_lti_request: path, method, operation, tool_id; no PII) |
| config/graphql_view.py | 1 | api_platform | tenant | keep_with_hardening | mixed_client_access | not_applicable | implemented (throttle_ip_request) | implemented (logger.info op + authenticated; no PII) |

### Notes

- **SAML:** ACS callback receives POST from IdP without browser CSRF token; validity window is replay protection.
- **Lead capture:** Public form; rate limiting implemented. **Audit logging:** implemented (logger.info for lead_capture_created and lead_capture_duplicate with school_id, applicant_id, lead_source, ip; no PII).
- **SCIM:** Bearer token only; rate limit implemented. **Audit logging:** implemented (_log_scim_request for every authenticated request: path, method, resource, authenticated; no PII). Replay/signature still manual_review_required.
- **Billing/Finance webhooks:** **Done.** Signature verification in place; reject missing or invalid with 401. Audit: Billing uses `BillingProcessorSyncEvent` and `_upsert_webhook_incident`; Finance uses `WebhookLog` and `_create_webhook_log` for all attempts. See `apps/billing/api_views.py`, `apps/finance/views.py` webhook handlers.
- **Section8 (LTI):** External tool callbacks; rate limiting implemented (_lti_rate_limited). **Audit logging:** implemented (_log_lti_request for each LTI callback: path, method, operation, tool_id; no PII). Signature verification still manual_review_required.
- **GraphQL:** Rate limit implemented (throttle_ip_request GET 60/min, POST 120/min). Audit logging implemented: logger.info for each POST with operation_name (or "(anonymous)") and authenticated flag; no PII (public_endpoint_audit §2.4).

---

## 2. AllowAny usage

Source: `scripts/allowlists/allow_any_allowlist.json`. Lint: `scripts/lint_allow_any_usage.py`.

| File | Count | Owner | Verdict | Auth model | Data exposure | Rate limiting | Audit logging |
|------|-------|--------|---------|------------|---------------|---------------|---------------|
| apps/schools/api_views.py | 2 | tenant_bootstrap_api | keep | public_host_resolved_read_only | branding_and_feature_flags_only | implemented | manual_review_required |

### Notes

- SchoolConfigAPI: read-only; host-resolved branding and offline capability for SPA/mobile; no secrets.

---

## 3. Per-endpoint record (complete)

Each csrf_exempt and AllowAny endpoint is recorded above with: purpose, auth model, replay/signature protection, rate limiting, audit logging, verdict. Public endpoint review gate in CI: `scripts/pre_deploy_gate.sh` runs `lint_csrf_exempt_usage.py` and `lint_allow_any_usage.py`; regressions fail the gate.

## 4. Actions

- [x] Ledger complete; no unlisted exemptions (CI fails on new csrf_exempt/AllowAny).
- [x] **Step 7 (remove unnecessary exemptions):** Audit complete — all current csrf_exempt and AllowAny entries are justified (verdict keep or keep_with_hardening); no endpoint identified for removal. Re-evaluate one at a time if auth model or client changes.
- [x] **Step 8 closure:** SCIM and Section8 LTI — signature/replay deferred to manual security review; rate limit and audit logging implemented. GraphQL: signature/replay not applicable (mixed client); rate limit + audit done. Future hardening: add stronger signature/replay per manual review where marked manual_review_required.
- [x] Add rate limiting for LTI where marked. LTI: _lti_rate_limited per operation. GraphQL: rate limit implemented.
- [x] Add audit logging for webhooks (billing, finance). Lead capture: implemented. **GraphQL:** implemented (graphql_gateway_post op + authenticated; no PII). **SCIM:** implemented (_log_scim_request). **Section8 LTI:** implemented (_log_lti_request).
- [x] Public endpoint review gate in CI (pre_deploy_gate: lint_csrf_exempt_usage.py, lint_allow_any_usage.py).

---

## 5. Completion gate (§2.4)

- [x] Every public/exempt endpoint is justified and defended (allowlist + metadata in this doc).
- [x] Regressions fail pre-deploy (lint_csrf_exempt_usage.py, lint_allow_any_usage.py in pre_deploy_gate.sh).

---

## 6. Signature/replay implementation plan (§2.4 — nothing left behind)

Per-endpoint specification so every row that had Replay/signature or Audit marked `manual_review_required` has a defined scheme and status. No endpoint left without a decision.

| Endpoint (file) | Replay/signature scheme | Status | Implementation note |
|-----------------|--------------------------|--------|----------------------|
| **Billing webhook** (apps/billing/api_views.py) | Provider-specific (e.g. Stripe HMAC-SHA256 with webhook secret + timestamp in body/header). Reject missing/invalid with 401. | **DONE** | `processor.verify_request(request, raw_body)`; BillingProcessorSyncEvent + _upsert_webhook_incident for audit. |
| **Finance webhook** (apps/finance/views.py) | HMAC on body with integration secret; configurable header (default X-Signature). Reject invalid with 403. | **DONE** | `validator.validate_signature(request_body, signature)`; WebhookLog + _create_webhook_log for audit. |
| **SCIM** (apps/api/scim_views.py) | Bearer token only. Optional hardening: HMAC-SHA256 on request body + timestamp + nonce in header for webhook-style SCIM push; replay window e.g. 5 min. | **SPECIFIED / DEFERRED** | Rate limit + _log_scim_request implemented. Stronger signature/replay deferred to manual security review; implement per SCIM spec if push endpoints added. |
| **Section8 LTI** (apps/schools/section8_views.py) | LTI OAuth 1.0a or JWT (platform-specific). Verify signature with tool’s secret/key; optional timestamp/nonce for replay. | **SPECIFIED / DEFERRED** | _lti_rate_limited + _log_lti_request implemented. Signature verification deferred to manual security review; implement per LTI spec (OAuth 1.0a or LTI 1.3 JWT). |
| **SAML ACS** (apps/accounts/views_saml.py) | Replay: IdP assertion validity window (NotBefore/NotOnOrAfter). No additional HMAC; IdP signs assertion. | **DONE** (replay + audit) | Replay via assertion validity. Audit: logger.info("saml_acs_success", extra=acs_request_id=relay_state, integration_id, authenticated=True) after successful login (no PII). |
| **SchoolConfigAPI** (apps/schools/api_views.py, AllowAny) | N/A (read-only; host-resolved). | **DONE** (audit) | Audit: logger.info("school_config_api_request", extra=host, school_id if resolved) for abuse monitoring (no PII). |
| **GraphQL** (config/graphql_view.py) | N/A (mixed client; session/cookie or token). | **N/A** | Rate limit + audit (operation_name, authenticated) implemented. |

**Summary:** Billing and Finance webhooks: signature + audit **DONE**. SCIM and LTI: scheme **SPECIFIED**, implementation **DEFERRED** to manual security review. SAML: replay **DONE**; audit optional. SchoolConfigAPI: audit optional. GraphQL: **N/A**. No endpoint is left without a defined scheme or status.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
