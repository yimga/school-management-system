# Execution map alignment — RunMyCampus Codebase Execution Map for Cursor

**Purpose:** Align this codebase with the RunMyCampus Codebase Execution Map for Cursor (single runtime constitution, Tenant Blueprint + Policy Registry injection, schema-per-tenant vs RLS formalization, refactor order) **without breaking existing behavior.**

---

## 1. Single runtime constitution

**Execution map conclusion:** *"You already have many of the raw parts of a platform giant, but they need a single runtime constitution."*

| Requirement | Where it lives | Status |
|-------------|----------------|--------|
| One tenant runtime object per request | `apps/platform_runtime/`: `TenantRuntime`, `build_tenant_runtime`, `TenantRuntimeMiddleware`. Set as **`request.tenant_runtime`** after `TenantContextMiddleware`. | Done |
| One blueprint path | `apps/policies/models.py` (TenantBlueprint, BlueprintPack, PolicyBundle), `apps/policies/blueprint_services.py`, `apps/policies/blueprint_registry.py` (single import for blueprint). Resolver: `get_tenant_blueprint(school)` / registry. | Done |
| One policy path | `apps/policies/resolver.py`: `get_effective_policy(school)`. `apps/policies/resolvers.py`: PolicyResolver, CapabilityResolver, etc. `apps/policies/policy_registry.py` (single import for policy). | Done |
| One injection path | Middleware: `request.tenant_ctx`, `request.tenant_runtime`. Views: use **`request.tenant_runtime.policy`**, `request.tenant_runtime.workflow_for()`, `request.tenant_runtime.dashboard_for()` or `get_effective_policy(school)` where request context not available. | Done |

**Rule:** No direct reads of `School.settings`, `School.features`, plan/addons, region config, feature toggles, workflow assignments, dashboard preferences, or site settings for **tenant behavior**. All such behavior is decided via:

- **In request context:** `request.tenant_runtime.policy` (and `.workflow_for()`, `.dashboard_for()`).
- **Outside request context:** `get_effective_policy(school)` (or `policy_registry.get_effective_policy(school)`).

Existing call sites that use `get_effective_policy(school)` remain valid; new code should prefer `request.tenant_runtime.policy` when the request is available.

---

## 2. Too many places deciding tenant behavior → consolidation

**Execution map:** *"The biggest thing to fix is not missing features. It is too many places deciding tenant behavior at once."*

| Current source | Intended role | Migration |
|----------------|---------------|-----------|
| School.settings | Legacy / overrides | Policy = platform ⊕ country ⊕ tenant; get_effective_policy merges tenant overrides. No new direct reads. |
| School.features | Legacy / overrides | Same; capability checks via get_effective_policy(school, capability=...) or request.tenant_runtime.policy. |
| plan / addons | Plan-level defaults | Policy and blueprint can be driven by plan; resolve via policy registry, not ad-hoc plan checks in app code. |
| region config | Country/region defaults | get_effective_policy merges country/region; use policy slice (e.g. terminology, finance). |
| feature toggles | Feature gates | Use get_effective_policy(school, capability=code) or is_feature_enabled(school, code) (which uses policy). |
| workflow assignments | Workflow definition | request.tenant_runtime.workflow_for(action_slug) or workflow_resolver.for_action(school, action_slug). |
| dashboard preferences | Dashboard composition | request.tenant_runtime.dashboard_for(role, user=...) or dashboard_resolver.for_role(school, role, ...). |
| site settings | Global + tenant overrides | SiteSettings for global; tenant-specific behavior from policy/blueprint only. |

**Redundancy and risk:** The execution map calls out these as "redundancy and risk hotspots." Consolidation is done by:

1. **Policy Registry** — single entry: `get_effective_policy(school)` / `policy_registry.get_effective_policy(school)`.
2. **Blueprint Registry** — single entry: TenantBlueprint + BlueprintPack + `get_tenant_blueprint(school)` / `blueprint_registry`.
3. **Runtime** — `request.tenant_runtime` carries resolved policy and delegates workflow/dashboard to existing resolvers.

No removal of existing call sites until a module is refactored end-to-end (see refactor order below).

---

## 3. Schema-per-tenant vs RLS/session — formalization

**Execution map:** *"Your codebase currently supports both schema-per-tenant and session-variable/RLS-style tenant behavior. That can be fine, but only if you formalize it."*

