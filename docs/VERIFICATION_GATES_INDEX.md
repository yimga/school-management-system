# Verification Gates Index

**Purpose:** Single index of how to verify §12 completion gates, Phase H, lints, and key ledgers so teams know what to run and where to look. Authority: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §12, §11 Phase H.

**Do not claim 9.5/10 or higher until §12 gates are satisfied and evidence is recorded.**

---

## 1. §12 completion gates (SOT §12.1)

| Gate | How to verify | In CI |
|------|----------------|-------|
| siteconfig materially decomposed | lint_tenant_settings --check-get-solo-only; lint_siteconfig_legacy_imports; site_settings_usage_inventory.md; domain_ownership | Yes |
| SiteSettings not tenant-behavior truth | Same; runtime resolvers; get_effective_site_settings(request) in tenant paths | Yes |
| runtime only legal behavior engine | test_runtime_contract, runtime_precedence.md, runtime inspector | Yes (targeted tests) |
| AI secrets safe | lint_secret_exposure; no provider keys in templates | Yes |
| public surfaces hardened | public_endpoint_audit.md; lint_csrf_exempt_usage; lint_allow_any_usage; lint_raw_sql_usage; lint_broad_except --strict; webhooks 401 on invalid signature | Yes (all four lints) |
| Gilead residue gone | Migration 0155 applied; lint_gilead_residue; no live UI/defaults | Yes |
| Studio OS replaces fragmented tools | Shell + five mode hubs (Experience, Automation, Output, Launch, Control); BACKLOG §4.1 | No (manual/staging) |
| package engine production-grade | Package validate/preview/apply/rollback; apps/packages tests | Yes |
| marketplace/packs productized | MARKETPLACE_SEED_TARGETS.md; test_marketplace_catalog_minimums; generate_platform_inventory --check | Yes |
| docs truth no contradictions | DOCS_TRUTH_AUDIT; key docs disclaim §12; no 9.5 claim until §12 | Yes (audit) |
| marketing front platform-grade | MARKETING_FRONT_PLACEHOLDER.md; fallbacks for all context keys; static/images/marketing/ | Yes (doc + code) |

**One-liner:** `bash scripts/pre_deploy_gate.sh` runs all CI checks above that are marked "Yes."

**Record output:** `bash scripts/record_pre_deploy_gate_output.sh` → docs/generated/pre_deploy_gate_run.txt (RELEASE_CHECKLIST).

---

## 2. Phase H verification

| Check | Command / doc |
|-------|----------------|
| Phase H UX (critical paths, URL reverse) | `python manage.py test apps.accounts.tests.test_phase_h_ux_verification` (DB required) |
| Smoke URLs | `python manage.py test apps.accounts.tests.test_smoke_urls` |
| Phase H audit (static) | `python scripts/phase_h_audit.py` |
| Phase H audit (live URL resolve) | `python scripts/phase_h_audit.py --live` |
| Phase H URL check (resolve names) | `python scripts/phase_h_url_check.py` |
| Phase H URL check (GET with server) | `python scripts/phase_h_url_check.py --hit http://localhost:8000` |
| Full Phase H script | `bash scripts/run_phase_h_verification.sh` |
| Manual checklist | [PHASE_H_MANUAL_CHECKLIST.md](PHASE_H_MANUAL_CHECKLIST.md) |
| Execution log | [PHASE_H_EXECUTION_LOG.md](PHASE_H_EXECUTION_LOG.md) |

---

## 3. Lint and CI

| Lint | Purpose |
|------|--------|
| lint_tenant_settings --check-get-solo-only | No get_solo in tenant paths; tenant behavior via runtime only |
| lint_siteconfig_legacy_imports | Block legacy siteconfig imports in app code |
| lint_csrf_exempt_usage | csrf_exempt allowlist; public_endpoint_audit |
| lint_allow_any_usage | AllowAny allowlist; public_endpoint_audit |
| lint_raw_sql_usage | raw_sql_audit allowlist; no ad-hoc raw SQL in app code |
| lint_broad_except --strict | broad_except allowlist; typed exceptions where required |
| lint_secret_exposure | No provider secrets in client/tracked config |
| lint_gilead_residue | No Gilead in live/default-facing surfaces |
| pre_deploy_gate.sh | Runs all above (and tests) for merge/release |

---

## 4. Key ledgers and inventories

| Doc | Purpose |
|-----|--------|
| [public_endpoint_audit.md](public_endpoint_audit.md) | Every csrf_exempt and AllowAny endpoint; classification; auth, rate limit, audit |
| [raw_sql_audit.md](raw_sql_audit.md) | Raw SQL usage; allowlist; repository/service abstraction |
| [feature_control_ledger.md](feature_control_ledger.md) | Feature toggles; owner/expiry; capability registry |
| [package_engine_ledger.md](package_engine_ledger.md) | Package engine; validate/preview/apply/rollback; partial failure |
| [LEGACY_PATH_INVENTORY.md](LEGACY_PATH_INVENTORY.md) | Legacy paths; REMOVED / REDIRECT / CANDIDATE / KEEP |
| [site_settings_usage_inventory.md](site_settings_usage_inventory.md) | SiteSettings fields and usage; domain ownership |
| [domain_ownership.md](domain_ownership.md) | Ownership migration; bounded contexts |
| [ENDPOINT_AND_CONTRACT_VERIFICATION.md](ENDPOINT_AND_CONTRACT_VERIFICATION.md) | Endpoint classification + contract tests |

---

## 5. Security review (§12.2)

Before release: run and log in [SECURITY_REVIEW_LOG.md](SECURITY_REVIEW_LOG.md).

- Public endpoints: ledger complete; no new unlisted; signature/replay where required
- AI gateway: no secrets in context; permission enforced; staff-only gated
- Secrets: lint_secret_exposure pass

Use [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) Security section.

---

*SOT ref: §12, §11 Phase H; PATH_TO_100 Phase H / verification.*
