# API Center Integration Governance

**Purpose:** §5.8 and §6.24 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Turn API Center into integration governance console; classify endpoints, harden auth, reduce public exposure. Nothing deferred.

**Status:** **MET (repo baseline)** — API Center dashboard (integrations, rate limits/quotas, audit log, toggles); `apps.apicenter.tests.test_governance_contract`. **§11.4 / NOT DONE:** per-endpoint hardening sweep + interop validation workbench (explicit backlog).

---

## 1. Integration governance scope

API Center as integration governance console must provide:

| Capability | Status | Notes |
|------------|--------|-------|
| Classify endpoints | MET (baseline) | Public/exempt ledger (public_endpoint_audit.md); internal vs public vs webhook modeled |
| Auth/signature/rate limiting | MET (baseline) + §11.4 | Allowlist + audits; tighten where `manual_review_required` remains |
| Reduce public/exempt exposure | Done (audit) | Allowlist + CI; remove unnecessary exemptions |
| Integration catalog | Present | INTEGRATION_CATALOG; API Center surfaces |
| Scope/permission visibility | MET (baseline) | Dashboard surfaces scope/permission/rate/audit per integration |
| Contract testing | MET (baseline) | `test_governance_contract`; broader cross-surface contracts = §11.4 |
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

- [x] API Center is the integration governance console (classify, harden, visibility, contract tests). **Repo spine MET**; per-endpoint hardening + interop workbench = **§11.4** depth (tracked in SOT **§11.4**, not “open §3 architecture” spine).
- [ ] Public surfaces hardened; no unjustified exemptions.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §5.8, §6.24.*
