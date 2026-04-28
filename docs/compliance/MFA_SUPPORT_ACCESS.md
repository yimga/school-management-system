# MFA, support access, and impersonation (architecture map)

This note ties together **where** policy is enforced in this repository. It does not replace the single execution source of truth; it is an operator-facing map for security reviews.

## Multi-factor and step-up authentication

- **Login and session** layers (allauth, account views, tenant middleware) own MFA and step-up requirements.
- **Tenant RBAC** after login uses `apps/schools/tenant_access.has_school_permission` and `apps/schools/security_enforcer.enforce_tenant_security` — these assume an authenticated user and a resolved `request.school` when applicable; they do not implement MFA.

## Control plane vs tenant

- **Platform operators** (superuser or `User.role == SUPERADMIN`) are gated for manager-host and `/super/` surfaces by `apps/schools/control_plane.user_has_control_plane_access` and `require_super_access_with_host`.
- **Tenant staff** must not gain control-plane capabilities by being staff on a school subdomain; the control-plane contract is explicit and separate from membership RBAC.

## Support queue and exports

- Support tooling lives under `/super/` with the same control-plane gate. CSV exports of global support tickets are operator-only surfaces (see `apps/schools/super_views_support`).
- Tenant-scoped CSV exports should call `apps/schools/security_enforcer.best_effort_audit_export_download` (or the existing compliance export audit pattern) so `AuditLog` retains export provenance.

## Impersonation (switch-to-tenant)

- Entry point: `apps/schools/super_views_impersonation.switch_to_tenant` (POST, super-admin only).
- Schools may enable **dual control**: `impersonation_dual_control` requires a distinct peer approver email before issuing the signed impersonation handoff.
- All impersonation attempts should remain logged via `ImpersonationLog` and platform audit patterns already attached to that flow.

For generated governance visibility (POST risk, CSRF, AllowAny, raw SQL, subprocess, export hints), run:

`python scripts/audit_security_surface.py`  
`python scripts/audit_post_surface.py`

Or one step so the POST ledger embed matches the latest security scan:

`python scripts/audit_post_surface.py --refresh-security-audit`

The control-plane **Security surface** dashboard reads the emitted JSON under `docs/generated/` (`security_surface_audit.json`, `post_surface_audit.json`, `post_handler_audit.json`).
