# Domain ownership (§2.1)

**Purpose:** Single reference for SiteSettings field ownership and target bounded contexts. Used by §2.1 (move ownership out of siteconfig), `site_settings_usage_inventory.md`, and CI (`lint_tenant_settings`, `lint_siteconfig_legacy_imports`).

**Phase 5 / §2.1:** Repository gate **MET** — classification lives in code; tenant reads use runtime resolvers only; aggregated verification: `python scripts/verify_phase_5_siteconfig.py` (also in `pre_deploy_gate.sh`).

**Source of truth (code):** `apps/siteconfig/domain_ownership.py` — `classify_site_settings_field()`, `EXACT_FIELD_OWNERS`, `PREFIX_FIELD_OWNERS`, `OWNERSHIP_DOMAINS`.

**Typed column registry (Batch 14+):** `apps/siteconfig/domain_ownership_storage.py` — every `EXACT_FIELD_OWNERS` key is either a `RuntimeDefaults` first-class column (`RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES`), an entry in `VIRTUAL_ONLY_EXACT_FIELDS`, or row metadata (`updated_at` / `delete`). Verified by `scripts/verify_domain_ownership_exact_storage.py` (bundled in `verify_phase_5_siteconfig.py`).

---

## 1. Ownership domains

Every SiteSettings field is classified into one of:

| Domain | Target bounded context / app |
|--------|------------------------------|
| safe_platform_default | Platform singleton only; no tenant-facing read |
| brand_experience | brand_experience, platform_runtime (resolver) |
| runtime_blueprints | platform_runtime, packages |
| policies_rules | policies, platform_runtime (get_effective_flags) |
| plans_entitlements | plans_entitlements |
| global_registries | global_registries |
| marketplace_integrations | marketplace, integrations |
| reports | reports |
| documents | documents |
| design_studio | design_studio |
| preview_platform | preview_platform |
| metadata_governance | metadata |
| delete | Deprecate / stop reading in tenant paths |

---

## 2. Field classification

- **Exact owners:** See `EXACT_FIELD_OWNERS` in `apps/siteconfig/domain_ownership.py` (e.g. `site_name`, `theme_pack`, `backend_feature_flags`, `cache_rankings_interval_minutes` → brand_experience, policies_rules, safe_platform_default).
- **Prefix rules:** See `PREFIX_FIELD_OWNERS` (e.g. `theme_*`, `report_*`, `finance_*` → brand_experience, reports, policies_rules).
- **Run:** `python scripts/generate_platform_inventory.py` for current field list and owner counts.

---

## 3. Resolver path (tenant-facing reads)

- Tenant code must **not** call `SiteSettings.get_solo()` or `SiteSettings.load()`.
- Use `get_effective_site_settings(request=..., school=...)` or `get_cached_site_settings(school=...)` (automation/tasks) from `apps.platform_runtime.helpers` and `apps.automation.helpers`.
- CI: `scripts/lint_tenant_settings.py --check-get-solo-only` flags `get_solo()` and `load()` in tenant apps.

---

## 4. Legacy path deletion

Legacy paths (deprecated accessors, re-exports) are **deleted per-migration** after replacement is live and verified. See `docs/SITECONFIG_OWNERSHIP_MIGRATION.md` and `docs/SITECONFIG_OWNED_MODELS.md` for model→app targets and migration order.

**PATH [§6.1](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) (siteconfig depth):** **III.2** legacy URL inventory and redirect discipline — `docs/LEGACY_PATH_INVENTORY.md`. **III.3** bounded consoles (Control Studio / Studio OS entry points replacing sprawling siteconfig admin) — `docs/BOUNDED_CONSOLES_INVENTORY.md`.

**§2.4 retained raw SQL (platform hygiene):** Six repository files only — `docs/raw_sql_audit.md` §1, `scripts/allowlists/raw_sql_allowlist.json`, `scripts/lint_raw_sql_usage.py`, `docs/raw_sql_replacement_targets.md`.

---

## 5. Next incremental (Step 4 — move ownership)

