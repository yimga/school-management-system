# Phase F — Design Studio & Parent/Student Portal

## Design Studio (existing)

- **DesignTemplate / BrandSettings** in siteconfig; tenant media prefix `tenants/{school_id}/` via `_tenant_upload_to()`.
- **Branding API:** `GET /api/config` returns `logoUrl`, `primaryColor`, `accentColor`, `schoolName`, `features`, `offlineEnabled` (schools.api_views.SchoolConfigAPI).
- **design_studio.py:** `render_template_to_html`, `render_template_to_pdf`, `design_template_http_response_pdf` for WeasyPrint/HTML.

## Parent portal (Phase F)

- **Bento encouragement dashboard:** Hero/GPA, schedule, attendance ring, pending tasks; conditional TRADE vs GENERAL blocks (existing parent_dashboard can be extended with Bento layout).
- **Child switcher:** Use `apps/portal/parent_portal_helpers`: `get_active_child_id(request)`, `set_active_child(request, child_id)`. Add a view that accepts `child_id`, calls `require_parent_child_access(request, child_id)`, then `set_active_child(request, child_id)` and redirects or returns HTMX fragment.
- **RTL:** In parent portal context, set `is_rtl` from `school.default_region` (e.g. RegionConfig or locale) so templates can use `dir="rtl"` / `html dir="{{ is_rtl|yesno:'rtl,ltr' }}"`.
- **Privacy:** Any view that takes `child_id` (query or path) must call `require_parent_child_access(request, child_id)` and bail with 403 if it returns `(None, response)`.
