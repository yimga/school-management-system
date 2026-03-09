# Shell architecture matrix

**Purpose:** Four surfaces (marketing, control-plane, admin backoffice, tenant app) have one canonical base template and one asset bundle each. No mixing of shells.

## Matrix: surface → base template → assets

| Surface | Canonical base | Extends | Key CSS/JS | URL / context |
|---------|----------------|---------|------------|----------------|
| **Marketing** | `templates/marketing/base_marketing.html` | — | design-tokens, tokens-marketing.css, marketing-shell.css; Bootstrap. No design-system-unified, no dashboard-*. | Public product pages, runmycampus.com marketing. |
| **Control plane** | `templates/control_plane_base.html` | control_plane_skeleton.html | design-tokens, design-system-unified, theme-visibility-guard, manager-control-plane.css, platform-high-end, surface-themes, table/form/card/chart, platform-responsive-touch. No marketing-shell. | `/super/*` (super dashboard, migration, tenant health, etc.). |
| **Admin backoffice** | Django admin / Unfold | config admin | Unfold/admin CSS. Separate from tenant portal. | `/admin/` (manager or tenant admin depending on URL config). |
| **Tenant app** | `templates/base.html` (shared/login/errors) or `templates/portal_base.html` (portal/backend) | — | base.html: design-tokens, design-system-unified, dashboard-*, theme-*, platform-*. portal_base: design-tokens, design-system-unified, portal_theme, dashboard-*, etc. backend_base extends portal_base. | Tenant subdomain: login, dashboard, portal, backend. |

## Hierarchy

- **Marketing:** `schools/marketing_base.html` → `marketing/base_marketing.html` (no further extend).
- **Control plane:** `control_plane_base.html` → `control_plane_skeleton.html` (skeleton has `<html>`, head, and body).
- **Tenant:** `backend_base.html` → `portal_base.html`. Standalone pages (login, errors, signup, find school) → `base.html`.
- **Admin:** Unfold/admin base_site.html.

## Rules

1. Marketing views must extend only `marketing/base_marketing.html` or `schools/marketing_base.html`; they must not load app-only CSS (design-system-unified, dashboard-*, theme-everywhere-dark).
2. Control-plane views must extend `control_plane_base.html` (or control_plane_skeleton); they must not load marketing-shell.css or tokens-marketing.css.
3. Tenant portal/backend views use portal_base or backend_base; shared/auth pages use base.html. No control-plane CSS in tenant views.
4. One base per surface; no cross-loading of surface-specific bundles.

## Tests

- `apps/platform_runtime/tests/test_marketing_shell.py`: marketing base does not include app-only stylesheets.
- Add test: control_plane_skeleton does not include marketing-only stylesheets (tokens-marketing.css, marketing-shell.css).

## References

- `docs/MARKETING_SHELL_VIEWS.md`
- `templates/base.html`, `templates/portal_base.html`, `templates/control_plane_skeleton.html`, `templates/marketing/base_marketing.html`
