# Full Plan Verification Audit

This document verifies implementation status against **plan_update_follow-up_and_auditor_926a22f2.plan.md** and **global_powerhouse_roadmap_9eab655a.plan.md**. Everything in those plans has been checked; gaps are listed at the end.

**When you complete a phase:** Update the **Phase status table** in the roadmap (Follow-Up and Status) and refresh this audit (tick any newly done items). See roadmap "Definition of Done" and `docs/DEPLOY_CHECKLIST.md` (Pre-merge checklist).

---

## 1. Plan Update (Follow-Up and Auditor plan)

| Item | Requirement | Status |
|------|-------------|--------|
| 1.1 | Add Follow-Up and Status to roadmap | ✅ In roadmap: "Follow-Up and Status (implementation progress)" with Phase I and A–H summary |
| 1.2 | Auditor Mode and Zero-Gaps Assurance section | ✅ In roadmap: "Auditor Mode and Zero-Gaps Assurance" with 2.1–2.6 |
| 1.3 | Summary Checklist cross-reference (Auditor Mode) | ✅ "Before considering a task done: Run the Auditor Mode checks..." in Summary Checklist |
| 1.4 | Optional: Future and Expansion Items (3.1–3.12+) | ✅ In roadmap: "Future and Expansion Items" catalog |
| 1.5 | .cursorrules AUDIT & QUALITY LAWS | ✅ Present: Tenant Leak, HTMX Partial, Localization, Offline Sync, Usage Limit, Sentry |

---

## 2. Phase I (Scale)

| Item | Requirement | Status |
|------|-------------|--------|
| 2.1 | Gap analysis doc | ✅ docs/PHASE_I_SCALE_GAP_ANALYSIS.md, PHASE_I_MULTI_REGION_AND_DEPLOY.md |
| 2.2 | phase_i_gap_analysis management command | ✅ apps/schools/management/commands/phase_i_gap_analysis.py |
| 2.3 | db_health_check command | ✅ apps/observability/management/commands/db_health_check.py |
| 2.4 | run_health_check.sh in predeploy | ✅ scripts/release/run_health_check.sh |
| 2.5 | Optional django-tenants, migrate_schools_to_tenants | ✅ Referenced in docs; conditional USE_DJANGO_TENANTS=1 |

---

## 3. Phase A (Foundation)

| Item | Requirement | Status |
|------|-------------|--------|
| 3.1 | Province model | ✅ apps/siteconfig/models.py — Province |
| 3.2 | TenantSystem, SystemFeature models | ✅ apps/siteconfig/models.py |
| 3.3 | get_tenant_modules(school) | ✅ apps/siteconfig/tenant_config.py |
| 3.4 | get_tenant_locale(request, school) / useLocalSettings | ✅ tenant_config.py; used in middleware, reports, format_currency |
| 3.5 | Optional sync getTenantModules → School.features | ✅ sync_tenant_modules_to_school_features; signal on TenantSystem change |
| 3.6 | RLS/timezone in middleware | ✅ TenantMiddleware sets timezone from get_tenant_locale(school) |
| 3.7 | Backfill: one TenantSystems row per school | ✅ Migration 0095_backfill_tenant_systems.py |

---

## 4. Phase B (Onboarding)

| Item | Requirement | Status |
|------|-------------|--------|
| 4.1 | Wizard: identity, region (country, province, city) | ✅ create_school_wizard, api_create_school |
| 4.2 | education_system_ids (multi), Plan & addons, theme_choice | ✅ In wizard/provisioning |
| 4.3 | Branding, Domain; api_provinces, api_education_profiles | ✅ super_views / APIs |
| 4.4 | Plan Configurator placeholder, estimated price | ✅ Referenced in roadmap status |
| 4.5 | DynamicThemeMiddleware, theme in admin | ✅ Implemented |
| 4.6 | Tenant Provisioning Engine on finalize | ✅ apps/schools/tasks.py provisioning |

---

## 5. Phase C (Metadata, grading & gradebook)

