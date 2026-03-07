# Phase F Plan Checklist (optional / polish)

## Done

- **Tenant media prefix:** `_tenant_upload_to(subpath)` in `apps.siteconfig.models` yields `tenants/{school_id}/{subpath}/{filename}`. `WaiverRequest.proof_file` uses it. See `docs/TENANT_MEDIA_AND_DESIGN_STUDIO.md`.
- **Branding API:** `GET /siteconfig/api/branding/` returns logo, colors, custom_css for `request.school`.
- **DesignTemplate:** Model and layout JSON; `design_studio.render_template_to_pdf()` for PDF output.

## Optional / deferred

- **Design Studio canvas editor:** Full drag-and-drop (Fabric.js / dnd-kit) or form + JSON layout + preview is deferred. Layout is editable as JSON for now.
- **Tenant media everywhere:** New FileField/ImageField on tenant-scoped models (with school FK) should use `upload_to=_tenant_upload_to("subpath")`. Existing fields (e.g. BrandSettings logo/background) use static paths; optional follow-up migration can switch them to tenant prefix for consistency.
