# Prompt 2 — Superadmin vs Tenant Boundary Audit Report

**Date:** 2026-03-06  
**Scope:** Control plane (Superadmin) vs tenant plane separation  
**Non-negotiable:** All boundary violations must be remediated.

---

## 1. Control-plane architecture review

### Layer 1 — Platform Control Plane (RunMyCampus)

- **URLconf:** Manager host uses `config.manager_urls`; `/super/` is included there only. Tenant host does not serve `/super/`.
- **Entry points:** All `/super/` views are registered in `apps/schools/super_urls.py` and wrapped with `require_super_access_with_host`.
- **Decorator:** `require_super_access_with_host` (apps/schools/control_plane.py) enforces:
  1. Request is on control-plane surface (manager host or path starting with `/super/`).
  2. User has control-plane access: `user_has_control_plane_access(user)` → SUPERADMIN or is_superuser.
- **Templates:** Control-plane pages extend `control_plane_base.html` / `control_plane_skeleton.html`; sidebar is `partials/control_plane_sidebar.html`. Documented in `docs/CONTROL_PLANE_TEMPLATES.md`.
- **Surfaces:** Dashboard, command center, create school, usage, migration cloud, pulse, tenant health, registries, blueprints, policies, workflow/dashboard packs, customer-success, billing, marketplace (governance, sandbox, incidents), support, switch-to-tenant, sync-repair, AI model hub, runtime inspector, workflow simulator, compliance, analytics, policy-diff.

### Layer 2 — Tenant Runtime Plane (schools)

- **URLconf:** Tenant URLconf is used when host is tenant (school subdomain or /t/<slug>/). Tenant views never serve `/super/` routes.
- **School context:** `request.school` set by middleware for tenant requests; tenant views and services filter by school/schema.

### Layer 3 — User Experience Plane (teachers, parents, students)

- **Portals and role-based surfaces:** Parent/teacher/student portals and tenant admin dashboards; all run in tenant context with tenant URLconf.

---

## 2. Tenant-plane architecture review

- Tenant apps: academics, people, finance, evals, reports, communication, analytics, payroll, school_events, requests, etc., live under tenant URLconf.
- Tenant models are in TENANT_APPS (schema-per-tenant or RLS); no tenant view should access control-plane-only URLs without explicit switch-to-tenant (which is super-only).

---

## 3. Boundary violation inventory

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| 1 | Tenant and shared apps (siteconfig, portal) contain both platform and tenant logic; separation is by URLconf + decorator, not by app boundary. | Low | Accepted: documented; control-plane views are on manager host only. |
| 2 | Marketplace views use `@user_passes_test(_control_plane_access)` but are also mounted under `/super/` with `require_super_access_with_host` in super_urls — defense in depth. | None | Correct. |
| 3 | Any view that uses only `is_staff` without host/surface check could be accessed from tenant host if URLconf leaked — audit for staff-only views on shared URLs. | Medium | Mitigated: `/super/` and manager-only routes use require_super_access_with_host; tenant URLconf does not include these. |

**No critical boundary violations found:** Control-plane routes are host- and path-protected; tenant routes do not expose super views.

---

## 4. Recommended structural corrections

1. **Done:** All `/super/` and manager-only views use `require_super_access_with_host`.
2. **Done:** Control-plane templates documented; super views use control_plane_base.
3. **Ongoing:** When adding new manager-only views, always register under manager_urls and wrap with `require_super_access_with_host`.
4. **Optional:** Consider moving all super views into a dedicated `apps/control_plane/` or `apps/superadmin/` package for clearer app boundary (not required for security).

---

## 5. Evidence summary

- **super_urls.py:** 70+ routes all wrapped with `require_super_access_with_host`.
- **control_plane.py:** `user_has_control_plane_access`, `_is_super_surface`, `require_super_access_with_host` implement host + role check.
- **CONTROL_PLANE_TEMPLATES.md:** Lists control-plane-only templates and decorator usage.
- **PLATFORM_AUDIT_REMEDIATION_BACKLOG.md:** Superadmin vs tenant boundary item marked Done.

---

**Next:** Proceed to Prompt 3 (Tenant Data Isolation and Security).
