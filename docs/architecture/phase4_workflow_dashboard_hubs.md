# Phase 4 — Workflow and Dashboard Hubs (24.3, 24.4)

Scope for consolidating workflow and dashboard logic into platform services so feature apps do not duplicate behavior.

## Goals

- **24.3:** No duplicated workflow logic across apps. One workflow engine / hub; apps register steps and use a single resolver.
- **24.4:** No duplicated dashboard composition logic across roles. One dashboard hub; roles get assigned widgets/sections from a central definition.

## Hub APIs (implemented)

- **Workflow:** `apps.siteconfig.workflow_resolver`
  - `for_action(school, action_slug)` — returns workflow definition (approval, form_signature, or automation TenantWorkflow).
  - `get_approval_workflow(school, workflow_key)` — returns approval_roles, approver_ids for grade_approval / syllabus_approval.
  - Use these instead of calling get_effective_approvers / SiteSettings directly in new code; migrate existing callers over time.

- **Dashboard:** `apps.siteconfig.dashboard_resolver`
  - `for_role(school, role, user=None, preference=None, page=None, include_registry=False)` — returns widget_keys and optionally full registry.
  - Wraps resolve_dashboard_widgets and get_tenant_dashboard_registry; single entry point for dashboard composition.
  - Use instead of calling resolve_dashboard_widgets / get_tenant_dashboard_registry directly in new code.

## Touchpoints (existing)

### Workflow

| Location | What | Use hub? |
|----------|------|----------|
| apps.accounts.delegation | get_approval_roles_for_workflow, get_effective_approvers | Backend for workflow_resolver.get_approval_workflow |
| apps.academics.views_syllabus | get_effective_approvers(WORKFLOW_SYLLABUS_APPROVAL) | Can switch to workflow_resolver.get_approval_workflow(school, "syllabus_approval") |
| apps.evals.views | get_effective_approvers(WORKFLOW_GRADE_APPROVAL), syllabus approvers | Can switch to workflow_resolver.for_action(school, "grade_approval") |
| apps.portal (FormSignature) | Signature status flow (pending/signed/rejected/expired) | workflow_resolver.for_action(school, "form_signature") returns step list |
| apps.siteconfig.models_workflow | TenantWorkflow, WorkflowTemplate, run_workflow | workflow_resolver.for_action(school, template_code) returns automation def |
| apps.academics.models WorkflowConfig | Wizard steps (onboarding etc.) | Separate from business workflows; keep as-is |

### Dashboard

| Location | What | Use hub? |
|----------|------|----------|
| apps.siteconfig.models | default_dashboard_widgets(role), resolve_dashboard_widgets(role, preference) | Backend for dashboard_resolver.for_role |
| apps.siteconfig.dashboard_registry | get_tenant_dashboard_registry(school, role, page) | Backend for dashboard_resolver.for_role(..., include_registry=True) |
| apps.portal.views | resolve_dashboard_widgets(get_user_role(...), preference) | Can switch to dashboard_resolver.for_role(school, role, user=request.user)[\"widget_keys\"] |
| apps.evals.views | resolve_dashboard_widgets(role, preference) | Can switch to dashboard_resolver.for_role(school, role, user=request.user)[\"widget_keys\"] |
| apps.siteconfig.views_workflow_api | dashboard_registry_api | **Done:** uses dashboard_for_role(..., include_registry=True); returns result["registry"] |
| apps.api.dashboard_layout_api | get_layout_for_page, widget filtering by role | Layout API; can use dashboard_resolver for registry |

## Current state

- **Workflows:** Approval chains, signature flows, and state machines are implemented per app (e.g. portal signed forms, evals, finance approvals). siteconfig has workflow template concepts; workflow_resolver provides single entry point.
- **Dashboards:** Role-based dashboards use siteconfig (default_dashboard_widgets, resolve_dashboard_widgets, get_tenant_dashboard_registry); dashboard_resolver provides single entry point.

## Target (Phase 4) — implemented

1. **Workflow hub (tenant-facing UI)**
   - Single entry: `/siteconfig/workflow-hub/`. Workflow gallery: activate/deactivate/rollback. All via workflow_resolver.

2. **Dashboard hub (tenant-facing UI)**
   - Single entry: `/siteconfig/dashboard-hub/`. Configuration: assign template by role. All via dashboard_resolver.

3. **Original target (reference)**

1. **Workflow hub**
   - Define workflow types (e.g. form_signature, approval_chain, visa_cahier) and steps in a registry or config.
   - Single `workflow_resolver.for_action(tenant, action_slug)` (or similar) returns the workflow definition; apps call the hub instead of maintaining their own state machines.
   - Align with blueprint_registry_current_state.md: TenantWorkflowRegistry (or equivalent) as source of truth; apps consume, not define.

2. **Dashboard hub**
   - Define dashboard “families” and role-to-widget/section assignments (e.g. admin sees academics/finance/accounts; teacher sees classes/attendance).
   - Single `dashboard_resolver.for_role(tenant, role)` returns the composed dashboard; shell/templates render from that.
   - Align with Section 20.6: TenantDashboardAssignment; control-plane can assign per tenant/plan.

## Implementation order

1. Document existing workflow and dashboard touchpoints (which apps have approval/signature/dashboard logic).
2. Introduce workflow hub API and migrate one flow (e.g. form signature or cahier visa) to use it.
3. Introduce dashboard hub API and migrate one role’s dashboard to use it.
4. Extend to remaining workflows and roles; deprecate duplicated logic.

## References

- Checklist: Section 24.3 (workflow), 24.4 (dashboard).
- blueprint_registry_current_state.md: TenantWorkflowRegistry, TenantDashboardAssignment.
- RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md: Part D implementation sequence, Phase 4.
