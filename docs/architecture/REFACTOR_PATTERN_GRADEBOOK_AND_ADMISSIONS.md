# Refactor pattern: Gradebook (evals) and Admissions (people) — runtime constitution

**Purpose:** Document the end-to-end refactor pattern so other modules can replicate it. Aligns with the RunMyCampus Execution Map and `EXECUTION_MAP_ALIGNMENT.md`.

---

## 1. Rule (single runtime constitution)

- **In request context:** Use `request.tenant_runtime.policy` for behavior; use `request.tenant_runtime.workflow_for(action_slug)`, `request.tenant_runtime.get_approval_workflow(key)`, `request.tenant_runtime.dashboard_for(role, user=request.user)` for workflow/dashboard.
- **Outside request context (services, models, tasks):** Use `policy_registry.get_effective_policy(school)` (or `blueprint_registry.get_tenant_blueprint(school)` for blueprint). Never read `School.settings` or `School.features` directly for tenant behavior.
- **Optional helper:** In the app, add a small `get_policy_for_request(request)` that returns `request.tenant_runtime.policy` if set, else `policy_registry.get_effective_policy(request.school)`, so views use one call.

---

## 2. Gradebook (evals) — what was done

| Location | Before | After |
|----------|--------|--------|
| **Policy in views** | Mixed: sometimes `get_effective_policy(school)` only | Prefer `request.tenant_runtime.policy` when available; else `policy_registry.get_effective_policy(school)`. |
| **Dashboard** | `dashboard_for_role(school, role, user=request.user)` | When `request.tenant_runtime` and `runtime._school`: `runtime.dashboard_for(role=..., user=request.user)`; else fallback to `dashboard_for_role(school, ...)`. |
| **Workflow** | `workflow_get_approval(school, "syllabus_approval")` | When `request.tenant_runtime` and `runtime._school`: `runtime.get_approval_workflow("syllabus_approval")`; else fallback to `workflow_get_approval(school, ...)`. |
| **Grade approval policy** | `get_grade_approval_policy(school=school, policy=policy)` in approval.py | approval.py accepts `policy=` from caller; when in request context caller passes `request.tenant_runtime.policy`. Uses `policy_registry.get_effective_policy(school)` when school given and policy not. |
| **Imports** | — | No direct `apps.policies.resolver`; use `apps.policies.policy_registry.get_effective_policy`. |
| **Helper** | — | `apps.evals.runtime_helpers.get_policy_for_request(request)` and `get_grade_approval_policy_for_request(request)` for consistent view usage. |

**Files touched:** `apps/evals/views.py` (policy from runtime then policy_registry; dashboard/workflow via runtime when available), `apps/evals/approval.py` (policy_registry, accept policy from caller), `apps/evals/runtime_helpers.py` (new).

**Not changed:** grading.py, services.py, forms.py (no policy/school behavior reads). Models use approval.py / policy for grade approval only.

---

## 3. Admissions (people) — what was done

| Location | Before | After |
|----------|--------|--------|
| **people/models.py** | `_get_admissions_policy(school)` used `apps.policies.resolver.get_effective_policy(school)` | `_get_admissions_policy(school=None, policy=None)`: if `policy` dict provided (e.g. from request.tenant_runtime.policy), use it first; else `policy_registry.get_effective_policy(school)`. |
| **Call sites** | `generate_admission_number(..., school=school)`, `save()` / validation call `_get_admissions_policy(school)` | Unchanged; models/tasks have no request, so they pass school only. Views that create students and have request can later pass `policy=request.tenant_runtime.policy` into any API that accepts it. |

**Files touched:** `apps/people/models.py` (policy_registry import; optional `policy=` on `_get_admissions_policy`).

---

## 3b. Portal, siteconfig, finance, reports, compliance (done)