| Model | Role | Where documented |
|-------|------|------------------|
| **Schema-per-tenant** | **Primary** isolation model. Each tenant has a dedicated PostgreSQL schema; `request.tenant` and `request.school` from host resolution; DB connection scoped to schema. | `docs/architecture/TENANCY_MODEL_DECISION.md`; `tenancy.md`; rule 24.10 in consolidated checklist. |
| **RLS / session variable** | **Compatibility / transitional** only. Used when not using django-tenants; session vars (e.g. `app.current_school_id`) for **audit and RLS scoping only**, not for resolving "which tenant am I?" in application code. | Same; application contract: tenant from host → request.tenant_ctx / request.tenant_runtime. |

**Haunted-house-bugs warning:** Do not mix both models as competing sources of tenant identity in the same request path. One mode per deployment (TENANCY_MODE); session variables are for audit/RLS only. See `TENANCY_MODEL_DECISION.md`.

---

## 4. Execution map → codebase map (Cursor-ready)

| Execution map artifact | Implementation in repo |
|------------------------|-------------------------|
| **blueprint_registry.py** | `apps/policies/blueprint_registry.py` — single entry for blueprint: `get_tenant_blueprint(school)`, `apply_blueprint_pack`, `preview_blueprint_pack`. Existing: `resolver.get_tenant_blueprint`, `blueprint_services`, `policies.registry.get_tenant_blueprint(request)`. |
| **policy_registry.py** | `apps/policies/policy_registry.py` — single entry for policy: `get_effective_policy(school)`, `invalidate_policy_cache`. Existing: `resolver.get_effective_policy`, `resolvers.PolicyResolver`. |
| **runtime_resolver.py** | `apps/platform_runtime/runtime_resolver.py` — `build_tenant_runtime(tenant_ctx, request=...)` → TenantRuntime. Used by TenantRuntimeMiddleware. |
| **Inject request.tenant_runtime** | `apps/platform_runtime/middleware.TenantRuntimeMiddleware` — runs after TenantContextMiddleware; sets `request.tenant_runtime = build_tenant_runtime(tenant_ctx, request=request)`. |
| **Refactor one module end-to-end** | Preferred: **Gradebook (evals)** or **Admissions (people)**. Pattern: views and services use `request.tenant_runtime.policy` and `request.tenant_runtime.workflow_for()` / `dashboard_for()` only; no direct School.settings/features or ad-hoc plan/region checks. That becomes the pattern for the rest of the platform. |

---

## 5. Full architecture diagram + refactor overlay

**Execution map:** *"The next strongest artifact is the full architecture diagram + current-codebase refactor overlay."*

| Item | Location |
|------|----------|
| North Star diagram | `RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md` Part A — public → edge → control/tenant/developer → policy & workflow → app services → data → three DB tiers. |
| Control vs tenant plane | Part B; Sections 2–3; `phase2_control_tenant_shells.md`, `phase10_superadmin_vs_tenant_ui.md`; manager vs tenant urlconfs. |
| Where Blueprint + Policy inject | `section_23_injection_verification.md` (middleware, context processor, views, forms, services, templates); `policy_injection.md`. |
| Split-brain (schema vs RLS) | `TENANCY_MODEL_DECISION.md`; overlay: `ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md`. |
| Exact refactor order | Part D (Phases 1–6); Section 12; `refactor_waves_12_7.md`; `REMAINING_PHASES_EXECUTION_ORDER.md`. |

---

## 6. Do not break existing behavior

- **Additive only:** New modules (`blueprint_registry`, `policy_registry`) are thin re-exports / single entry points. Existing imports from `resolver`, `resolvers`, `blueprint_services`, `registry` continue to work.
- **Existing call sites:** All current uses of `get_effective_policy(school)`, `get_tenant_blueprint(school)`, `request.tenant_runtime`, and `request.tenant_ctx` remain valid.
- **Refactor per module:** When a module (e.g. Gradebook or Admissions) is refactored to use only `request.tenant_runtime` and policy/blueprint registries, do it inside that module; do not force-change unrelated call sites elsewhere.
- **Tests:** Existing tests that rely on tenant context, policy, or blueprint resolution should continue to pass; new tests for registry entry points can be added without changing existing test behavior.

---

## 7. Recommended next coding move (from execution map)

1. **Use the registries** — New code: import from `apps.policies.blueprint_registry` and `apps.policies.policy_registry` for blueprint/policy; use `request.tenant_runtime` in views when available.
2. **Refactor one module** — Gradebook (evals) and Admissions (people) are refactored; full pattern and replication checklist: **`REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.md`**.
3. **Replicate the pattern** — Apply the same pattern to other modules (portal, finance, siteconfig, etc.) using that doc’s checklist.

---

## 8. Gradebook (evals) and Admissions (people) refactor — executed

