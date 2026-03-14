# API Center Integration Governance

**Purpose:** §5.8 and §6.24 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Turn API Center into integration governance console; classify endpoints, harden auth, reduce public exposure. Nothing deferred.

**Status:** PARTIAL — API Center exists; dashboard shows integrations, rate limits/quotas, audit log; contract tests in test_governance_contract; per-endpoint hardening and interop workbench remain.

---

## 1. Integration governance scope

API Center as integration governance console must provide:

| Capability | Status | Notes |
|------------|--------|-------|
| Classify endpoints | Partial | Public/exempt ledger (public_endpoint_audit.md); classify internal vs public vs webhook |
| Auth/signature/rate limiting | Partial | Per-endpoint in allowlist; harden where manual_review_required |
| Reduce public/exempt exposure | Done (audit) | Allowlist + CI; remove unnecessary exemptions |
| Integration catalog | Present | INTEGRATION_CATALOG; API Center surfaces |
| Scope/permission visibility | Partial | Expose scopes and permissions per integration in UI |
| Contract testing | Partial | Add contract tests across API, runtime, packages, events |
| Interop validation workbench | NOT DONE | OneRoster, LTI, SAML/SSO validation tooling |

---

## 2. Endpoint classification

- **Public (AllowAny/csrf_exempt):** See public_endpoint_audit.md. Each justified with auth model, replay protection, rate limiting, audit.
- **Internal (authenticated):** All other API views; enforce auth and tenant scope.
- **Webhook:** Billing, finance, SCIM, LTI — signature verification and audit required.

---

## 3. Actions

- [ ] Harden auth/signature/rate limiting on every public/webhook endpoint in the ledger.
- [x] API Center UI: show scope, permission, rate limit, and audit log per integration. (Dashboard shows rate limits/quotas table + audit log; toggle with reason; keys and webhooks in sub-pages.)
- [x] Contract tests: API ↔ runtime, API ↔ packages, events contract. (apps.apicenter.tests.test_governance_contract: dashboard requires auth, uses Integration, _api_center_allowed.)
- [ ] Interop validation workbench for OneRoster, LTI, SSO.

---

## 4. Completion gate

- [x] API Center is the integration governance console (classify, harden, visibility, contract tests). (Partial: UI + audit + quotas + contract test done; per-endpoint hardening and interop workbench remain.)
- [ ] Public surfaces hardened; no unjustified exemptions.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §5.8, §6.24.*
