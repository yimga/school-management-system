# Phase 7 — Runtime-first enforcement — mandatory audit

**Authority:** Cursor **Phase 7** — tenant behavior on **touched** flows resolves through `platform_runtime` (precedence, `build_tenant_runtime`, `get_effective_*` helpers), not ad-hoc singletons or duplicate fallback chains.

**Canonical SOT:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (runtime / precedence anchors). **Narrative:** [runtime_precedence.md](../runtime_precedence.md), [runtime_resolvers_and_contracts.md](../runtime_resolvers_and_contracts.md), [PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md](../PHASE_6_RUNTIME_FIRST_ENFORCEMENT.md) (execution map). **Checklist:** [phase_07_runtime_first.md](../phase_checklists/phase_07_runtime_first.md).

**Mechanical gate:** `python scripts/verify_cursor_phase7_runtime_first.py`

**Updated:** 2026-03-24 — **CLOSED** for in-repo precedence, resolver registry, inspector, and contract test bundle.

**Historical scope:** This file is a **Phase 7 audit trail** for runtime-first work. It is **not** the source of truth for current one-shot bundle **run order** in `python scripts/verify_phases_3_11_gates.py` (use `main()` in that script; maintainer table: [PHASES_3_11_GATE_VERIFICATION.md](../PHASES_3_11_GATE_VERIFICATION.md) appendix from `docs/gate_map_appendix_config.json`).

---

## 1. Goal

| Requirement | Result | Evidence |
|-------------|--------|----------|
| Runtime authoritative on tenant-facing resolution | **PASS** | `build_tenant_runtime` / `request.tenant_runtime`; helpers in `apps/platform_runtime/helpers.py` |
| Precedence explicit and testable | **PASS** | `precedence.py` + `describe_precedence_chain()` + `test_precedence.py` |
| Fallback outside runtime removed from **touched** tenant paths | **PASS** | `lint_tenant_settings.py` (bundled in Phase 6 gate) + inventory |

---

## 2. Precedence (seven layers)

Order (low → high authority for merges): **platform default → registry default → blueprint default → policy bundle → entitlement gate → tenant override → sandbox/preview override.**

| Layer | Code | Tests |
|-------|------|-------|
| Chain definition | `apps/platform_runtime/precedence.py` — `PRECEDENCE_ORDER`, `merge_by_precedence`, aliases | `test_precedence.py`, `test_phase7_runtime_gate.py` |
| Documentation | `docs/runtime_precedence.md` | Gate script asserts key phrases |
| Inspector visibility | `inspect_runtime()` — `precedence_chain`, `feature_flags_merge_order` | `RuntimeInspectorPrecedenceTests` in `test_runtime_contract.py` |

---

## 3. Resolver map (required facets)

Registry: `apps/platform_runtime/resolver_registry.py` — `RESOLVER_ENTRY_POINTS`.

| Resolver | Primary implementation | Notes |
|----------|------------------------|-------|
| RuntimeResolver | `runtime_resolver.build_tenant_runtime` | Aggregates 13-step compilation |
| BrandingResolver | `runtime_resolver._step7_branding` | Effective branding / theme path |
| BlueprintResolver | `runtime_resolver._step4_blueprint` | Applied pack / blueprint context |
| PolicyResolver | `apps.policies.resolver.get_effective_policy` | Policy bundle merge |
| WorkflowResolver | `apps.siteconfig.workflow_resolver.for_action` | Workflow pack resolution |
| DashboardResolver | `apps.siteconfig.dashboard_resolver.for_role` | Dashboard pack resolution |
| EntitlementResolver | `runtime_resolver._step6_flags_entitlements` | Flags + plan gates |
| IntegrationResolver | `runtime_resolver._step10_integrations_marketplace` | Integrations / marketplace slice |
| LocalizationResolver | `runtime_resolver._step3_registry_context` | Registry / locale context |

**Also registered:** `SchemaResolver`, `LayoutResolver`, `EntitlementRegistrySnapshot` (bounded context or snapshot helpers).

**Contract:** `ResolverRegistryContractTests` — dotted paths importable; `test_phase7_runtime_gate.py` — required names present.

---

## 4. Touched behavior paths (inspection summary)

| Area | Resolution path | Fallback leakage control |
|------|-----------------|---------------------------|
| Site settings / branding | `get_effective_site_settings`, runtime payload, PGB | Phase 6 lints; no tenant `get_solo()` |
| Feature flags | `get_effective_flags*`, `_step6`, policy features merge | Precedence merge in `merge_feature_flags_by_runtime_precedence` |
| Policy | `get_effective_policy` → runtime `policy_typed` | Policies app resolver |
| Blueprint | `_step4_blueprint`, school `tenant_blueprint` | Contract test `test_step4_blueprint_*` |
| Workflow / dashboard | Steps 8–9 + siteconfig resolvers | `TenantRuntime` sections populated |
| Localization / registry | `_step3_registry_context` | `RegistryContext` on runtime |
| Integrations | Step 10 | `IntegrationGovernanceTests` |

**Detail:** `docs/site_settings_usage_inventory.md` (Phase 6) + `helpers.py` docstrings.

---

## 5. Runtime inspector

| Aspect | Implementation |
|--------|----------------|
| Core API | `apps/platform_runtime/runtime_inspector.py` — `inspect_runtime`, `get_runtime_inspection`, `get_runtime_inspection_for_school`, `get_feature_toggle_inspection`, `entitlements_why` |
| Super UI | `super:runtime_inspector` — `apps/schools/super_views_runtime_ops.py`, template `templates/schools/super_runtime_inspector.html` |
| Control / Studio links | `control_outcome_center.py`, `studio_os/views.py` (Control rail), `deep_links.py`, `control_plane_nav.py` |
| Payload | `precedence_chain`, `compilation_trace`, entitlement / blueprint / marketplace registry snapshots |