| Item | Requirement | Status |
|------|-------------|--------|
| 5.1 | get_scale_for_school, get_grading_schema_for_school | ✅ apps/evals/grading.py; tenant_config |
| 5.2 | get_custom_field_definitions, get_report_template_family_for_school | ✅ tenant_config.py |
| 5.3 | format_currency / date from tenant locale | ✅ region_format templatetags; get_tenant_locale |
| 5.4 | Student/Staff custom_attributes (JSONB) + admin | ✅ people/models.py custom_attributes; people/admin |
| 5.5 | Grading entry points doc | ✅ docs/GRADING_ENTRY_POINTS.md |
| 5.6 | Gradebook sticky header | ✅ templates/teacher/marks_list.html gradebook-thead-sticky; design-system-unified.css |
| 5.7 | Optional ReportTemplate/report_template_family in config | ✅ get_report_template_family_for_school used in reports |

---

## 6. Phase D (Feature gate & plan)

| Item | Requirement | Status |
|------|-------------|--------|
| 6.1 | Plan model (included_features, etc.) | ✅ apps/siteconfig/models.py Plan |
| 6.2 | School.plan_id, addons | ✅ schools/models.py |
| 6.3 | is_feature_enabled(school, code) | ✅ schools/models.py; plan + addons + School.features |
| 6.4 | FeatureGatekeeperMiddleware, FEATURE_GATE_PATH_MAP | ✅ schools/middleware.py; in MIDDLEWARE |
| 6.5 | UsageLimitMiddleware (on by default) | ✅ middleware.py; DISABLE_USAGE_LIMIT_MIDDLEWARE=1 to disable |
| 6.6 | 403 or Upgrade Modal | ✅ Middleware returns 403; Upgrade Modal placeholder doc |
| 6.7 | Upgrade Modal placeholder template | ⚠️ **Was missing** — see fix below |
| 6.8 | Template tag for feature check in UI | ✅ siteconfig/templatetags/feature_control.py feature_enabled |
| 6.9 | Tests (plan, is_feature_enabled, middleware) | ✅ apps/schools/tests/test_plan_and_feature_gate.py |

---

## 7. Phase E (Monetization & billing UX)

| Item | Requirement | Status |
|------|-------------|--------|
| 7.1 | billing_type, waiver_note on School | ✅ migration 0006 |
| 7.2 | Unfold "Waive subscription" action | ✅ School admin approve/deny; sets COMPLIMENTARY, BillingWaiverAuditLog |
| 7.3 | Plan Configurator API (plans, addons, country_multiplier) | ✅ GET /super/api/plans-configurator/; docs/PLAN_CONFIGURATOR_API.md |
| 7.4 | RevenueSnapshot, calculate_monthly_stats | ✅ siteconfig/models, billing_services.py, task, management command |
| 7.5 | Financial Bento (MRR, waived, heatmap, donut) | ✅ super_dashboard: total_mrr, total_waived, waiver_%, revenue_by_country, billing_model_breakdown |
| 7.6 | WaiverRequest (proof, status, approve/deny queue) | ✅ models, admin actions approve_waiver_requests, deny_waiver_requests |
| 7.7 | School request waiver (accounts:request_waiver) | ✅ accounts/views request_waiver, template, URL |
| 7.8 | BillingWaiverAuditLog | ✅ model, admin, created on waiver approval |

---

## 8. Phase F (Design Studio & portal)

| Item | Requirement | Status |
|------|-------------|--------|
| 8.1 | DesignTemplate model | ✅ siteconfig/models.py |
| 8.2 | BrandSettings model | ✅ siteconfig/models.py |
| 8.3 | Tenant media prefix tenants/{school_id}/ | ✅ _tenant_upload_to in siteconfig/models; used for waiver_requests etc. |
| 8.4 | Sync Center (list conflicts, resolve) | ✅ views_sync_center, sync_center.html, sync_center_resolve |
| 8.5 | Parent dashboard Bento-style | ✅ Referenced in roadmap status as "Bento elements as added" |

---

## 9. Phase G (Offline & sync)

| Item | Requirement | Status |
|------|-------------|--------|
| 9.1 | SyncConflict model | ✅ siteconfig/models.py; migration 0097 |
| 9.2 | DeltaSyncEngine / sync_services create SyncConflict | ✅ api/sync_services.py creates SyncConflict on conflict |
| 9.3 | Sync Center UI (side-by-side, resolve) | ✅ sync_center.html; server/client/discard actions |
| 9.4 | Emergency Sync Repair (super admin) | ✅ super_views sync_repair by tenant_id; list conflicts; Force Overwrite (transaction.atomic) |
| 9.5 | Integration tests (conflict, tenant isolation) | ✅ api/tests/test_delta_sync_phase_g.py |

