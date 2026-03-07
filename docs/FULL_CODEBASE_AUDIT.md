# Full Codebase Audit – Summary

This document records the audit pass over URLs, templates, views, and logic. It is intended to be extended as more areas are reviewed.

## 1. URL configuration

### Fixes applied

- **`config/urls.py`**
  - **`marketing_blog_detail`** was only defined in `config/public_urls.py`. The main urlconf (used for tenant and default) did not define it, so the blog listing template (`schools/marketing_page.html`) could raise `NoReverseMatch` when rendering post links. **Fix:** Imported `blog_post_detail` from `apps.schools.marketing_views` and added `path("blog/<slug:slug>/", blog_post_detail, name="marketing_blog_detail")` to the main urlpatterns.

### Hardcoded links replaced with `{% url %}`

- **`templates/admin/index.html`**
  - `/analytics/master-sheet/` → `{% url 'analytics:master_sheet' %}`
  - `/analytics/deadlines/` → `{% url 'analytics:deadlines' %}`
  - `/reports/publish/` → `{% url 'reports:publish_term_results' %}`
  - `/siteconfig/customizer/clear-preview/` → `{% url 'siteconfig:clear_preview' %}`
- **`templates/admin/base_site.html`**
  - `/siteconfig/customizer/clear-preview/` → `{% url 'siteconfig:clear_preview' %}`
- **`templates/schools/marketing_landing.html`**
  - `/book-demo/` → `{% url 'marketing_book_demo' %}`
  - `/discover/` → `{% url 'global_login_discovery' %}`

- **`templates/widgets/parent_dashboard_widgets.html`**
  - `href="/finance/"` → `href="{% url 'finance:dashboard' %}"`
  - `href="/finance/payments/"` → `href="{% url 'finance:payments' %}"`

### Left as-is (intentional)

- **`templates/schools/frozen_account.html`**  
  `href="/super/"` is kept as a direct link to the super-admin surface; acceptable for this context.
- **`templates/accounts/mfa_setup.html`**  
  `/docs/security/` is an internal doc path; no change.
- **`templates/schools/marketing_landing.html`**  
  Other hardcoded paths in that file were not changed in this pass; can be revisited.

## 2. URL → view linkage (verified)

- **config/urls.py, config/tenant_urls.py, config/manager_urls.py**  
  All top-level paths and includes point to existing modules and callables.
- **apps.schools.super_urls**  
  All names (e.g. `dashboard`, `command_center`, `create_school_wizard`, `billing_dashboard`, `marketplace_governance`, `blueprint_marketplace`, `app_catalog`) resolve to views in `super_views` or `marketplace.views` or `customersuccess.views_super`.
- **Manager host**  
  `platform_incidents_console` is defined in `config/manager_urls.py` and points to `obs_views.platform_incidents_console`.
- **Django check**  
  `python manage.py check` passes with no issues.

## 3. Templates (partial)

- **URL names in templates**  
  Sampled template references to `accounts:*`, `portal:*`, `siteconfig:*`, `finance:*`, `reports:*`, `analytics:*`, `communication:*`, `evals:*`, `kb:*`, `admin:*`, `super:*` match existing URL names in the corresponding urlconfs.
- **`marketing_blog_detail`**  
  Used in `schools/marketing_page.html`; now defined in main urlconf (see above).
- **`approval_workflow_hub`**, **`dashboard_configuration_hub`**  
  Present in `apps.accounts.urls` and `apps.siteconfig.urls` respectively.

## 4. Views and logic (sampled)

- **Accounts**  
  `approval_workflow_hub` and other URL-backed views exist in `apps.accounts.views` and related modules.
- **Siteconfig**  
  `dashboard_configuration_hub`, `workflow_hub`, `workflow_flow_gallery`, `clear_preview` exist and are wired in urls.
- **Finance**  
  `notifications` view and URL name exist.
- **Control plane**  
  Sidebar and manager search use correct `reverse()` names; manager redirects (e.g. portal/finance/evals) go to `super:dashboard` or equivalent.

## 5. Middleware and settings

- Not changed in this pass. Order and behavior can be audited separately (see Phase10 and execution map docs).

## 6. Static / CSS

- **platform-responsive-touch.css**  
  Included in `base.html`, `control_plane_skeleton.html`, and `portal_base.html`.
- **manager-control-plane.css**  
  Layout and navbar responsive rules added (see RESPONSIVE_AND_LINKS_AUDIT.md).

## 7. Recommended next steps

1. **Template sweep**  
   Run a project-wide search for remaining hardcoded `href="/..."` and `action="/..."` and replace with `{% url %}` where the target is an in-app view.
2. **View logic**  
   Per-app review of permission checks, redirects, and form handling (especially POST targets and success URLs).
3. **Tests**  
   Run the full test suite (and Phase10 control-plane tests) after any further URL or view changes.
4. **Extend this doc**  
   Add sections for each app (evals, academics, compliance, api, etc.) as they are audited in detail.
