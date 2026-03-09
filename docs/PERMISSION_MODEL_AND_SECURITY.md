# Permission model and security

**Goal:** Control-plane vs tenant-plane boundaries strict and documented; no exception masking in security paths; sensitive actions audited; permission model documented.

## Boundaries

- **Control-plane:** Manager host + `/super/*` + super-only API routes. Requires SUPERADMIN or is_superuser. Enforced by `require_super_access_with_host`, ManagerHostControlPlaneRequiredMiddleware, TenantSuperAdminRequiredMiddleware. See docs/CONTROL_PLANE_BOUNDARY_RULES.md.
- **Tenant-plane:** Tenant host; tenant URLconf; school-scoped data. Users have roles per school (ADMIN, TEACHER, etc.); no access to other tenants or `/super/`.

## Roles (summary)

- **Platform:** is_superuser (Django admin + control-plane); SUPERADMIN (control-plane access, may not be is_superuser).
- **Tenant:** SchoolMembership.role (ADMIN, TEACHER, GUARDIAN, etc.); permission checks via decorators and module_permissions. Student data, grade edit, invoice access follow role and policy.

## Sensitive actions and audit

Sensitive actions must emit audit events (actor, action, target, before/after where applicable):

- Impersonation (if implemented)
- Role change (user/tenant admin)
- Billing change (plan, subscription)
- Data export (compliance, report)
- Tenant delete / deactivate
- Policy or blueprint apply/rollback
- School lifecycle (activate, deactivate)

Implement or document per flow; add tests that sensitive actions emit audit events.

## Exception handling in security paths

- Do not use bare `except Exception` in auth or permission code without logging; never swallow auth/permission errors. Use specific catch and log; re-raise or return 403/500 as appropriate. See item 7 (exception hygiene) in runtime_resolver, tenancy middleware, policies resolver.

## Security checklist

- Run security review or penetration-test checklist; address findings. Document in docs/security-checklist.md or equivalent.

## References

- apps/accounts/permissions.py — role checks, control-plane strip
- apps/schools/control_plane.py — require_super_access_with_host
- apps/compliance/middleware.py — path allowlists
- docs/CONTROL_PLANE_BOUNDARY_RULES.md
