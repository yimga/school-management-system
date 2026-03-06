# Refactor Waves (Checklist 12.7)

Verification of the refactor wave sequence and control plane hardening.

**Wave order:** Tenancy cleanup → Blueprint foundation → Admissions refactor → Gradebook/attendance → Finance/comms → Dashboard/workflow → Marketplace → Control plane hardening.

---

## Wave 1: Tenancy cleanup
- **Status:** Done. TENANCY_MODE (SCHEMA | RLS), apps/tenancy (context, strategy, middleware, checks), single tenant resolution from host, no second tenancy model. Documented in tenancy.md.

## Wave 2: Blueprint foundation
- **Status:** Done. TenantBlueprint, PolicyBundle, BlueprintPack; get_effective_policy(school), get_tenant_blueprint(request); policy_injection.md; resolver merges platform/country/tenant.

## Wave 3: Admissions refactor
- **Status:** Done. Admissions module uses policy for labels, admission number, mode; REPEATABLE_REFACTOR_PATTERN; policy_injection.md § Admissions.

## Wave 4: Gradebook/attendance
- **Status:** Done. Gradebook/reports use policy (grading_scale, default_language, report labels); siteconfig/accounts/reports use get_effective_policy only where required.

## Wave 5: Finance/comms
- **Status:** Done. Full policy-driven config (Section 10): finance, attendance, communication in get_effective_policy with all listed items; section_10_helpers and context_processors expose tenant_attendance_policy, tenant_communication_policy; finance gateways use policy; Invoice media tenant-prefixed.

## Wave 6: Dashboard/workflow
- **Status:** Done. workflow_resolver and dashboard_resolver as platform services; portal, evals, academics, views_workflow_api migrated to hubs; phase4_workflow_dashboard_hubs.md.

## Wave 7: Marketplace
- **Status:** Done. BlueprintPack + apply flow; manager Blueprint marketplace and App catalog UIs; Phase 6; phase6_marketplace.md. Governance console, install pipeline, 24.12 schema contracts.

## Wave 8: Control plane hardening
- **Status:** Done. require_super_access on all super views; SuperAdminRateLimitMiddleware (120/min); audit log for approve/create/impersonation/sync-repair; control_plane_runbooks.md; observability (request_id, tenant_id, metrics) and security baseline (SAST/DAST) per section_25.

---

## Checklist 12.7
Refactor waves 1–8 are complete. Phases 1–6 and Phase 7 (24.12–24.15) delivered. Control plane hardening: permission checks, rate limiting, audit logging, runbooks, and observability implemented and documented.
