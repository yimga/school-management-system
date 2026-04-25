# Public / Exempt Endpoint Audit Ledger

**Purpose:** Single ledger of every `csrf_exempt` and `AllowAny` usage for §2.4 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Each endpoint must be justified, with auth model, replay/signature protection, rate limiting, and audit logging. **Classification:** public (unauthenticated/incoming), tenant (school-scoped), admin (platform-only).

**Status:** **MET** — LTI 1.3 **launch callback** verifies `id_token` via **JWKS** when `lti_tool_jwks_uri` (+ optional `lti_tool_issuer`) on ServiceIntegration; strict env `LTI_REQUIRE_SIGNED_ID_TOKEN` else decode without verify. Ledger + CI gate unchanged. Test DB: `docs/TEST_DATABASE.md`.

**Verification tests:** `apps/schools/tests/test_section8_views.py` — JWKS verify success/failure, rate limit path (`_lti_rate_limited`). Implementation: `apps/schools/lti_id_token_verify.py`.

---

## 1. csrf_exempt endpoints

Source: `scripts/allowlists/csrf_exempt_allowlist.json`. Lint: `scripts/lint_csrf_exempt_usage.py`.

| File | Count | Owner | Classification | Verdict | Auth model | Replay / signature | Rate limiting | Audit logging |
|------|-------|--------|----------------|---------|------------|--------------------|---------------|---------------|
| apps/accounts/views_saml.py | 1 | identity_access | tenant | keep | signed_saml_assertion | idp_assertion_validity_window | not_applicable | **implemented** (logger.info saml_acs_success; integration_id; no PII) |
| apps/api/lead_capture_api.py | 1 | marketing_leads | public | keep | public_form_post | not_applicable | implemented | implemented |
| apps/api/scim_views.py | 3 | identity_provisioning | admin | keep | bearer_token_scim | **optional:** X-SCIM-Timestamp ±5m (_scim_replay_check); X-SCIM-Nonce dedupe (_scim_nonce_replay_check); **optional body integrity:** X-SCIM-Signature `sha256=<hex>` = HMAC-SHA256(bearer secret, raw body) (_scim_signature_check) | implemented (throttle_ip_request) | implemented (_log_scim_request: path, method, resource, authenticated; no PII) |
| apps/billing/api_views.py | 1 | billing | public | keep | provider_webhook_signature | **implemented** (HMAC + reject invalid) | not_applicable | **implemented** (BillingProcessorSyncEvent, _upsert_webhook_incident) |
| apps/finance/views.py | 1 | finance_payments | public | keep | payment_webhook_signature | **implemented** (HMAC + reject invalid) | not_applicable | **implemented** (WebhookLog, _create_webhook_log) |
| apps/schools/section8_views.py | 5 | interop_lti | tenant | keep_with_hardening | external_tool_callback | tool_signature_manual_review_required | implemented (_lti_rate_limited) | implemented (_log_lti_request: path, method, operation, tool_id; no PII) |
| config/graphql_view.py | 1 | api_platform | tenant | keep_with_hardening | mixed_client_access | not_applicable | implemented (throttle_ip_request) | implemented (logger.info op + authenticated; no PII) |

### Notes