---

## 10. Phase H (Super Admin & polish)

| Item | Requirement | Status |
|------|-------------|--------|
| 10.1 | Super Admin dashboard (schools, systems) | ✅ super_dashboard with schools, selected_systems, Financial Bento |
| 10.2 | Financial Bento when E in place | ✅ total_mrr, total_waived, waiver_%, revenue_by_country, billing_model_breakdown |
| 10.3 | Registry link | ✅ super_dashboard context registry_url |
| 10.4 | Unfold dashboard_callback | ✅ config UNFOLD DASHBOARD_CALLBACK → unfold_dashboard.dashboard_callback |
| 10.5 | Visual standards in .cursorrules | ✅ Bento, Cmd+K, empty states, Unfold, feature gate |

---

## 11. Section 7 — Nuance Engine (Multi-tenant extensibility)

| Item | Requirement | Status |
|------|-------------|--------|
| 11.1 | CustomNuance model (school, hook_point, logic_data, human_description, is_active) | ✅ siteconfig/models.py |
| 11.2 | PendingNuance (proposed_logic, status, reviewed_by, human-in-the-loop) | ✅ siteconfig/models.py |
| 11.3 | Migration | ✅ 0101_nuance_engine_custom_pending_nuance.py |
| 11.4 | Hook registry (allowed keys per hook) | ✅ nuance_engine.HOOK_REGISTRY |
| 11.5 | apply_nuance(school, hook_point, context) — scrub, timeout, read-only | ✅ nuance_engine.py |
| 11.6 | verify_nuance_safety(logic_data, test_contexts) | ✅ nuance_engine.py |
| 11.7 | nuance_engine_enabled(school) — plan gating | ✅ nuance_engine.py |
| 11.8 | Admin: CustomNuance, PendingNuance; Approve action (safety then promote) | ✅ siteconfig/admin.py |
| 11.9 | Plan gating on save (warning if not enabled) | ✅ CustomNuanceAdmin.save_model |
| 11.10 | docs/NUANCE_ENGINE.md | ✅ Hook points, safety, plan gating, call site |
| 11.11 | One hook call site (fee_discount) | ✅ finance/services.py _apply_fee_discount_nuance in create_fee_invoices |

---

## 12. Section 8 — Industry Interoperability & Integrations

| Item | Requirement | Status |
|------|-------------|--------|
| 12.S8.1 | ServiceIntegration, WebhookSubscription models (siteconfig) | ✅ models; migration 0102 |
| 12.S8.2 | School.is_frozen, frozen_reason | ✅ schools/models; migration 0011 |
| 12.S8.3 | Caddy ask endpoint GET /api/caddy-check/?domain= | ✅ section8_views.verify_caddy_domain; custom_domain only if verified |
| 12.S8.4 | Global login discovery /discover/ (email → school redirect) | ✅ section8_views.global_login_discovery; template global_login_discovery.html |
| 12.S8.5 | LTI placeholder /lti/launch/<tool_id>/ (501), /lti/jwks.json | ✅ section8_views; URLs in config/urls.py |
| 12.S8.6 | Frozen account page /account-frozen/, TenantFreezeMiddleware | ✅ frozen_account view, frozen_account.html, FROZEN_EXEMPT_PREFIXES, staff bypass |
| 12.S8.7 | Health utils (PG table sizes, top tables, schema stats) | ✅ apps/schools/health_utils.py |
| 12.S8.8 | Super dashboard Health block (resource hogs, top 10 tables) | ✅ super_views context; super_dashboard.html |
| 12.S8.9 | Admin: ServiceIntegration, WebhookSubscription | ✅ siteconfig/admin.py |
| 12.S8.10 | SECURE_REDIRECT_EXEMPT for caddy-check, discover, account-frozen | ✅ config/settings.py |

Gaps/tests: See docs/GAPS_SECTION8_AND_TAGGING.md (no automated tests for Section 8 yet).

---

## 13. Information Tagging (zero hardcoding)

