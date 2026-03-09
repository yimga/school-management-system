# Control-plane vs tenant-plane boundary rules

**Purpose:** Enforce separation between control-plane (superadmin, platform ops) and tenant-plane (tenant users). No tenant code can access control-plane resources; no control-plane code relies on tenant request context inappropriately.

## Rules

1. **URL namespace:** All control-plane views live under `/super/` (or manager host). Tenant views live under tenant subdomain or paths that resolve to tenant context.
2. **Permission:** All `/super/` views require control-plane permission (e.g. superadmin or explicit `can_access_control_plane`). Tenant users must receive 403 when hitting control-plane URLs.
3. **Middleware:** Middleware sets `request` surface to `control_plane` or `tenant_plane` (see `apps/platform_runtime.contracts.RouteContext.surface`). Use this to gate behavior.
4. **Data:** Tenant views must not read/write control-plane-only DB (e.g. platform-wide School list for provisioning). Control-plane views may read tenant data for ops but must scope by tenant.

## Tests

- `apps/accounts/tests/test_control_plane_boundaries.py`: superadmin vs tenant_admin module access; GraphQL school registry is control-plane only.
- `apps/schools/tests/test_control_plane_boundary.py`: extend with assertion that tenant user cannot access `/super/*` URLs (HTTP 403 or redirect).

## References

- `apps/platform_runtime/contracts.py` (RouteContext.surface)
- `apps/schools/control_plane.py`
- `apps/accounts/permissions.py` (can_access_module, control-plane checks)
