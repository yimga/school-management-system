# Marketing shell — which views use which base

**Purpose:** Public marketing (runmycampus.com) must not inherit the app shell. Marketing has its own base template and CSS/JS bundle.

## Marketing base (no app chrome)

- **Template:** `templates/marketing/base_marketing.html` or `templates/schools/marketing_base.html` (which extends base_marketing).
- **CSS loaded:** `design-tokens.css`, `marketing/css/tokens-marketing.css`, `marketing/css/marketing-shell.css` only. No `design-system-unified.css`, no `dashboard-*.css`, no `theme-everywhere-dark.css`.

## Views that use marketing shell

Templates that extend `marketing/base_marketing.html` or `schools/marketing_base.html`:

- `marketing/marketing_compare_page.html`
- `schools/marketing_topic_page.html`
- `marketing/marketing_role_page.html`
- `schools/marketing_landing.html` (extends schools/marketing_base)
- `schools/marketing_blog_detail.html`
- `schools/developer_sdk.html`
- `marketing/marketing_institution_page.html`
- `schools/developer_portal.html`
- `schools/marketing_page.html`
- (Any other template extending `marketing/base_marketing.html` or `schools/marketing_base.html`)

## App shell (base.html, backend_base.html, portal_base.html, control_plane_base.html)

Login, errors, signup, FAQ, school find, support hub, docs landing, onboard wizard, tenant dashboard, backend, and control-plane views extend `base.html`, `backend_base.html`, `portal_base.html`, or `control_plane_base.html` and load the full app CSS/JS.

## Test

CI asserts that `templates/marketing/base_marketing.html` does not include app-only stylesheets (design-system-unified, dashboard-*, theme-everywhere-dark). See `apps/platform_runtime/tests/test_marketing_shell.py` (or lint step).
