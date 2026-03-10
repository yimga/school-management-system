# Global Multi-Tenant Rollout

## Completed in this pass

### Phase 1: Global Geo Foundation
- Added `GlobalGeoCatalog` (`apps/siteconfig/global_catalog.py`) backed by:
  - ISO countries (`pycountry`)
  - Global city index (`geonamescache`)
  - Full timezone list (`pytz.all_timezones`)
- Updated school provisioning wizard to use global country and searchable city selection:
  - `apps/schools/super_views.py`
  - `templates/schools/super_create_school_wizard.html`
  - `apps/schools/super_urls.py`
- Added geo APIs for UI search:
  - `super:api_geo_cities`
  - `super:api_geo_timezones`
- Added global region seed command:
  - `python manage.py seed_global_regions`

### Phase 2: Education Profile Engine
- Added `EducationSystemProfile` model with configurable:
  - academic start month
  - term count and labels
  - grading scale
  - default language/currency/timezone
  - default subject seeds
  - extra config JSON
- Added migration seed profiles for:
  - Global default
  - Cameroon (EN/FR)
  - Uganda
  - Nigeria
  - Kenya
- Updated provisioning task (`apps/schools/tasks.py`) to auto-apply profile defaults.

### Phase 3: De-hardcoded Reporting Labels
- Added profile/tenant-aware report label resolver in `apps/reports/services.py`:
  - `resolve_report_labels(student=..., school=...)`
  - precedence is now: global -> region -> profile -> school overrides.
- Updated report preview flows in `apps/siteconfig/views.py` to use dynamic labels instead of hardcoded Cameroon labels.
- Preserved backward compatibility for single-tenant deployments using `REGION_CODE=CMR`.

### Phase 4: Communication Tenant Ownership + RLS
- Added explicit `school` ownership field to communication models:
  - `Message`, `DirectConversation`, `Announcement`, `AnnouncementAuditLog`,
    `ClassAnnouncement`, `MessageThread`, `ThreadMessage`, `ThreadReadState`,
    `AlertRule`, `ContactRequest`, `ContactRequestAttachment`.
- Added auto-assignment logic in model `save()` methods to infer school from:
  - classroom/department/student links
  - thread/request/announcement parent object
  - user school membership/profile.
- Added migration `apps/communication/migrations/0009_...py`:
  - schema updates
  - legacy data backfill for `school_id`
  - PostgreSQL Row-Level Security policies for communication tenant tables.
- Added tenant-audit guardrails:
  - `apps/siteconfig/tenant_audit.py`
  - command `python manage.py audit_tenant_models --strict`
  - test `apps/siteconfig/tests/test_tenant_audit.py`.

### Phase 5: Feature Registry Data-Backed Starter
- Converted module catalog read path to DB-backed registry in `apps/schools/feature_registry.py`:
  - seeds `FeatureToggleDefinition` rows for `module.*`
  - reads module-market catalog from DB (fallback to static list remains).
- Added tests in `apps/schools/tests/test_feature_registry.py`.

### Phase 6: Global Country Packs
- Added country-pack engine in `apps/siteconfig/education_profile_engine.py`:
  - auto-generates per-country education profiles when explicit packs are missing
  - resolves profile precedence: explicit selection -> country/sub-system -> country/ANY -> global fallback
  - creates `RegionConfig` on demand for valid ISO countries.
- Added global profile seeding command:
  - `python manage.py seed_country_profiles`
- Extended region seed command:
  - `python manage.py seed_global_regions --with-profiles`
- Updated provisioning task (`apps/schools/tasks.py`) to always resolve a valid education profile and persist selected/auto profile code.
- Added tests:
  - `apps/siteconfig/tests/test_education_profile_engine.py`
  - additional provisioning/profile tests in `apps/schools/tests/test_tenant_isolation_and_provisioning.py`.

### Phase 7: Provisioning Wizard Upgrade
- Upgraded super-admin wizard (`templates/schools/super_create_school_wizard.html`) with explicit:
  - `Education template` selector (`Auto by Country and Sub-system` default)
  - live template refresh by country + sub-system.
- Added API endpoint for template options:
  - `super:api_education_profiles`
- Extended create-school API to accept `education_profile_code` and store provisioning mode metadata.
- Added custom-domain workflow metadata to school settings at provisioning start.
- Updated super dashboard table (`templates/schools/super_dashboard.html`) to surface:
  - selected template code (or Auto)
  - custom domain verification status.
- Upgraded Feature Control weather location to global country/city search:
  - new endpoint `siteconfig:feature_control_weather_cities`
  - global city persistence in backend feature flags.

### Phase 8: CI/Release Hardening
- Hardened pre-deploy gate (`scripts/pre_deploy_gate.sh`) to include:
  - `python manage.py audit_tenant_models --strict`
  - targeted global/multi-tenant regression suites
  - startup command sanity checks for `render.yaml` and `Procfile` (`render_start_web.sh`).
- Kept health/readiness routes active:
  - `/health/`, `/ready/`, `/status/`.

### Hardening improvements
- Expanded `RegionConfig.term_count_per_year` from fixed choices to validated range `1..12`.
- Updated region validator command (`validate_regions`) to match new range.
- Expanded regional translation stubs to include more countries/regions.

## Suggested next phases
### Phase 9: Profile Pack Governance
- Add admin workflow for profile pack versioning and approval.
- Add per-tenant override UI for term labels, grading logic, and report template family.

### Phase 10: Country Compliance Packs
- Add country-specific compliance/reporting templates (ministry layouts, transcript variants).
- Link packs to `EducationSystemProfile.config` with versioned template keys.

### Phase 11: Provisioning Automation
- Add asynchronous provisioning status timeline (queued, region seeded, profile applied, domain pending/verified).
- Add DNS/API integration hooks for custom-domain verification updates.

### Immediate deployment note
- If Render logs show:
  - `Running '.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:$PORT'`
  this means Dashboard start command is overriding repo config.
- Set web service start command to:
  - `bash ./scripts/release/render_start_web.sh`
  so Gunicorn uses `config/gunicorn.conf.py` and consistent bind behavior.
