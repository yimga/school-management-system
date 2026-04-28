# Access control policy (RunMyCampus product)

## Scope

Applies to the Django monolith: tenant hosts, manager (control-plane) host, public/marketing hosts, and API host as configured in `config/settings.py` and URLconfs under `config/`.

## Principles

1. **Platform operators** (superuser or `SUPERADMIN` role) may use manager-host and `/super/` surfaces per `apps/schools/control_plane.py`.
2. **Tenant staff** use tenant URLconf; they must not receive manager-host capabilities by cookie alone (see `ManagerHostControlPlaneRequiredMiddleware` and related tests).
3. **Students / parents / teachers** are scoped to portal and role-specific URLs; backend dashboard requires staff and tenant context.
4. **Django admin** remains an **advanced** operator surface; control-plane UIs are preferred for routine operations (see admin gravity audit).

## Evidence

- `apps/schools/middleware.py`, `apps/accounts/decorators.py`
- Tests: `apps/schools/tests/test_control_plane_boundary.py`, `apps/tenancy/tests/test_manager_urlconf_boundary.py`
- Generated: `docs/generated/admin_gravity_audit.json`

## Review

Re-run `python scripts/audit_admin_gravity.py --strict` and security surface audit after material auth or middleware changes.