---

## 6. Acceptance

| Criterion | Result | How verified |
|-----------|--------|--------------|
| Runtime authoritative on touched flows | **PASS** | Runtime contract tests + helper tests + middleware attachment pattern |
| Precedence explicit, testable, inspectable | **PASS** | `precedence.py` + inspector payload + `test_precedence.py` |
| Fallback outside runtime removed from touched paths | **PASS** | Phase 6 tenant lints (run from granular or standard Phase 6 bundle) |
| Contract tests | **PASS** | `test_runtime_contract.py` (compilation order, resolver registry, inspector precedence) |

---

## 7. Mechanical re-audit

```bash
python scripts/verify_cursor_phase7_runtime_first.py
python scripts/verify_cursor_phase7_granular.py
```

Scoped pytest (also invoked by the first script):

```bash
python -m pytest apps/platform_runtime/tests/test_phase7_runtime_gate.py \
  apps/platform_runtime/tests/test_precedence.py \
  apps/platform_runtime/tests/test_runtime_contract.py -q
```

**Do not proceed to Phase 8** until the gate above passes.

---

## 8. Granular inventory (line-by-line scope)

### 8.1 Core services / modules (inspected)

| Module | Role |
|--------|------|
| `apps/platform_runtime/middleware.py` | Attaches `request.tenant_runtime` via `build_tenant_runtime` |
| `apps/platform_runtime/runtime_resolver.py` | 13-step compilation; blueprint, policy, flags, branding, workflow, dashboard, integrations |
| `apps/platform_runtime/helpers.py` | `get_effective_site_settings`, `get_platform_site_settings_record`, flags, cache invalidation |
| `apps/platform_runtime/precedence.py` | Seven-layer order, `merge_by_precedence`, feature-flag merge helper |
| `apps/platform_runtime/resolver_registry.py` | Declared resolver entry points (importability tested) |
| `apps/platform_runtime/runtime_inspector.py` | `inspect_runtime`, `get_runtime_inspection*`, precedence in payload |
| `apps/policies/resolver.py` | `get_effective_policy` (PolicyResolver) |
| `apps/siteconfig/workflow_resolver.py` | WorkflowResolver |
| `apps/siteconfig/dashboard_resolver.py` | DashboardResolver |
| `apps/siteconfig/context_processors.py` | Uses `get_effective_site_settings(request=)` |

### 8.2 Representative touched consumer paths (runtime-first reads)

| Area | Files (sample) |
|------|----------------|
| Portal / accounts | `portal/views_*.py`, `accounts/decorators.py`, `accounts/forms.py` |
| Finance / payroll | `finance/views*.py`, `finance/admin.py`, `payroll/services.py` |
| Reports | `reports/views.py` |
| Siteconfig UI | `siteconfig/views.py` (multiple `get_effective_site_settings`) |
| Studio OS | `studio_os/views.py` — **persist** paths use `get_platform_site_settings_record` / `apply_theme_experience_state`, not raw `SiteSettings.objects` in tenant tree |
| Super control plane | `schools/super_views_runtime_ops.py` — `super_runtime_truth_hub` uses `get_platform_site_settings_record(create=False)` for the singleton summary |

### 8.3 Inspector routes and templates

| Name | Route | Template / partial |
|------|-------|-------------------|
| `super:runtime_inspector` | `super/runtime-inspector/` | `templates/schools/super_runtime_inspector.html` |
| `super:runtime_truth_hub` | `super/runtime-truth-hub/` | `templates/schools/super_runtime_truth_hub.html` |
| Links | — | `control_outcome_center.py`, `studio_os` Control partials, `super_education_systems.html`, `super_policy_diff.html` |

`super_runtime_truth_hub` loads the platform singleton via **`get_platform_site_settings_record(create=False)`** (no raw `SiteSettings.objects` in the view).

### 8.4 Test coverage (contract + isolation)

| Module | Covers |
|--------|--------|
| `test_phase7_runtime_gate.py` | Precedence tuple + required resolver names |
| `test_precedence.py` | Aliases, `merge_by_precedence` |
| `test_runtime_contract.py` | `TenantRuntime` shape, 13-step trace, resolver registry, inspector precedence, helpers |
| `test_tenant_isolation_and_identity.py` | `request.tenant_runtime` middleware attachment |
| `lint_tenant_settings.py` + `TENANT_APPS` | **Includes `apps/studio_os`** — no `get_solo` / raw `SiteSettings.objects` / forbidden `school.settings` on tenant trees |
| `schools/tests/test_super_views_runtime_ops.py` | `SuperRuntimeTruthHubContractTests` — truth hub source must use `get_platform_site_settings_record`, not `SiteSettings.objects` |

---

## 9. Granular verification command

```bash
python scripts/verify_cursor_phase7_granular.py
```

Runs: `verify_cursor_phase7_runtime_first.py`, **`lint_sitesettings_orm_singleton`** (no `SiteSettings.objects` outside `models.py` + `helpers.py`), all three `lint_tenant_settings` modes (with Studio OS in tenant tree), `test_tenant_isolation_and_identity.py`, and `schools/tests/test_super_views_runtime_ops.py` (truth hub contract). **Required** before claiming Phase 7 satisfies execution-law “re-audited + validated,” not only `verify_cursor_phase7_runtime_first.py`.
