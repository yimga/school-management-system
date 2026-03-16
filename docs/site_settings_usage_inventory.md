# SiteSettings Usage Inventory

**Purpose:** Single inventory of every `SiteSettings` field and usage site to support §2.1 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Classify each usage; move ownership into bounded contexts; replace direct singleton reads with runtime resolvers.

**Status:** NOT DONE — inventory created; classification and migration in progress.

---

## 1. Usage sites (code)

### 1.1 Runtime path (`get_effective_site_settings`) — preferred

| File | Notes |
|------|--------|
| `apps/portal/views_onboarding.py` | request-scoped |
| `apps/platform_runtime/helpers.py` | defines resolver; fallback to `build_platform_default_site_settings` when no school |
| `apps/evals/approval.py` | school-scoped |
| `apps/accounts/context_processors.py` | request-scoped `site_settings_context` |
| `apps/observability/views.py` | request-scoped |
| `apps/finance/admin.py` | school-scoped |
| `apps/finance/views.py` | multiple views; request-scoped |
| `apps/portal/views.py` | multiple views; request-scoped |
| `apps/schools/middleware.py` | (imports helpers) |
| `apps/dashboard/admin_context.py` | request-scoped |
| `apps/accounts/tasks.py` | school-scoped |
| `apps/payroll/services.py` | school-scoped |
| `apps/reports/management/commands/generate_regional_reports.py` | no request |
| `apps/siteconfig/context_processors.py` | `site_settings()` uses get_effective_site_settings or build_platform_default_site_settings |
| `apps/analytics/tasks.py` | uses `get_cached_site_settings(school=)` (automation helper) |
| `apps/evals/caching.py` | uses `get_cached_site_settings(school=)` (§2.1: was SiteSettings.load()) |

### 1.2 Platform / control-plane only (`SiteSettings.get_solo()` or `.objects`) — allowlisted

| File | Context | Action |
|------|---------|--------|
| `apps/siteconfig/context_processors.py` | Imports model; uses get_effective_site_settings in request path | OK |
| `apps/siteconfig/signals.py` | Invalidates cache on SiteSettings save | Platform |
| `apps/siteconfig/migrations/*` | Migrations | Keep |
| `apps/platform_runtime/models.py` | `sync_from_site_settings(site_settings)` — caller passes instance | Platform |
| `apps/platform_runtime/helpers.py` | `get_platform_site_settings_record()`, `_build_platform_site_settings_base()` | Platform |
| `apps/siteconfig/management/commands/seed_admin_dashboard_palettes.py` | Command; uses get_platform_site_settings_record | Platform |

**Tests:** All test files that previously used `SiteSettings.get_solo()` have been migrated to `get_platform_site_settings_record(create=True)` or `get_effective_site_settings(school=...)`. No test file calls `get_solo()` directly. (SiteSettings model still imported where needed for `.objects` or admin registry, e.g. test_theme_studio, test_access_requests.)

### 1.3 Lint and scripts

| Script | Purpose |
|--------|---------|
| `scripts/lint_tenant_settings.py` | CI: flag get_solo() in tenant apps |
| `scripts/generate_platform_inventory.py` | Reports SiteSettings refs; uses domain_ownership |

---

## 2. Field classification (target owner)

Classification from `apps/siteconfig/domain_ownership.py`. Each field should move to the bounded context listed; tenant-facing reads must go through runtime.

| Owner | Fields (examples) |
|-------|-------------------|
| safe_platform_default | maintenance_mode, cache_rankings_interval_minutes |
| brand_experience | site_name, tagline, meta_description, primary_color, theme_pack, admin_theme_pack, favicon, custom_css, ... |
| runtime_blueprints | admin_portal_stats_config, default_widgets_per_role, school_code, admission_number_* |
| policies_rules | backend_feature_flags, portal_features, grade_approval_enabled, require_mfa_*, ... |
| plans_entitlements | (future) |
| global_registries | country, region, ministry, default_region, default_grading_scale, ministry_registration_code |
| metadata_governance | (future) |
| marketplace_integrations | sms_provider, sms_api_key, whatsapp_*, email_from_address, marksheet_ocr_command |
| reports | default_report_preview_type, report_preview_*, enable_reports_pdf, reports_* |
| documents | auto_tag_photos_from_exif |
| preview_platform | preview_mode_enabled, preview_note, skip_theme_publish_guard |
| delete | updated_at (metadata only) |

### 2.1 Full field list (all SiteSettings fields with owner)

Every SiteSettings field is classified by `classify_site_settings_field()` in `apps/siteconfig/domain_ownership.py`. Exact owners: see `EXACT_FIELD_OWNERS` (30+ fields). Prefix rules: see `PREFIX_FIELD_OWNERS` (e.g. theme_*, brand_*, footer_* → brand_experience; grade_*, delegation_*, finance_* → policies_rules; report_* → reports; sms_*, whatsapp_* → marketplace_integrations; default_dashboard_*, portal_* → runtime_blueprints; country, region, ministry, grading_*, locale_* → global_registries; preview_* → preview_platform; plan_*, billing_* → plans_entitlements; document_*, signature_* → documents; design_*, layout_* → design_studio). Any field not matched is `metadata_governance`. Run `python scripts/generate_platform_inventory.py` for current field list and owner counts.

---

## 3. Per-classification actions

- **platform default only:** Keep in SiteSettings as platform singleton; no tenant-facing read.
- **brand/experience:** Move ownership to `brand_experience`; resolve via runtime/branding resolver.
- **runtime/blueprint:** Resolve via runtime/blueprint resolver; no direct get_solo() in tenant code.
- **policy/rules:** Resolve via policies resolver / runtime.
- **plans/entitlements:** Resolve via plans_entitlements; runtime consumption.
- **registries/localization:** Resolve via global_registries / runtime.
- **integrations/marketplace:** Move to marketplace/integration config; no secrets in SiteSettings in tenant path.
- **metadata governance:** Move to metadata app.
- **delete/deprecate:** Remove or stop reading in tenant paths.

---

## 4. Completion criteria (§2.1 gate)

- [x] All tenant-facing code uses `get_effective_site_settings(request=..., school=...)` or equivalent runtime path only. (Verified: lint_tenant_settings --check-get-solo-only pass; get_solo only in siteconfig definition, platform_runtime/helpers (internal), allowlisted management; tests use get_platform_site_settings_record(create=True) or get_effective_site_settings only.)
- [x] No new tenant-facing `SiteSettings.get_solo()` (enforced by lint_tenant_settings.py in pre_deploy_gate.sh).
- [ ] SiteSettings contains only safe platform defaults; behavioral fields owned by bounded contexts. (Shrink plan in SITECONFIG_OWNERSHIP_MIGRATION Phase B; incremental migration.)
- [x] Bounded consoles exist for each owner; legacy siteconfig admin trimmed. (Phase B: System config console at siteconfig:console_domains_hub; control plane nav; manager shell; domains link to Studio OS + feature control.)

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1.*
