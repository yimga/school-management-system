# SiteSettings Field Classification

**Purpose:** Platform transition audit (Prompt 1). Tenant-facing code must not call `SiteSettings.get_solo()` for tenant behavior; use `request.tenant_runtime` or `apps.platform_runtime.helpers` (`get_effective_flags`, `get_effective_site_settings`, `get_site_display_name`, etc.) instead.

**Allowed to call `get_solo()`:** Control-plane only code (manager host, admin/super views), platform-default builders (e.g. `policies.resolver` when building policy for a school), `siteconfig.models` internals, `platform_runtime.helpers` shims, and management commands that run in platform context.

---

## Control-plane only (platform / superadmin)

- `admin_theme_pack`, `admin_use_site_primary` — Configuration Engine branding
- Theme pack FKs used only on manager/admin
- `preview_mode_enabled`, `preview_note`, `preview_toggle_*` — Admin preview
- Platform-wide feature toggles (when added)

**Use in:** Manager host views, `/admin/` views, super dashboard, provisioning.

---

## Public-only (marketing / unauthenticated)

- `site_name`, `tagline`, `meta_description` when no tenant
- `login_hero_heading`, `login_hero_subtext`
- Public branding (logo, favicon) when not in tenant context

**Use in:** Public pages, login when `request.school` is None. Prefer `get_effective_site_settings(request)` or `get_site_display_name(request)` so tenant context is respected when present.

---

## Tenant-runtime defaults (must flow via runtime/policy)

All tenant-facing behavior must resolve from `request.tenant_runtime` or `get_effective_*` helpers (which layer school/policy over platform defaults). Do **not** read these from `SiteSettings.get_solo()` in tenant views, context processors, or tenant-scoped models/services:

- **Branding:** `site_name`, `company_name`, `primary_color`, `accent_color`, theme pack FKs, logo, favicon, layout_style, default_sidebar_collapsed
- **Feature flags:** `backend_feature_flags` → use `get_effective_flags(request)` or `get_effective_flags_for_school(school)`
- **Admissions:** `school_code`, `admission_number_*` → use policy `admissions` section or `get_effective_policy(school)["admissions"]`
- **Grade approval:** `grade_post_roles`, `grade_approval_*` → use policy `grade_approval` section
- **Finance:** `finance_payment_reminder_default_*` → use policy finance section or helper
- **Dashboard/widgets:** `default_widgets_per_role`, `portal_sidebar_order` → use runtime dashboards / `get_effective_dashboard(request, role)`
- **Portal:** `portal_*`, `report_downloads_enabled`, `enable_offline_mode` → use `get_effective_site_settings(request)` when request is available

**Use in:** Tenant views, context processors, tenant app models (via helpers/policy only).

---

## Lint and tests

- `scripts/lint_tenant_settings.py` — Flags `SiteSettings.get_solo()` in tenant apps (excluding allowlisted paths and test files). Run in CI; fail on hits.
- Tenant-facing production code in `apps/portal`, `apps/evals`, `apps/finance`, `apps/dashboard`, `apps/people`, `apps/communication`, `apps/accounts`, `apps/reports`, `apps/api`, etc. must not call `get_solo()` except via allowlisted platform-default layers.

See: `docs/PLATFORM_TRANSITION_AUDIT_REPORT.md`, `docs/PLATFORM_AUDIT_REMEDIATION_BACKLOG.md`.
