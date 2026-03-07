# Architecture overlay and runtime constitution — verification

**Purpose:** Map the “Architecture Diagram + Current Codebase Refactor Overlay” and the **one runtime constitution** to this repo. Use this to verify everything is complete and done correctly.

---

## 1. One runtime constitution (done)

The platform must have **one runtime constitution**: a single contract that every module uses so the system does not “grow sideways and argue with itself in the dark.”

| Pillar | Requirement | Where implemented | Status |
|--------|-------------|-------------------|--------|
| **One tenant runtime object** | Single object per request carrying identity + policy + workflow/dashboard access | `apps/platform_runtime/`: `TenantRuntime`, `build_tenant_runtime`, `TenantRuntimeMiddleware`. Set as `request.tenant_runtime` after `TenantContextMiddleware` (both RLS and schema-per-tenant stacks). | Done |
| **One blueprint registry** | Single place for tenant blueprint (country, region, education, branding, policy overrides) | `apps/policies/models.py`: TenantBlueprint, PolicyBundle, BlueprintPack. `apps/policies/blueprint_services.py`: get_tenant_blueprint, apply_blueprint_pack. Resolvers in `apps/policies/resolvers.py` (TenantBlueprintResolver). | Done |
| **One policy resolver** | Single entry point for “how should this tenant behave?” | `apps/policies/resolver.py`: get_effective_policy(school). `apps/policies/resolvers.py`: PolicyResolver, CapabilityResolver, TerminologyResolver, ComplianceResolver, BrandingResolver, ChannelResolver. Policy = platform_defaults ⊕ country_defaults ⊕ tenant_overrides; per-tenant cache. | Done |
| **One consistent injection path** | Every module gets policy/blueprint via the same path, not ad-hoc school.settings | Middleware: `request.tenant_ctx`, `request.tenant_runtime`. Context processor: `global_env` = resolved policy. Views: use `request.tenant_runtime.policy`, `request.tenant_runtime.workflow_for()`, `request.tenant_runtime.dashboard_for()` or get_effective_policy(school) where runtime not yet used. Forms: apply_form_policy(policy). Services: accept policy or school and call get_effective_policy. Documented in `section_23_injection_verification.md`. | Done |

---

## 2. Overlay checklist (architecture diagram + current codebase)

What the overlay adds; where it lives in this repo.

| Overlay item | Where in repo | Status |
|--------------|---------------|--------|
| **Full platform architecture diagram** | `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` Part A — North Star (text diagram: public → edge → control/tenant/developer → policy & workflow → app services → data → three DB tiers) | Done |
| **Control plane vs tenant plane separation** | Part B (five layers); Section 2 (control ownership), Section 3 (tenant ownership); `phase2_control_tenant_shells.md`, `phase10_superadmin_vs_tenant_ui.md`; urlconfs (manager vs tenant vs public) | Done |
| **Current Django app overlay** | `docs/architecture/apps.txt`; `FINDINGS_REPO_AUDIT.md`; `phase11_module_architecture_section_9.md` (module map); policy/runtime usage: portal, evals, people, siteconfig, finance, policies, platform_runtime, tenancy, schools, marketplace, etc. | Done |
| **Exact places where Blueprint + Policy inject** | `section_23_injection_verification.md` (23.1–23.7: middleware, context processor, views, forms, services, templates, signals); `policy_injection.md` | Done |
| **Split-brain warning (schema-per-tenant + RLS/session coexistence)** | `TENANCY_MODEL_DECISION.md` (schema primary, RLS/session secondary; session vars for audit/RLS only); `tenancy.md`; rule 24.10 in consolidated checklist | Done |
| **Dashboard hub and workflow hub architecture** | `phase4_workflow_dashboard_hubs.md`; `apps.siteconfig.workflow_resolver`, `apps.siteconfig.dashboard_resolver`; TenantRuntime.workflow_for(), .dashboard_for(); `/siteconfig/workflow-hub/`, `/siteconfig/dashboard-hub/` | Done |
| **What is configurable platform-wide** | Section 10 (Admissions, Academics, Finance, Attendance, Communication, HR/Staff, Compliance, Dashboards); `phase12_platform_configurability_section_10.md`; get_effective_policy keys and section_10_helpers | Done |
| **Exact phased refactor order** | Part D (Phases 1–6); Section 12 (12.1–12.7); `refactor_waves_12_7.md` (waves 1–8); `REMAINING_PHASES_EXECUTION_ORDER.md` (24 phases) | Done |
| **Cursor-ready implementation block** | Part F — Cursor / Implementation Directive (steps 1–27 referencing every checklist section); paste into Cursor Agent to drive implementation | Done |