The **evals** (Gradebook) and **people** (Admissions) apps were refactored to use the runtime constitution end-to-end. Full step-by-step pattern and replication checklist: **`REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.md`**.

### What was done

| Area | Change |
|------|--------|
| **Policy source in views** | When `request.tenant_runtime` is present, use `runtime.policy` for feature flags and grade_approval config. Else use `policy_registry.get_effective_policy(school)`. Fallback to SiteSettings only when no school (e.g. base domain). |
| **Workflow / dashboard** | When `request.tenant_runtime` and `runtime._school` are set, use `runtime.dashboard_for(role=..., user=...)` and `runtime.get_approval_workflow("syllabus_approval")`. Else call `dashboard_resolver.for_role(school, ...)` and `workflow_resolver.get_approval_workflow(school, ...)` as before. |
| **Helpers (approval.py)** | `get_grade_approval_policy(school=None, policy=None)` — when `policy` is provided (e.g. from `request.tenant_runtime.policy`), use it first; else resolve via `policy_registry.get_effective_policy(school)`. All helpers that take `school` now accept optional `policy=` and pass it through so callers can supply pre-resolved policy. |
| **Registries** | Evals imports policy from `apps.policies.policy_registry`; uses `apps.evals.runtime_helpers.get_policy_for_request(request)` in views for a single policy read path. People (Admissions) uses `policy_registry` in `StudentProfile._get_admissions_policy(school=None, policy=None)`. No direct School.settings/features. |
| **Admissions (people)** | `StudentProfile._get_admissions_policy(school=None, policy=None)` accepts optional `policy=` (e.g. from request.tenant_runtime.policy); uses `policy_registry.get_effective_policy(school)` when policy not provided. |
| **Notifications** | `_notify_grade_approvers` derives `school` from the approval request and passes it to `grade_approver_users(school=school)` so approver list is tenant-specific. |

### Pattern for other modules

1. **In views that have `request`:**  
   - Prefer `policy = getattr(request.tenant_runtime, "policy", None)` when `request.tenant_runtime` exists; else `policy = policy_registry.get_effective_policy(school)` when `school` is set.  
   - For workflow/dashboard: if `request.tenant_runtime` and `runtime._school`, use `runtime.workflow_for(...)` / `runtime.get_approval_workflow(...)` / `runtime.dashboard_for(...)`; else keep using the existing resolvers with `school`.

2. **In helpers/services:**  
   - Add optional `policy=None` (and keep `school=None`). When `policy` is provided, use it; otherwise resolve via `policy_registry.get_effective_policy(school)` (or SiteSettings when no school).  
   - Callers in request context can pass `policy=request.tenant_runtime.policy` to avoid re-resolving.

3. **No breaking changes:**  
   - All existing call sites that pass only `school` continue to work (policy is resolved inside the helper when `policy` is None).  
   - New call sites can pass `policy=` when they already have it.

**Full replication checklist and file-level details:** see **`REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.md`**.

---

## 9. Module refactor status (all done)

| Status | Module | Notes |
|--------|--------|-------|
| Done | **evals (Gradebook)** | runtime_helpers.get_policy_for_request; views use policy from runtime or policy_registry; approval.py accepts policy=; workflow/dashboard via runtime when available. |
| Done | **people (Admissions)** | _get_admissions_policy(school=None, policy=None) uses policy_registry; models/tasks pass school. |
| Done | **portal** | runtime_helpers.get_policy_for_request; views and views_onboarding, views_kb, views_support use get_policy_for_request or policy_registry; no direct resolver. |
| Done | **siteconfig** | context_processors, brand_registry, identifier_policy_service, education_dna, views use policy_registry. |
| Done | **finance** | gateways/registry uses policy_registry.get_effective_policy. |
| Done | **reports** | services use policy_registry.get_effective_policy. |
| Done | **compliance** | management commands use policy_registry.get_effective_policy. |
| Done | **accounts, schools, api, marketplace** | All imports of get_effective_policy / invalidate_policy_cache switched to policy_registry. |
| N/A | **communication** | No policy reads in app; no change. |

**Current status:** All targeted modules now use the single runtime constitution: policy_registry (and request.tenant_runtime.policy in request context via portal/evals runtime_helpers). No app imports get_effective_policy from apps.policies.resolver directly; internal policies app (resolver.py, resolvers.py, registry.py) and platform_runtime/runtime_resolver.py remain the implementation layer.

---

**References:** RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md, ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md, TENANCY_MODEL_DECISION.md, section_23_injection_verification.md, policy_injection.md, phase10_superadmin_vs_tenant_ui.md, **REFACTOR_PATTERN_GRADEBOOK_AND_ADMISSIONS.md**.
