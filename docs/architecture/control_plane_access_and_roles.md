# Control plane access and roles

**Purpose:** Document how control plane (super-admin) access is enforced. There is no separate role model; access is via Django superuser and a single gate.

**Reference:** PLAN_COMPLIANCE.md Phase 9 "Control-plane roles and permissions (own role system) | Deferred (access via require_super_access / superuser)".

---

## Current implementation

- **Who can access:** Any user with `is_superuser=True` (Django admin superuser). There is no separate "control plane role" table or enum.
- **How it is enforced:** All super-admin views are wrapped with `require_super_access` (see `apps/schools/control_plane.py`). That decorator checks that the request user is authenticated and has `user.is_superuser`. If not, the user is redirected or shown 403.
- **URLs:** All control plane routes live under the manager host (e.g. `manager.runmycampus.com/super/`) and are included in `apps/schools/super_urls.py`; each path is wrapped with `require_super_access(super_views.view_name)`.

---

## No separate role system

By design, there is **no** ControlPlaneRole or SuperAdminRole model. Rationale:

- One gate (`require_super_access` + `is_superuser`) is easier to audit and secure.
- If finer-grained roles are needed later (e.g. "support only", "billing only"), they can be added as a separate phase with a role model and permission checks.

---

## Done when

- [x] Access is documented (this file).
- [x] All super views use `require_super_access`.
- [ ] Optional: add a dedicated role model and assignable permissions only if product requires it.
