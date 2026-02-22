# Tenant Media & Design Studio (Phase F)

## Tenant media prefix

All tenant-specific uploads must use the path prefix `tenants/{school_id}/` so that:

- Files are isolated per school (no cross-tenant access).
- Storage (e.g. S3) can use the same prefix for lifecycle or permissions.

### Implementation

- **Helper:** `apps.siteconfig.models._tenant_upload_to(subpath)` returns an `upload_to` callable that generates `tenants/{school_id}/{subpath}/{filename}`. Use it for any `FileField` or `ImageField` on a model with a `school` FK.
- **Example:** `WaiverRequest.proof_file` uses `upload_to=_tenant_upload_to("waiver_requests")`.
- **New models:** When adding file fields on tenant-scoped models, set `upload_to=_tenant_upload_to("your_subpath")` (and ensure the model has a `school` FK).

### Optional: DEFAULT_FILE_STORAGE

For S3 or custom storage, you can use a storage class that always prefixes keys with `tenants/{tenant_id}/` when the request context is available. The current approach (per-field `upload_to` with `_tenant_upload_to`) works with the default filesystem storage and does not require a custom storage class.

## Branding API

- **URL:** `GET /siteconfig/api/branding/` (requires login; tenant context from `request.school`).
- **Response:** `{ "logo_url", "primary_color", "accent_color", "custom_css" }`.
- When `BrandSettings` exists for the school, it is used; otherwise `School.logo_url`, `primary_color`, `accent_color` are returned.
- Frontend can inject these as CSS variables (e.g. `--brand-primary`, `--brand-accent`) for white-label.

## Design Studio (DesignTemplate)

- **Model:** `DesignTemplate`: school, name, document_type (report_card, certificate, invoice, id_card), layout (JSON), is_default.
- **Layout JSON:** Blueprint with widgets, positions, and placeholders (e.g. `{{student_name}}`). To be extended with a full-screen canvas editor (Fabric.js / dnd-kit) later.
- **Rendering:** Use `apps.siteconfig.design_studio.render_template_to_pdf(template, context)` to hydrate placeholders and produce PDF (WeasyPrint when available).
