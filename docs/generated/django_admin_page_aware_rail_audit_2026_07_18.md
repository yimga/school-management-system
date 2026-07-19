# Django admin page-aware rail — first audit (2026-07-18)

Scope: **operator + tenant** Django admin (`/admin/` on manager and tenant hosts).

Approved design: `var/design-previews/django-admin-page-aware-rail-approval-2026-07-18.html`

## Gate results (pre-fix)

| Gate | Result |
|------|--------|
| `audit_django_admin_canvas_contract.py` | PASS (page-aware tokens already present on shared change-form/list/index rails) |
| `audit_django_surface_platformwide_contract.py` | **FAIL** — stale cache token `?v=20260717-parity-close` |
| `audit_tenant_surface_scroll_contract.py` | **FAIL** — same stale admin cache token |
| `scan_undefined_css_classes.py` | PASS (0) |

## Surface matrix

| Surface | Operator | Tenant | Page-aware rail | Notes |
|---------|----------|--------|-----------------|-------|
| Index (`index_superadmin` / `index_tenant`) | Yes | Yes | Wired | Shared `admin_index_context_rail` |
| Change form | Yes | Yes | Wired | Pulse + facts; History/View in head |
| Change list | Yes | Yes | Wired | Counts/filters |
| App index | Shared | Shared | **GAP** | Command band only — no rail/workbench |
| `delete_guided` / `waive_subscription` | Operator | — | **GAP** | `base_site` content override, no canvas |
| Model overrides extending `change_form`/`change_list` | Inherit | Inherit | OK | Inherit shared canvas |
| CountryRegistry preview | Operator | — | OK | Real model drawer, not staged rail preview |

## Gaps to close (this pass)

1. Bump platformwide + tenant-scroll audits to `?v=20260718-page-aware-rail`.
2. App index: two-column workbench + page-aware rail.
3. Guided school forms: premium workspace + page-aware rail.
4. Rail links: do not duplicate History / View on site (already in head actions).
5. Canvas audit: drop staged `rmc-django-preview-card` requirement; require page-aware on index + app-index.
6. Re-audit A–Z after fixes.
