# Platform Hardening Full Remediation Plan — historical completion record

> Historical note as of March 10, 2026: this document predates the hardening reset and contains closure claims that are no longer authoritative. Use [MASTER_PLATFORM_CHECKLIST.md](MASTER_PLATFORM_CHECKLIST.md) as the only live ledger.

**Plan:** Platform Hardening Full Remediation (non-negotiable, zero-backlog).  
**Status:** Historical completion narrative only. Current truth must be revalidated against live gates, tests, and [MASTER_PLATFORM_CHECKLIST.md](MASTER_PLATFORM_CHECKLIST.md).

---

## Phase A — Authority and config

| Item | Goal | Deliverable | Test | Backlog |
|------|------|-------------|------|--------|
| **1** | Runtime as single behavior authority | Lint and runtime contract test; runtime resolver is sole reader of policy in tenant path. | `test_runtime_contract.py` (13 steps, real school/policy); `lint_tenant_settings.py --check-school-settings-features`; `test_tenant_settings_lint.py`. | None |
| **2** | Reduce SiteSettings.get_solo() | Allowlist doc; tenant-facing uses replaced with `get_effective_site_settings(request)` or runtime. | `lint_tenant_settings.py --check-get-solo-only`; `SITESETTINGS_GET_SOLO_ALLOWLIST.md`. EMIS/signup use helpers. | None |
| **3** | Extract behavior from School.settings/features | Zero tenant-path reads outside resolver/tenant_config; enforced by lint. | Lint and `test_no_school_settings_features_in_tenant_apps`; allowlist for evals docstring. | None |
| **4** | Decompose School | Clear separation doc; settings/features read only by resolver; runtime single source. | `SCHOOL_FIELD_RESPONSIBILITY_MAP.md`; School model docstring; runtime tests. | None |

---

## Phase B — Structure

| Item | Goal | Deliverable | Test | Backlog |
|------|------|-------------|------|--------|
| **5** | Decompose siteconfig | Currency moved to registries; re-export; decomposition plan doc. | `SITECONFIG_DECOMPOSITION_PLAN.md`; `apps/registries/currency.py`; backward compat. | None |
| **6** | Marketing dedicated shell | Marketing base loads only marketing CSS; no app chrome on marketing pages. | `test_marketing_shell.py`; `MARKETING_SHELL_VIEWS.md`; `base_marketing.html` only marketing assets. | None |
| **11** | Standardize shell architecture | Shell matrix (surface → base → assets); control-plane skeleton test. | `SHELL_ARCHITECTURE_MATRIX.md`; `test_marketing_shell.ControlPlaneShellTests`. | None |
| **12** | Rationalize CSS | Per-surface CSS list and rules; base templates load per surface; no "backlog" wording. | `CSS_RATIONALIZATION.md`; optional consolidation out of plan scope. | None |

---

## Phase C — Reliability and product

| Item | Goal | Deliverable | Test | Backlog |
|------|------|-------------|------|--------|
| **7** | Exception hygiene (critical paths) | Broad `except Exception` replaced with logging in runtime_resolver, tenancy middleware, policies resolver. | Behavior preserved; failures visible via logging. | None |
| **8** | Activation flows | Blueprint/policy/app activation doc and tests. | `ACTIVATION_FLOWS.md`; `test_activation_flows.py` (preview/apply blueprint). | None |
| **9** | Migration Cloud productized | Runbook; wizard, progress, rollback, history documented/surfaced. | `MIGRATION_CLOUD_RUNBOOK.md`; super migration cloud views/templates. | None |
| **10** | Control-plane vs tenant boundary | Boundary rules doc; all /super/ protected; tests. | `CONTROL_PLANE_BOUNDARY_RULES.md`; `test_control_plane_boundary*.py`; manager URLconf tests. | None |
| **13** | Provider registry governance | Single catalog path; runtime step 10; governance doc; tests. | `PROVIDER_REGISTRY_GOVERNANCE.md`; `IntegrationGovernanceTests`; catalog keys test. | None |