| Module | Change |
|--------|--------|
| **portal** | Added `runtime_helpers.get_policy_for_request(request)`. views.py, views_onboarding.py, views_kb.py, views_support.py use it or policy_registry; capability check in _cahier_enabled uses policy_registry.get_effective_policy(school, capability=...). **Workflow/dashboard:** parent dashboard view uses `request.tenant_runtime.dashboard_for(role=..., user=request.user)` when runtime and `runtime._school` are set, else `dashboard_for_role(school, ...)`. |
| **siteconfig** | context_processors, brand_registry, identifier_policy_service, education_dna, views.py import from policy_registry. **Workflow/dashboard:** views_workflow_api.dashboard_registry_api uses `runtime.dashboard_for(..., include_registry=True)` when runtime and `runtime._school` are set, else `dashboard_for_role(school, ...)`. |
| **finance** | gateways/registry.py uses policy_registry.get_effective_policy and accepts optional `policy=` (e.g. request.tenant_runtime.policy). Added `runtime_helpers.get_policy_for_request(request)`; views that call get_gateway or get_platform_fee should pass `policy=get_policy_for_request(request)`. |
| **reports** | services.py uses policy_registry.get_effective_policy. |
| **compliance** | compliance_auditor, export_compliance_evidence_pack use policy_registry.get_effective_policy. |
| **accounts, schools, api, marketplace** | All get_effective_policy / invalidate_policy_cache imports switched to policy_registry. |

---

## 4. Replication checklist for another module

1. **Policy in views**  
   - Replace direct `get_effective_policy(school)` with: get policy from `request.tenant_runtime.policy` if present, else `policy_registry.get_effective_policy(school)`.  
   - Option: add `get_policy_for_request(request)` in the app and use it in every view that needs policy.

2. **Workflow / dashboard in views**  
   - Where you call `workflow_resolver.for_action(school, slug)` or `get_approval_workflow(school, key)` or `dashboard_resolver.for_role(school, role, user=...)`:  
   - If `request.tenant_runtime` and `runtime._school` are set, use `runtime.workflow_for(slug)`, `runtime.get_approval_workflow(key)`, `runtime.dashboard_for(role, user=request.user)` instead.  
   - Keep a fallback to the resolver when runtime/school is missing (e.g. no tenant context).

3. **Services / models / tasks (no request)**  
   - Use `policy_registry.get_effective_policy(school)` (and optionally `blueprint_registry.get_tenant_blueprint(school)`).  
   - Prefer functions that accept an optional `policy=` dict so callers with request can pass `request.tenant_runtime.policy`.

4. **Imports**  
   - Use `from apps.policies.policy_registry import get_effective_policy` (no direct `apps.policies.resolver` for new code).  
   - Use `from apps.policies.blueprint_registry import get_tenant_blueprint` when blueprint is needed.

5. **No direct tenant behavior from**  
   - `School.settings`, `School.features`, plan/addons, region config, or feature toggles in app code. Resolve all via policy/blueprint or runtime.

6. **Tests**  
   - Keep existing tests passing. Add tests for the helper (e.g. `get_policy_for_request` with/without tenant_runtime) if added.

---

## 5. Do not break

- Existing call sites that use `get_effective_policy(school)` or `request.tenant_runtime` remain valid.  
- Fallbacks (e.g. `dashboard_for_role(school, ...)` when runtime has no school) stay so behavior is unchanged when tenant context is missing.  
- Refactor one module at a time; do not change unrelated apps in one go.

---

**Status:** Pattern replicated to portal, siteconfig, finance, reports, compliance, and all other apps that used policy; see **EXECUTION_MAP_ALIGNMENT.md** §9.

**References:** EXECUTION_MAP_ALIGNMENT.md, ARCHITECTURE_OVERLAY_AND_RUNTIME_CONSTITUTION.md, section_23_injection_verification.md, apps/evals/runtime_helpers.py, apps/evals/approval.py, apps/people/models.py (`_get_admissions_policy`).
