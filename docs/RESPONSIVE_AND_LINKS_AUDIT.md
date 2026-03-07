# Responsive & Link/Button Audit

This document summarizes the responsive and clickability work done so the platform is usable on all devices and every control works and navigates correctly.

## Global

- **`static/css/platform-responsive-touch.css`**  
  - Viewport/overflow rules, min touch targets (44px for coarse pointer), focus-visible outlines, responsive containers, table-responsive, full-width forms on small screens.  
  - Included in: `templates/base.html`, `templates/control_plane_skeleton.html`, `templates/portal_base.html`.

## Control plane (manager.runmycampus.com)

- **Layout:** `manager-control-plane.css` — `.cp-layout`, `.cp-main-col`, `.cp-sidebar-col` use `min-width: 0` to avoid horizontal overflow; navbar brand scales with viewport; search results dropdown items have adequate padding and hover/focus.
- **Nav:** Desktop sidebar + mobile offcanvas (`#cpSidebarOffcanvas`). Toggler opens offcanvas; close button uses `data-bs-dismiss="offcanvas"`. Script in `control_plane_base.html` closes offcanvas when a sidebar nav link is clicked.
- **Links:** `partials/control_plane_sidebar.html` uses `<a href="{% url ... %}">` for all entries (Dashboard, Command Center, Provision tenant, Billing, Support, Governance, Blueprints, App catalog, Customer Success, Migration, Usage, Pulse, Tenant Health, Incidents, Configuration Engine, Sign out).

## Tenant portal / backend

- **Base:** `portal_base.html` includes `platform-responsive-touch.css`, `portal-sidebar.css`, and existing responsive rules (e.g. `dashboard-responsive.css`).
- **Sidebar:** Desktop column + mobile offcanvas (`#portalSidebar`). Toggler and close button wired; nav items are proper links.
- **Buttons/links:** Auth and key flows use `<button type="submit">` or `<a href="...">`; no div/span used as primary actions. Print and similar actions use `<button type="button" onclick="...">` with aria-label where appropriate.

## Public / auth (base.html)

- **`templates/base.html`** now includes `platform-responsive-touch.css`, so login, manager login, and any page extending `base.html` get the same touch targets and focus/overflow rules.
- **Auth:** `auth/login.html` and `auth/manager_login.html` use proper form submit buttons and `href` links (e.g. “Back to public site”).

## Checklist (for future passes)

- [ ] Any new page should extend the correct base (control plane vs portal vs base) and get the right CSS.
- [ ] New actions: use `<button type="submit">` or `<button type="button">` or `<a href="...">`; avoid clickable divs without role and keyboard support.
- [ ] New nav items: use `<a href="{% url 'app:view' %}">` (or equivalent) so they work in both desktop and mobile (offcanvas auto-close where implemented).
- [ ] Test at 320px, 768px, and 1024px width; confirm no horizontal scroll and that primary buttons/links are easily tappable.

---

## Full codebase audit (URLs, links, logic)

### URL / link fixes applied

1. **`config/urls.py`**  
   - Added `blog_post_detail` import and `path("blog/<slug:slug>/", blog_post_detail, name="marketing_blog_detail")` so blog post links in `schools/marketing_page.html` resolve when the root urlconf is used (not only public_urls).

2. **Hardcoded hrefs replaced with `{% url %}`**  
   - `templates/admin/index.html`: `/analytics/master-sheet/`, `/analytics/deadlines/`, `/reports/publish/`, `/siteconfig/customizer/clear-preview/` → `{% url 'analytics:master_sheet' %}`, `{% url 'analytics:deadlines' %}`, `{% url 'reports:publish_term_results' %}`, `{% url 'siteconfig:clear_preview' %}`.  
   - `templates/schools/marketing_landing.html`: `/book-demo/`, `/discover/` → `{% url 'marketing_book_demo' %}`, `{% url 'global_login_discovery' %}`.  
   - `templates/admin/base_site.html`: already used `{% url 'siteconfig:clear_preview' %}` for Clear preview.

3. **Left as intentional**  
   - `templates/schools/frozen_account.html`: `<a href="/super/">` — points to manager control plane; keep as absolute path for cross-host.  
   - `templates/accounts/mfa_setup.html`: `/docs/security/` — documentation path (can be made configurable later).

### Verification

- `python manage.py check` passes.  
- Config urlconfs (urls.py, tenant_urls.py, manager_urls.py, public_urls.py) are consistent; manager uses compat patterns and redirects for portal/finance/evals/kb/analytics/compliance/payroll.  
- Control plane sidebar and portal sidebar use `<a href="{% url ... %}">` throughout.  
- Base templates (base.html, portal_base.html, backend_base.html, control_plane_base.html, control_plane_skeleton.html) exist and are extended correctly.

### Views logic (permissions, redirects)

- **Auth:** Views use `@login_required`, `@user_passes_test` (e.g. control plane access, schema allowed, admin/staff) where appropriate. Marketplace, apicenter, portal (support, contact requests, AI copilot), siteconfig, compliance, accounts (certification) use login and/or permission checks.
- **Forbidden:** `HttpResponseForbidden` used for disabled features (API Center), missing permission (grading settings, modules, report template), and contact-request authorization.
- **Redirects:** No raw `redirect("/...")` or `redirect("https://...")` in app code; redirects use named URLs (e.g. `redirect("finance:invoice_detail", invoice_id=...)`, `redirect("evals:grade_approval_list")`).
- **Forms/errors:** Form validation and error handling are view-specific; no global gaps identified in the sampled views.

### Middleware order (config/settings.py)

- **Order:** Security → BlockScanner → WhiteNoise → ManagerCookieIsolation → Session → LegacyBaseDomainRedirect → UrlConfSwitcher → ReservedPublicHost → PublicPathRedirect → Tenant (or RlsReset) → Tenancy → PlatformRuntime → TenantFreeze → Sentry → LastActivity → ModuleActivation → ApiQuota → DynamicTheme → Locale → Common → CSRF → Authentication → ImpossibleTravel → RoleBasedSessionTimeout → ModuleAccess → RequireMFA → TenantSuperAdminRequired → SuperAdminRateLimit → FeatureGatekeeper → UsageLimit; then ComplianceGuard → OTP → Message → Maintenance → Preview → IPCountry → AuditLogging → AccessControl → RequestId → Observability → XFrame.
- **Critical path:** UrlConfSwitcher sets request.urlconf (public / tenant / manager); TenantMiddleware (or TenantMainMiddleware when USE_DJANGO_TENANTS) sets request.school; TenantFreezeMiddleware redirects frozen schools to `/account-frozen/`; TenantSuperAdminRequiredMiddleware restricts `/super/` to SUPERADMIN.

### Static / CSS / JS references

- **Fix applied:** `static/images/logo.png` was missing; added as copy of `runmycampus-icon.png` so fallbacks in portal_base, dashboard_footer, and siteconfig context (e.g. `_resolve_media_url(..., "images/logo.png")`) resolve.
- **Fix applied:** `static/js/photo-capture-id.js` was missing; added a minimal stub that wires a capture button to a file input so `portal/photo_upload_phone.html` does not 404. Replace with full camera/capture implementation if required.
- **Verified:** All `{% static 'css/...' %}` and `{% static 'js/...' %}` and `{% static 'vendor/...' %}` referenced in base.html, control_plane_base.html, portal_base.html, admin/base_site.html point to files that exist (design-tokens, bootstrap, platform-responsive-touch, htmx, manager-control-plane, etc.). `images/runmycampus-icon.png` and `images/runmycampus-logo.png` exist.