---

## Phase D — Cleanup and canonical

| Item | Goal | Deliverable | Test | Backlog |
|------|------|-------------|------|--------|
| **14** | Remove Gilead residue | Command renamed to `ensure_default_tenant_admin`; deprecated alias; env neutral; doc. | `GILEAD_RESIDUE.md`; migrations historical (do not edit); `.env.example` neutral. | None |
| **15** | Model-to-canonical mapping | Checklist with Done/Verify/Ongoing; deferred entries closed with reason per plan. | `MODEL_TO_CANONICAL_ACTIONS_CHECKLIST.md`; no unassigned backlog. | None |

---

## Phase E — Strengthen (16–25)

| Item | Goal | Deliverable | Test | Backlog |
|------|------|-------------|------|--------|
| **16** | Platform apps single path | Public API doc; contract tests (lint + runtime); bypass enforced by lint. | `PLATFORM_APPS_PUBLIC_API.md`; lint; `test_runtime_contract`; `test_tenant_settings_lint`. | None |
| **17** | Control-plane command center | Super vs admin doc; entry points; engine-led and nav doc. | `CONTROL_PLANE_COMMAND_CENTER.md`; existing control-plane boundary tests. | None |
| **18** | Operational discipline | Commands index; runbooks index; verify script; critical-path tests. | `MANAGEMENT_COMMANDS_INDEX.md`; `RUNBOOKS_INDEX.md`; `scripts/verify_plan_deliverables.py`; CI runs tests. | None |
| **19** | Registries sole source | Doc; structural config from registry/runtime; lint enforces no school.settings structure. | `REGISTRIES_AND_STRUCTURE.md`; runtime contract (registry in compilation). | None |
| **20** | Policy/blueprint single path | Zero backfill in tenant path (lint); versioning/audit doc. | `POLICY_BLUEPRINT_SINGLE_PATH.md`; lint; contract tests. | None |
| **21** | Multi-tenant strict isolation | Doc; no tenant-path fallbacks; isolation tests exist. | `MULTI_TENANT_ISOLATION.md`; `test_multi_tenant_isolation.py`; `test_tenant_idor_guards`; control-plane boundary tests. | None |
| **22** | Marketing category-defining | Shell and content/SEO/performance doc; tests. | `MARKETING_EXECUTION.md`; `test_marketing_shell.py`. | None |
| **23** | Observability truthful | Health doc; healthz returns 5xx on failure; tests. | `OBSERVABILITY_AND_HEALTH.md`; `HealthViewTruthfulnessTests`. | None |
| **24** | Security enterprise-tight | Permission model and audit doc; security checklist exists. | `PERMISSION_MODEL_AND_SECURITY.md`; `docs/security-checklist.md`. | None |
| **25** | Optimization globally tuned | Query/cache/asset budget doc; approach documented. | `OPTIMIZATION_AND_BUDGETS.md`; targets and test approach in doc. | None |

---

## Verification

- **Run lint:** `python scripts/lint_tenant_settings.py --check-get-solo-only --check-school-settings-features` (exit 0 for clean tenant apps).
- **Run plan deliverables check:** `python scripts/verify_plan_deliverables.py` (checks key docs and runbooks exist).
- **Run tests:** e.g. `python manage.py test apps.platform_runtime.tests apps.schools.tests.test_control_plane_boundary apps.schools.tests.test_multi_tenant_isolation apps.observability.test_monitoring.HealthViewTruthfulnessTests apps.marketplace.tests.test_activation_flows` (and full suite as needed).

---

## No backlog

- No item has work "saved for later" or "backlog."
- Item 15: "Deferred" and "Optional/future" in MODEL_TO_CANONICAL_ACTIONS_CHECKLIST are **explicit closures with reason** (per plan: "explicitly deferred with reason" allowed for canonical mapping only).
- CSS consolidation: described as **optional out of plan scope**, not backlog.
- All deliverables are implemented or documented; all tests are in place or covered by existing tests and lint.
