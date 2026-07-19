# Django admin page-aware rail — second audit A–Z (2026-07-18)

Approved design implemented. Re-audit after gap closure.

## Gates (post-fix)

| Gate | Result |
|------|--------|
| `audit_django_admin_canvas_contract.py` | **PASS** |
| `audit_django_surface_platformwide_contract.py` | **PASS** |
| `audit_tenant_surface_scroll_contract.py` | **PASS** |
| `scan_undefined_css_classes.py` | **PASS** (0) |
| `scan_off_token_colors.py` | **PASS** (0) |
| `verify_template_compiles.py` | **PASS** (1851 / 0) |
| `verify_service_worker_version.py --check-monotonic` | **PASS** `sms-v4.05.145-admin-page-aware-a2z-2026-07-18` |
| `apps.siteconfig.tests.test_admin_page_aware_rail` | **PASS** (6) |

## Surface matrix (12/12)

| Surface | Page-aware | Premium canvas | Operator | Tenant |
|---------|------------|----------------|----------|--------|
| Index superadmin | Yes | Yes | Yes | — |
| Index tenant | Yes | Yes | — | Yes |
| Change form (shared) | Yes + Form pulse | Yes | Yes | Yes |
| Change list (shared) | Yes | Yes | Yes | Yes |
| App index | Yes | Yes | Yes | Yes |
| Guided delete school | Yes | Yes | Yes | — |
| Guided waive subscription | Yes | Yes | Yes | — |
| Model overrides extending change_form/list | Inherit | Inherit | Yes | Yes |

## Closed from first audit

1. Stale cache tokens → `?v=20260718-page-aware-a2z`
2. App index missing rail → workbench + `admin_app_index_rail`
3. `delete_guided` / `waive_subscription` missing canvas → guided workspace + rail
4. History/View no longer duplicated in rail links (head only)
5. Staged Live preview remains removed

## Honest residual

- Live Playwright screenshots of `/admin/` still need a running Django instance + login (not claimed in this batch).
