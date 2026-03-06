# Policy injection

Where Policy Registry and tenant context are injected (middleware, context processors, services). Use these instead of reading `school.settings` / `school.features` directly in business logic.

**Verification (Phase 5):** See `docs/architecture/section_23_injection_verification.md` for a layer-by-layer table (23.1–23.7) with file/function references.

## Middleware

- **apps.tenancy.middleware.TenantContextMiddleware**  
  Injects `request.tenant_ctx` (TenantContext: tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host). Does not call `get_effective_policy`; it only attaches the raw context. Must run after tenant/school is set (e.g. after TenantMiddleware or TenantSchemaSchoolBridgeMiddleware).

## Context processors

- **apps.policies.context_processors.tenant_policy_context**  
  Adds to every template:
  - `tenant_ctx`: from `request.tenant_ctx`
  - `global_env`: from `get_effective_policy(request.school, user=request.user)` (merged platform + region + tenant policy).  
  Templates and views should use `global_env` (and optional `tenant_ctx`) instead of reading `school.settings` or `school.features` directly.

## Resolver (single read path for school.settings/features)

- **apps.policies.resolver.get_effective_policy(school, user=None, capability=None)**  
  The only place that should read `school.settings` and `school.features` to build the merged policy. Returns a dict: terminology, grading, workflows, features, **admissions**, **finance**, **attendance**, **communication**, rtl, default_language, grading_scale, education_dna_preset, plus pass-through keys (report_labels, education_profile_code, payment_gateways, labels_map, education_profile, security_weights, security_grace_period_days).  
  Modules must use `get_effective_policy(school)` (or the registry) for behavior; they must not read `school.settings`/`school.features` in business logic.  
  **Finance (10.3):** `policy["finance"]` — invoice_timing, fee_templates, late_fee_rules (defaults: {}).  
  **Attendance (10.4):** `policy["attendance"]` — statuses, lateness_rules, escalation (defaults: []/{}).  
  **Communication (10.5):** `policy["communication"]` — channel_order, fallback_order (defaults: []). Blueprint/policy_snapshot can override; merge from bundle when POLICY_USE_BUNDLES.  
  **HR/Staff (10.6):** `policy["hr_staff"]` — recruitment, onboarding, certification_tracking, review_cycles, leave_approvals, substitute_workflows (defaults: {}).  
  **Operational identity (21.4):** `policy["operational_identity"]` — default_workflow_slug, default_dashboard_slug, comms_defaults, fee_pack_defaults.

## Registry (request-scoped)

- **apps.policies.registry.get_tenant_blueprint(request)**  
  Returns `get_effective_policy(tenant)` for the tenant/school attached to the request. Used when you have a request and need the full policy dict.

- **apps.policies.registry.get_policy_for_request(request)**  
  Wrapper that returns policy for the request’s tenant; used by code that has only request.

## Feature gate

- **apps.schools.models.is_feature_enabled(school, capability)**  
  Use for feature-flag checks. Backed by merged features (and school model); do not read `school.features` directly in modules.

## Services that use policy (read-only)

These call `get_effective_policy(school)` and use the returned dict; they do not read `school.settings`/`school.features`:

- Reports: `apps.reports.services` (report_labels, education_profile_code, report_labels overrides).
- Finance gateways: `apps.finance.gateways.registry` (payment_gateways).
- Accounts: `apps.accounts.views` (default_language), `apps.accounts.security_health` (security_weights, security_grace_period_days).
- Branding: `apps.siteconfig.brand_registry` (labels_map, education_profile.labels_map).

## Admissions module (Phase 1 refactor)

Policy keys consumed: **admissions** (admission_number_mode, admission_number_strategy, admission_number_template, admission_number_pattern, school_code), **terminology** (admission_number_label).

- **Resolver:** `get_effective_policy(school)` returns `out["admissions"]` (from school.settings["admissions"] or backfill from SiteSettings). `out["terminology"]["admission_number_label"]` defaults to "Admission number".
- **Views:** `portal.views.link_child`, `link_child_wizard` pass `policy=get_tenant_blueprint(request)` into `LinkChildForm(..., policy=policy)`. `portal.views_onboarding.student_onboarding_wizard` passes `policy=get_tenant_blueprint(request)` into `StudentOnboardingForm(..., policy=policy)`.
- **Forms:** `LinkChildForm` uses policy for help_text (school_code), label (terminology.admission_number_label). `StudentOnboardingForm` uses policy["admissions"] for mode and pattern in `clean_admission_number`; fallback to SiteSettings when policy not passed.
- **Services / models:** `people.StudentProfile._get_admissions_policy(school)` returns admissions dict from `get_effective_policy(school)` or SiteSettings fallback. `generate_admission_number(..., school=...)`, `save()`, and `clean()` use this; no direct SiteSettings read in business logic.

