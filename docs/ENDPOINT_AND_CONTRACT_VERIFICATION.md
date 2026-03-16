# Endpoint Classification and Contract Verification (III.71, III.76)

**Purpose:** Single reference for API endpoint classification (public / tenant / admin) and contract tests so PATH_TO_100 III.71 and III.76 are verifiable. See [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §6.24.

---

## Endpoint classification (III.71)

- **Ledger:** [public_endpoint_audit.md](public_endpoint_audit.md) — every `csrf_exempt` and `AllowAny` endpoint is recorded with:
  - Classification: **public** (unauthenticated/incoming), **tenant** (school-scoped), **admin** (platform-only)
  - Auth model, replay/signature protection, rate limiting, audit logging, verdict
- **CI:** `scripts/lint_csrf_exempt_usage.py`, `scripts/lint_allow_any_usage.py`; `scripts/pre_deploy_gate.sh` runs these; regressions fail the gate.
- **Extending:** When adding new public/exempt endpoints, add a row to the ledger and update the allowlist; run lints before merge.

---

## Contract tests (III.76)

- **Runtime:** `apps/platform_runtime/tests/test_runtime_contract.py` — resolver registry, compilation order, get_effective_site_settings, get_effective_flags_for_school, INTEGRATION_CATALOG. See [runtime_resolvers_and_contracts.md](runtime_resolvers_and_contracts.md).
- **Precedence:** `apps/platform_runtime/tests/test_precedence.py` — runtime precedence and tenant isolation.
- **API Center / governance:** `apps/apicenter/tests/test_governance_contract.py` — dashboard auth, Integration, _api_center_allowed.
- **CI:** `scripts/pre_deploy_gate.sh` runs targeted tests including platform_runtime contract tests.
- **Expanding:** Add contract tests for API ↔ runtime, API ↔ packages, events when product prioritizes; current coverage: runtime + API Center governance.

---

## Verification

- **Endpoints:** Open public_endpoint_audit.md; run `python scripts/lint_csrf_exempt_usage.py` and `python scripts/lint_allow_any_usage.py` (or pre_deploy_gate).
- **Contracts:** Run `python manage.py test apps.platform_runtime.tests.test_runtime_contract apps.platform_runtime.tests.test_precedence apps.apicenter.tests.test_governance_contract --no-input`.

---

*SOT ref: §6.24 III.71, III.76; NA_REGISTER: full classification and contract expansion N/A product 2026-03-12.*