| Item | Requirement | Status |
|------|-------------|--------|
| 13.IT.1 | InformationTag model (school, name, category, color_hex, is_private, is_critical) | ✅ people/models.py; migration 0029 |
| 13.IT.2 | StudentProfile.tags M2M to InformationTag | ✅ people/models.py |
| 13.IT.3 | Nuance: student_tags in fee_discount context, "in" operator | ✅ nuance_engine HOOK_REGISTRY + _safe_eval "in"; finance/services _apply_fee_discount_nuance |
| 13.IT.4 | Tag Manager UI (list/create/edit), settings.manage | ✅ siteconfig/views_tag_manager; tag_manager.html, tag_manager_edit.html; permission_required |
| 13.IT.5 | Student list tags column (pills), is_private visibility | ✅ people/views_backend prefetch tags; backend_student_list.html; can_see_private_tags |
| 13.IT.6 | Admin: StudentProfile tags fieldset, InformationTag admin | ✅ people/admin.py |
| 13.IT.7 | Critical-tag signal → AccessRequest (OTHER), assign to leadership | ✅ people/signals.py on_student_critical_tag_added |
| 13.IT.8 | docs/INFORMATION_TAGGING.md | ✅ |

Gaps/tests: See docs/GAPS_SECTION8_AND_TAGGING.md (no automated tests for tagging yet).

---

## 14. Optional / Cross-cutting

| Item | Requirement | Status |
|------|-------------|--------|
| 14.1 | UsageLimitMiddleware on by default | ✅ In MIDDLEWARE; DISABLE_USAGE_LIMIT_MIDDLEWARE=1 to turn off |
| 14.2 | Request Waiver at accounts:request_waiver | ✅ View, form, template, URL |
| 14.3 | Welcome email (post-provisioning) | ✅ schools/welcome_email.py; triggered from provisioning; siteconfig task send_welcome_email |
| 14.4 | ComplianceRule, ComplianceGuardMiddleware | ✅ apps/compliance; in MIDDLEWARE |
| 14.5 | DEPLOY_CHECKLIST.md | ✅ Pre/post deploy, optional SSL/CI/CD |

---

## 15. Future and Expansion Items (catalog only)

Items 3.1–3.26 are **cataloged** in the roadmap; implementation is when that phase is active. Verified as **present in plan** (not all implemented by design):

- 3.1 Emergency Sync Repair ✅ Implemented (Phase G).
- 3.2 HTMX audits — documented as prompts; no code mandate.
- 3.3 Gradebook expansion — partial (sticky header); full live-edit/weights in phase when active.
- 3.4–3.12, 3.13–3.26 — expansion/future; referenced in roadmap.

---

## Gaps found and fix

1. **Upgrade Modal placeholder (Phase D)**  
   The quick reference and checklist expect `templates/components/upgrade_modal_placeholder.html` for use when a feature is gated; it was missing. **Fix:** Add the placeholder template so UI can include it where a gated feature would show an upgrade message instead of 403 or empty content.

2. **Section 8 & Information Tagging gaps**  
   Tag Manager lacked RBAC; SECURE_REDIRECT_EXEMPT did not include Caddy, discover, account-frozen. **Fix:** Tag Manager now uses `@permission_required("settings.manage")`; SECURE_REDIRECT_EXEMPT updated. Remaining gaps (tests, rate limiting, audit entries) are documented in **docs/GAPS_SECTION8_AND_TAGGING.md**.

---

## Summary

- **Phases I, A, B, C, D, E, F, G, H**, **Section 7 (Nuance Engine)**, **Section 8 (Industry Interoperability)**, and **Information Tagging** are implemented as specified; audit tables 12 and 13 added above.
- **Gaps addressed:** Upgrade Modal placeholder added; Tag Manager RBAC and SECURE_REDIRECT_EXEMPT fixed.
- **Remaining gaps:** See docs/GAPS_SECTION8_AND_TAGGING.md (tests for Section 8 and tagging, optional rate limiting, Caddy IP allowlist).
- **Auditor Mode:** .cursorrules has AUDIT & QUALITY LAWS; roadmap has Auditor Mode section and Summary Checklist line.
- **Docs:** GRADING_ENTRY_POINTS, PHASE_D_E_QUICK_REFERENCE, DEPLOY_CHECKLIST, NUANCE_ENGINE, PLAN_CONFIGURATOR_API, INFORMATION_TAGGING, GAPS_SECTION8_AND_TAGGING, Phase I docs exist.