## Gradebook / evals (Phase 1 refactor — policy-only)

Policy keys consumed: **grading** (grading_scale), **grade_approval** (grade_post_roles, grade_approval_roles, grade_approval_deadline_days, grade_approval_deadline_note, grade_approval_auto_validate, grade_approval_enabled), **features** (for marksheet/backend flags when school is set).

- **Resolver:** `get_effective_policy(school)` returns `grading` (including grading_scale from region/school.settings) and **grade_approval** (backfilled from SiteSettings when not in school.settings). Bundle snapshot merge includes `grade_approval`. No direct SiteSettings read in evals business logic for approval/grading config.
- **Evals approval:** `apps.evals.approval.get_grade_approval_policy(school)` returns the grade_approval dict (policy when school set, else SiteSettings fallback). `grade_post_roles(school=None)`, `grade_approver_roles(school=None)`, `user_can_finalize_submission(user, school=None)` all take optional `school` and use policy when provided. `create_grade_approval_request(...)` derives school from teacher/classroom and uses policy for deadline_days and auto_validate.
- **Evals views:** Grade approval list/detail and marksheet entry view pass `request.school` into approval helpers; deadline_note and final_roles come from `get_grade_approval_policy(school)`. When `request.school` is set, marksheet view uses `get_effective_policy(school)` for `grade_approval_enabled` and `features` (flags) instead of SiteSettings.
- **Reports:** Unchanged; already use policy for grading_scale and report labels (see below).

## Gradebook / reports (grading scale, labels)

Policy keys consumed: **grading_scale**, **default_language**, **report_labels** (and profile-derived overrides), **education_profile_code**.

- **Resolver:** `get_effective_policy(school)` returns `grading_scale`, `default_language`, and pass-through `report_labels` / `education_profile_code` from school.settings or region-derived defaults.
- **Reports:** `apps.reports.services.resolve_report_labels(school, ...)` uses policy (and education profile) only for labels; no CMR or country branches. `_region_display_context(school, ...)` uses `get_effective_policy(school)` for `grading_scale` when school is set.
- **Context processor:** `apps.siteconfig.context_processors.region_settings`: when `request.school` is set, `grading_scale` and `default_language` come from `policy` only (no direct `region.grading_scale` / `region.default_language`).
- **Siteconfig view:** Grading/language settings view uses `get_effective_policy(school)` for current grading and language display instead of reading `school.settings` and `region` directly for behavior.

## Per-tenant policy caching (optional)

- Set **POLICY_CACHE_TTL** (seconds) in settings to enable caching of the full policy dict per school. When set, `get_effective_policy(school)` (with `capability=None`) is cached under key `policy:{school_id}`. Use Redis or another backend for production scale.
- Call **invalidate_policy_cache(school)** after updating `school.settings` or `school.features` (e.g. from a `post_save` signal on School) so the next request gets a fresh policy.

## Form policy (Section 23.4 / 24.8)

- **apps.policies.form_policy**  
  Policy-driven forms: field visibility, required/optional, labels, picker options (choices_key), document_required. Use `apply_form_policy(form, form_name, policy, school=...)` in form `__init__` after `super().__init__()`. Form schemas live in `policy["forms"][form_name]` (merged from platform defaults, bundle, and school.settings["forms"]). See phase3_metadata_driven_forms_24_8_23_4.md.

## Feature flags and OpenFeature (Section 31.7)

- **Current:** Use **`is_feature_enabled(school, code)`** and **`can(school, capability)`** (`apps.schools.models`) for all entitlement/feature checks. Backed by merged policy (plan, addons, school.features, FeatureToggleState).
- **OpenFeature:** The platform can later adopt [OpenFeature](https://openfeature.dev) as a provider layer: an OpenFeature provider would call the same resolution as `is_feature_enabled(school, evaluation_context.get_value("school_id"), flag_key)` so runtime toggles (e.g. launch darkly) can override without code deploy. Until then, single read path remains `is_feature_enabled` / `can()`.
- **Refinement:** See `docs/architecture/REFINEMENT_AND_IMPLEMENTATION_ORDER.md` (Priority 3).

## Excluded (by design)

- **Writers / source of truth:** `apps.policies.resolver` (reads school.settings/features to build policy), `apps.siteconfig.tenant_config`, `system_morph`, signup_views, siteconfig views that **write** to school.settings/features.
- **Canonical model:** `apps.schools.models` (e.g. `_has_feature_fallback`, used by `is_feature_enabled`).
- **Tests** that assert on `school.settings` or `school.has_feature` for model/behavior.