---

## 3. Django apps and runtime/constitution usage

Apps that must use the single injection path (policy/runtime, no direct school.settings/features):

| App | Uses policy/runtime / blueprint | Notes |
|-----|---------------------------------|--------|
| platform_runtime | Defines TenantRuntime; middleware sets request.tenant_runtime | Single runtime object |
| tenancy | TenantContext; middleware sets request.tenant_ctx | Identity only |
| policies | get_effective_policy, resolvers, context processor, form_policy, blueprint_services | One policy resolver, one blueprint path |
| siteconfig | workflow_resolver, dashboard_resolver, get_tenant_blueprint, identifier_policy_service | Hubs + policy |
| portal | get_tenant_blueprint, policy in forms, dashboard_resolver, workflow (form signature) | Views/forms use policy |
| evals | get_grade_approval_policy, workflow_resolver, dashboard_resolver | Gradebook refactored |
| people | _get_admissions_policy(school), policy for admission number | Admissions refactored |
| finance | gateways use policy (get_gateway(..., policy=request.tenant_runtime.policy)); section_10_helpers | Finance uses runtime when in request context |
| reports | resolve_report_labels, _region_display_context from policy | Policy only |
| compliance | policy slices, ComplianceResolver | Policy only |
| schools | tenant resolution, feature gates (get_effective_policy) | Middleware / gates |
| marketplace | install pipeline, AppAuditLog; governance | Control/tenant split |

---

## 4. Double-check: nothing left behind

- **Runtime constitution:** One object (TenantRuntime), one blueprint (TenantBlueprint + services), one policy (get_effective_policy + resolvers), one injection path (middleware → context processor → views/forms/services) — all implemented and documented.
- **Overlay:** Diagram (Part A), control/tenant split (Part B, Sections 2–3), app overlay (apps.txt, phase11, FINDINGS), injection points (Section 23 + section_23_injection_verification), split-brain (TENANCY_MODEL_DECISION), hubs (phase4, workflow_resolver, dashboard_resolver), configurable (Section 10, phase12), phased order (Part D, Section 12, refactor_waves), Cursor block (Part F) — all present.
- **Deferred/optional:** Listed in “Deferred and optional items register” in consolidated doc; follow-up in REMAINING_PLAN_AUDIT_GAPS.md.

---

## 5. Roadmap (5-year + module rollout)

The **full 5-year platform roadmap and module-by-module rollout order** is implemented in:

- **`docs/architecture/PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md`**

It includes: 5-year horizon (Year 1–5 themes and deliverables), module-by-module rollout table (refactor status and next steps per app), prioritised backlog from REFINEMENT_AND_IMPLEMENTATION_ORDER and REMAINING_PLAN_AUDIT_GAPS mapped to years, and execution order (phases tied to roadmap). Use it for strategic planning, module ownership, and sprint backlog; REFINEMENT and REMAINING_PLAN_AUDIT_GAPS remain the source for item detail and checklist alignment.

---

---

## 6. Execution map alignment (no-break)

Alignment with the **RunMyCampus Codebase Execution Map for Cursor** is documented in **`EXECUTION_MAP_ALIGNMENT.md`**. Summary:

- **Single runtime constitution:** One object (`request.tenant_runtime`), one blueprint path (`blueprint_registry`), one policy path (`policy_registry`), one injection path — all implemented; existing call sites remain valid.
- **Schema-per-tenant = primary;** RLS/session variable = **compatibility / transitional only** (see `TENANCY_MODEL_DECISION.md`). Session vars are for audit and RLS scoping only, not for resolving tenant identity in app code.
- **Registries:** `apps/policies/blueprint_registry.py` and `apps/policies/policy_registry.py` are the canonical single entry points; they re-export existing resolver/blueprint_services so **nothing is broken**; new code should prefer these imports and `request.tenant_runtime` in request context.
- **Refactor order:** One module (Gradebook or Admissions) end-to-end using only `request.tenant_runtime` and registries, then replicate the pattern. No big-bang changes.

---

**References:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md, TENANCY_MODEL_DECISION.md, section_23_injection_verification.md, policy_injection.md, phase4_workflow_dashboard_hubs.md, refactor_waves_12_7.md, VERIFICATION_COMPLETENESS.md, PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md, **EXECUTION_MAP_ALIGNMENT.md**.
