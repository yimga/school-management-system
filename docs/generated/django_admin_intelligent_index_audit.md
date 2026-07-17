# Django Admin Canvas Intelligent Index Audit

Generated: 2026-07-17

## Result

Status: DONE (repo-scope) — mechanical canvas + platformwide contracts green.

## Before (live screenshot vs preview)

| Surface | Live (before) | Preview target |
| --- | --- | --- |
| Tenant `/admin/` | Empty void, green Feature Control strip, Raw model CRUD banner | Full-canvas command surface with usable catalog |
| Tenant change_form / change_list | Structural hooks already present | Command band + rail + native table |
| Operator `/admin/` | Catalog hub already intelligent | Same canvas contract markers |

## Root causes

1. `index_tenant.html` steered users away from admin instead of filling the canvas with a searchable model catalog.
2. `admin_nav_bridge.html` injected `operator_console_strip` on the admin index whenever `PRIMARY_CONTROL_PLANE_NAV` was set.
3. `base_site.html` forced `data-surface=control-plane` on tenant admin, so tenant index CSS selectors never applied.
4. `.tenant-admin-index { min-height: 100vh }` amplified the empty middle.

## Fixes

- Rewrote tenant index as `smart-index` workspace (command band, KPIs, searchable catalog, context rail).
- `TenantAdminSite.index` builds `admin_catalog` via `build_platform_admin_catalog`.
- Skip `operator_console_strip` on `admin:index`.
- Host-aware `data-surface` (`tenant` vs `control-plane`).
- Canvas CSS index two-pane layout; cache key `20260717-intelligent-index`.
- Audits extended to forbid Raw-CRUD-only tenant index.

## Validation

- `python scripts/audit_django_admin_canvas_contract.py` → PASS
- `python scripts/audit_django_surface_platformwide_contract.py` → PASS
- `python scripts/audit_tenant_surface_scroll_contract.py` → PASS
- `SECRET_KEY=local-validation-only python scripts/verify_django_admin_canvas_templates_compile.py` → PASS

## Honest residual

Live browser screenshots of tenant/operator `/admin/` remain operator-gated when local SQLite schema drifts.
