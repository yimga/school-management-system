# Powerhouse Phase Doc + Audit Rules + Phase A + B — Summary (save token)

## Done (this session)

- **Phase Doc:** Main roadmap `global_powerhouse_roadmap_9eab655a.plan.md` updated with Follow-Up and Status, Auditor Mode and Zero-Gaps Assurance (prompts, checklists), cross-ref in Summary Checklist.
- **Phase Audit Rules:** `.cursorrules` — added AUDIT & QUALITY LAWS (tenant leak, HTMX, i18n, offline sync, usage limit).
- **Phase A:** `is_feature_enabled()` uses `get_tenant_modules(school)`; middleware sets `timezone.activate(school.timezone)`; context_processors expose `TENANT_LOCALE` via `use_local_settings()`. Sidebar already filters by `has_feature()`.
- **Phase B:** api_create_school accepts `education_system_ids`, `province_id`; api_provinces + api_education_profiles(province_id); provisioning creates TenantSystem rows and calls `sync_tenant_modules_to_school_features`; DynamicThemeMiddleware; wizard: province dropdown, education_system_ids multi-select, theme_choice in payload.

## Optional items (done)

- **Phase A:** Signal on TenantSystem post_save/post_delete calls `sync_tenant_modules_to_school_features(school)` (siteconfig/signals.py).
- **Phase B:** Wizard progress text "Step X of 4"; smart default (select Trade/Vocational profile in multi-select when chosen as primary).
- **Phase C:** `report_template_family` from profile.config written to school.settings in provisioning (tasks.py); `get_report_template_family_for_school` already in tenant_config.
- **Phase F:** BrandSettings already in codebase (migration 0098); duplicate definition removed.
- **Phase G:** `test_has_feature_respects_tenant_systems` in schools/tests/test_tenant_isolation_and_provisioning.py.
- **Phase H:** New schools get `is_approved=False` when `ENABLE_SCHOOL_APPROVAL_WORKFLOW=1`; Super Dashboard shows "Pending approval" card and Approve button; `api_approve_school`; Last activity column (updated_at) in schools table.

## Key paths

- Roadmap: `.cursor/plans/global_powerhouse_roadmap_9eab655a.plan.md`
- Plan update / phases: `.cursor/plans/plan_update_follow-up_and_auditor_926a22f2.plan.md`
- tenant_config: `apps/siteconfig/tenant_config.py` (get_tenant_modules, use_local_settings, sync_tenant_modules_to_school_features)
- Wizard: `apps/schools/super_views.py`, `apps/schools/tasks.py`, `templates/schools/super_create_school_wizard.html`