- **Done (this run):** `cache_rankings_interval_minutes` moved to `RuntimeDefaults` as first-class column (migration 0004). Resolver `_build_platform_site_settings_base` uses it when set; `sync_from_site_settings` / `backfill_runtime_defaults` backfill from SiteSettings. evals/caching continues to read via `get_effective_site_settings` (unchanged).
- **Done (2026-03-26):** `public_brand_primary_color` / `public_brand_accent_color` promoted to first-class `RuntimeDefaults` columns (migration `0010`); payload backfill + strip; `SiteSettings.__getattr__` prefers typed columns over payload; marketing context processor reads columns first.
- **Done (2026-03-26):** `meta_description` / `branded_domain` first-class (`0011`); `tagline` / `school_code` first-class (`0012`); same strip/column-win semantics; `verify_phase_5_siteconfig.py` asserts migration artifacts through `0012`.
- **Done (2026-03-26):** `company_name` / `company_email` first-class (`0013`) from automatic suggestion pass (`suggest_next_runtime_defaults_fields`); same strip/column-win semantics.
- **Done (2026-03-26):** Larger batch first-class (`0014`): `company_phone`, `company_address`, `company_slug`, `country`, `region`, `ministry_registration_code` with payload-strip backfill and column-win behavior.
- **Done (2026-03-26):** Registry strings first-class (`0015`): `ministry`, `default_region`, `default_grading_scale` with payload-strip backfill and column-win behavior.
- **Done (2026-03-26):** Runtime blueprint defaults first-class (`0016`): `admission_number_mode`, `admission_number_pattern`, `admission_number_strategy`, `admission_number_template`, and `admin_portal_stats_config` with payload-strip backfill and column-win behavior.
- **Done (2026-03-26):** Mixed brand/runtime dashboard defaults first-class (`0017`): `accent_color`, `danger_color`, `custom_css`, `admin_use_site_primary`, `default_sidebar_collapsed`, `default_dashboard_view`, `default_refresh_rate`, `default_widgets_per_role` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Portal feed batch first-class (`0018`, **5 fields**): `portal_announcements`, `portal_quick_actions`, `portal_recent_grades`, `portal_upcoming_assessments`, `top_students_default_limit` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Brand palette/social batch first-class (`0019`, **5 fields**): `site_name`, `primary_color`, `success_color`, `warning_color`, `social_links` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Portal/theme policy batch first-class (`0020`, **5 fields**): `use_dark_mode`, `use_secondary_font_for_headings`, `default_portal_role_dual_role`, `enable_parent_portal`, `enable_teacher_portal` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Theme-surface batch first-class (`0021`, **5 fields**): `backend_console_theme`, `header_bg_color`, `footer_bg_color`, `theme_brightness`, `theme_harmony` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Policy/runtime toggles batch first-class (`0022`, **5 fields**): `grade_approval_enabled`, `grade_approval_auto_validate`, `enable_practical_assessment`, `enable_concurrent_mark_uploads`, `enable_offline_mode` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Reports/theme-pack/maintenance batch first-class (`0023`, **10 fields**): `maintenance_mode`, `theme_pack`, `admin_theme_pack`, `teacher_theme_pack`, `parent_theme_pack`, `default_term_report_style`, `default_annual_report_style`, `default_report_preview_type`, `enable_reports_pdf`, `reports_require_approved_grades_before_publish` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Policy/report/reminder batch first-class (`0024`, **5 fields**): `require_mfa_all_staff`, `use_promotion_rule_for_pass`, `notify_parent_welcome_email`, `reports_use_approved_grades_only`, `requests_reminder_interval_hours` with payload-strip backfill and dedicated column-wins tests.
- **Done (2026-03-26):** Policy maps/compliance/referral batch first-class (`0025`, **7 fields**): `backend_feature_flags`, `portal_features`, `notification_channels`, `require_mfa_roles`, `offline_sync_conflict_resolution`, `compliance_profile_id`, `referral_bonus_amount` with payload-strip backfill and dedicated column-wins tests.
- **Next concrete move:** Continue with automatic shortlist from `domain_ownership` for remaining keys; keep behavior-sensitive fields in dedicated slices with explicit contract tests and no PGB FK/media duplication.
- **UX gravity (2026-03-26):** Control plane outcome registry + sidebar admin bridges now foreground **bounded-context** changelists (`PlatformGlobalBranding`, `PlatformPhaseBDomainSnapshot`, integrations, policy compatibility, country registry) beside siteconfig consoles — operators should land on owner apps first; siteconfig remains coordination for legacy save/sync, not the only entry point.
- **Inventory:** Keep `site_settings_usage_inventory.md` and `apps/siteconfig/domain_ownership.py` in sync when adding or reclassifying fields.
- **Rule:** No new `get_solo()`/`load()` in tenant code (CI); ownership move is additive (new column + resolver) then subtractive (stop reading old) per field.

---

## 6. §12 gate satisfaction (siteconfig materially decomposed / SiteSettings not tenant-behavior truth)

**When are these two gates MET?**

- **siteconfig materially decomposed:** (a) Every SiteSettings field classified to an ownership domain (domain_ownership.py + this doc). (b) Bounded-context surfaces exist (platform_runtime, brand_experience, policies, etc.). (c) No tenant-facing code uses `SiteSettings.get_solo()` or `.load()` — enforced by `lint_tenant_settings --check-get-solo-only`. (d) `get_effective_site_settings(request=..., school=...)` is the only tenant-facing API for site settings; it is runtime-first (RuntimeDefaults then SiteSettings). (e) `lint_siteconfig_legacy_imports` blocks new direct imports from legacy siteconfig domain wrappers.
- **SiteSettings not tenant-behavior truth:** Tenant-behavior *truth* is the output of `get_effective_site_settings` (runtime-first). SiteSettings is the legacy data source used by the resolver when RuntimeDefaults is not populated; it is not the authority for tenant behavior. Verification: same lints + runtime_precedence.md + test_runtime_contract.

**Verification:** Run `python scripts/verify_phase_5_siteconfig.py`, `lint_tenant_settings --check-get-solo-only`, and `lint_siteconfig_legacy_imports`; all must pass. See BACKLOG_AND_DEFERRED_CLOSURE §6.3 and RUNMYCAMPUS §12.1.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.1.*