- **SchoolConfigAPI:** Read-only host-resolved JSON; rate limit per IP. **Audit (batch 948):** `authenticated` boolean in `school_config_api_request` extra (no PII); see `apps/schools/tests/test_school_config_api_hardening.py`. **Batch 955 (III.32):** **`http_method_names`** allow **GET/HEAD/OPTIONS** only — **POST/PUT/PATCH/DELETE** → **405**; `test_batch955_control_plane_boundary`.
- **SAML:** ACS callback receives POST from IdP without browser CSRF token; validity window is replay protection.
- **Lead capture:** Public form; rate limiting implemented. **Audit logging:** implemented (logger.info for lead_capture_created and lead_capture_duplicate with school_id, applicant_id, lead_source, ip; no PII).
- **SCIM:** Bearer token; rate limit implemented. **Audit logging:** implemented (_log_scim_request for every authenticated request: path, method, resource, authenticated; no PII). **Replay / integrity:** optional `X-SCIM-Timestamp` window, optional `X-SCIM-Nonce` deduplication, optional `X-SCIM-Signature` HMAC over raw body (see Section 6 table).
- **Billing/Finance webhooks:** **Done.** Signature verification in place; reject missing or invalid with 401. Audit: Billing uses `BillingProcessorSyncEvent` and `_upsert_webhook_incident`; Finance uses `WebhookLog` and `_create_webhook_log` for all attempts. See `apps/billing/api_views.py`, `apps/finance/views.py` webhook handlers.
- **Section8 (LTI):** OIDC launch callback verifies `id_token` via tool JWKS when `lti_tool_jwks_uri` is set; rate limit + audit (_lti_rate_limited, _log_lti_request). AGS/NRPS/deep-linking: Bearer to integration secret.
- **GraphQL:** Rate limit implemented (throttle_ip_request GET 60/min, POST 120/min). Audit logging implemented: logger.info for each POST with operation_name (or "(anonymous)") and authenticated flag; no PII (public_endpoint_audit §2.4).

---

## 2. AllowAny usage

Source: `scripts/allowlists/allow_any_allowlist.json`. Lint: `scripts/lint_allow_any_usage.py`.

| File | Count | Owner | Verdict | Auth model | Data exposure | Rate limiting | Audit logging |
|------|-------|--------|---------|------------|---------------|---------------|---------------|
| apps/schools/api_views.py | 2 | tenant_bootstrap_api | keep | public_host_resolved_read_only | branding_and_feature_flags_only | implemented | **implemented** (logger.info school_config_api_request: host, school_id, authenticated; no PII) |

### Notes

- SchoolConfigAPI: read-only; host-resolved branding and offline capability for SPA/mobile; no secrets. **955:** framework-enforced GET-only (see §6 table).

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
| **SCIM** (apps/api/scim_views.py) | Bearer token. Optional **X-SCIM-Timestamp** (Unix sec): reject outside 5 min (`_scim_replay_check`). Optional **X-SCIM-Nonce**: reject duplicate nonce within same window via cache (`_scim_nonce_replay_check`). Optional **X-SCIM-Signature** `sha256=<hex>` = HMAC-SHA256(bearer secret, `request.body`) (`_scim_signature_check`, PATH Phase II.1). | **REPLAY + NONCE + OPTIONAL HMAC DONE** | Rate limit + `_log_scim_request`. Tests: `apps/api/tests/test_scim_views.py`. |
| **Section8 LTI** (section8_views + lti_id_token_verify.py) | LTI 1.3: verify `id_token` with tool JWKS when configured. | **IMPLEMENTED (JWKS path)** | JWKS verify when `lti_tool_jwks_uri` set; 401 on bad sig. OAuth 1.0a body paths unchanged. _lti_rate_limited + _log_lti_request. |
| **SAML ACS** (apps/accounts/views_saml.py) | Replay: IdP assertion validity window (NotBefore/NotOnOrAfter). No additional HMAC; IdP signs assertion. | **DONE** (replay + audit) | Replay via assertion validity. Audit: logger.info("saml_acs_success", extra=acs_request_id=relay_state, integration_id, authenticated=True) after successful login (no PII). |
| **SchoolConfigAPI** (apps/schools/api_views.py, AllowAny) | N/A (read-only; host-resolved). | **DONE** (audit + verb bind) | Audit: logger.info("school_config_api_request", extra=host, school_id if resolved, authenticated) for abuse monitoring (no PII). **Batch 948:** authenticated flag (§6.12 / III.31). **Batch 955:** **`http_method_names`** GET/HEAD/OPTIONS only (§6.12 / III.32); tests `test_batch955_control_plane_boundary`. |
| **GraphQL** (config/graphql_view.py) | N/A (mixed client; session/cookie or token). | **N/A** | Rate limit + audit (operation_name, authenticated) implemented. |

**Summary:** Billing/Finance webhooks: **DONE**. LTI launch callback: **JWKS path DONE** (configure `lti_tool_jwks_uri`). SCIM: Bearer + optional timestamp, nonce, and body HMAC. SAML: replay **DONE**. SchoolConfigAPI / GraphQL as above.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
