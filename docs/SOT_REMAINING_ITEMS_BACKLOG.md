# SOT remaining open checkboxes — backlog registry

**Authority:** Remaining `- [ ]` in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) after **2026-03-19** reconciliation. Resolved rows are removed from this file (see git history).

**Rule:** Status is one of **NEXT_CODE** | **PRODUCT** | **OPS** | **COMPLIANCE** | **BLOCKED** (external).

**Last sync:** 2026-03-22

---

## Recently closed (evidence only — do not reopen without new scope)

| Item | Evidence |
|------|----------|
| Wave 19–20 POS + inventory | `schoolops` `ops_pos`, migration `0010`, `test_tenant_ops_wave18_pos` |
| Wave 5 competitor packs (structural) | `MigrationProfile`, `test_migration_cloud_phase_a`, `schema_fingerprint.py` |
| Serious Simple (csrf / role / LB) | `lint_csrf_exempt_usage.py` allowlist; `permissions.py` `user_can_access_ops_*`; `test_ops_role_helpers.py`; SLO LB section |
| N16 program | [N16_SOC2_ISO_EXECUTION_PROGRAM.md](N16_SOC2_ISO_EXECUTION_PROGRAM.md) |
| N18 structural | [DEVELOPER_PUBLIC_API.md](DEVELOPER_PUBLIC_API.md) webhooks + OpenAPI |
| N29 methodology | [GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md](GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md#n29-measured-setup-structural-closure) |
| N6 partial | `role_home_engine` + ops RBAC helpers |
| Foundation raw SQL / broad except | §2.4 + lints (SOT checkbox [x]) |
| RESILIENT_EDGE incremental (N5 / long forms) | `critical-read-degraded.js`, `portal_base.html`; timetable + parent widgets; `form-draft-save.js` on support/contact/requests; `test_resilient_edge_wiring.py` |
| Wave 4 POS fiscal increment | `0011_possaleline_tax`, `ops_pos` tax + totals + draft; `test_pos_sales_tax_snapshot_and_gross` |
| Compliance erasure draft | `templates/compliance/erasure_request.html`; `test_erasure_template_wiring.py` |
| N28 deadlines API | `NorthStarUpcomingDeadlinesView`, `merged_upcoming_events_for_api`, `test_north_star_api_views` |
| GAP.5 runtime trace (request id; OTel still open) | `tracing.py`; `runtime_resolver.build_tenant_runtime` + `helpers.get_effective_site_settings`; `structured_logging.request_context_for_log`; gap audit §4/§8 **Partial** |
| Finance form drafts + a11y table headers | `invoice_detail.html`, `cash_office_closure.html`, `generate_fees.html`; `closure_profile_id` in `views_payments`; `test_finance_form_draft_templates.py`; teacher **`timetable.html`** **`scope="col"`** |
| N22 incremental (RTL context contract) | `region_settings` → `is_rtl`; `apps/siteconfig/tests/test_n22_region_settings_rtl.py`; [N22_RTL_AND_REGIONAL_UX.md](N22_RTL_AND_REGIONAL_UX.md) — **full N22 row in SOT still [ ]** |
| BR-12 marketing mega-file split | `marketing_page_definitions.py` (`MARKETING_PAGE_*`, `TOPICAL_LANDING_*`); `marketing_views.py` imports; `test_marketing_validation` |
| Finance drafts increment (access bulk / suspense / payments filter) | `access_bulk.html`, `suspense_queue.html`, `payments.html` + `test_finance_form_draft_templates.py` — umbrella row still **[ ]** |
| Finance drafts + N3 table scope (wave) | `scan_teller_placeholder`, `trial_balance`, `invoices` filter, `reports` (period + request), `requests` inbox; `split_allocation` **`scope="col"`**; `test_finance_form_draft_templates` (growing; **14** tests as of 2026-03-20) |
| N3 finance read-only tables + template drift doc | `expense_vs_budget.html`, `bursar_entries_report.html` **`scope="col"`**; [TEMPLATE_EDITING_CONVENTION.md](TEMPLATE_EDITING_CONVENTION.md); `verify_sot_pillar_evidence` path |
| N3 PDF receipt + i18n context | `finance/receipt.html` table scopes + `lang`; `invoice_receipt` → `render_to_string(..., request=request)`; `test_invoice_receipt_pdf.py` |
| BR-12 super_views command-center extraction | `super_views_constants.py`, `super_views_command_center_data.py`, `test_super_views_command_center_data.py` — **`super_views.py` still large**; umbrella **[ ]** |
| BR-12 constants dedupe | `super_views_catalog`, `super_views_migration`, `super_views_provisioning` import `CONTROL_PLANE_*` from `super_views_constants.py` |
| N23 incremental (governance + receipt a11y) | `docs/N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md`; `CONTENT_AND_TERMINOLOGY_GOVERNANCE.md` §2.7; `templates/finance/receipt.html` (`i18n`, logo `alt`, table `aria-label`); `verify_sot_pillar_evidence` N23 path; **`test_printable_receipt_accessible_logo_and_table_label`** — **full N23 SOT row still `[ ]`** |
| N3 payroll portal tables | `templates/payroll/` employee_payslips, dashboard, employee_leave, run_detail **`scope="col"`**; `test_payroll_template_table_a11y.py` |
| N3 analytics/evals/reports tables | `analytics/deadlines.html` (visually-hidden Actions column); `evals/grade_import_upload_v2.html` validation table **`scope="col"`** + `aria-label`; `reports/term_report.html` subject grid **`scope="col"`** + `aria-label`; `test_n3_misc_table_header_templates.py` (**18** tests: **`test_all_template_th_open_tags_include_scope`** = **all** `templates/**/*.html` **`<th>`** have **`scope`**; + control-plane `super_regions_list`, `super_plans_list`, `super_site_settings_list`, `super_country_multipliers_list`, `super_grading_list`, `super_registries`; `requests/dashboard`; `certification_home` / `certification_session_detail`; `evaluation_grid`; `term_report_cameroon_modern`; `reportcard_style_preview`; `student360/transcript_archive_year`; `teacher/marks_entry`; `observability/platform_incidents`; prior batch: `analytics/dashboard`, annual/Cameroon reports, pay history, grade approvals, report card builder, `super_metadata_catalog`, toggles/plan/migration, `rbac_dashboard`) |
| BR-12 super_views hygiene | Removed unused **`safe_school_timeline_url`** import (was shadowed by local **`_safe_school_timeline_url`**) |
| BR-12 super_views geo API split | **`super_views_geo_api.py`**: **`api_geo_cities`**, **`api_geo_timezones`**, **`api_provinces`**, **`api_education_profiles`**, **`api_system_blueprint`**, **`api_plans_configurator`**; **`super_views`** re-exports; **`test_super_views_geo_api.py`**; **`verify_sot_pillar_evidence`** paths — **`super_views.py`** still large; umbrella **[ ]** |
| BR-12 super_views school API split | **`super_views_school_api.py`**: **`api_school_timeline`**, **`api_approve_school`**, **`school_lifecycle_action`**, **`api_school_policy_bundles`**, **`api_school_policy_bundle_activate`**; **`test_super_views_school_api.py`**; **`verify_sot_pillar_evidence`** |
| BR-12 super_views policy split | **`super_views_policy.py`**: **`super_policy_diff`**, **`super_apply_policy_bundle_to_sandbox`** (+ **`_policy_bundle_impact_preview`**); **`test_super_views_policy.py`** |
| BR-12 super_views trust surface split | **`super_views_trust_surface.py`**: **`super_compliance_overview`**, **`super_trust_center`**, **`super_config_hub_redirect`**, **`super_audit_export`**, **`super_platform_events`**; **`test_super_views_trust_surface.py`**; **`super_platform_events`** tolerates non-numeric **`limit`** (defaults to 100) |
| BR-12 super_views support split | **`super_views_support.py`**: **`super_support_dashboard`**, **`support_queue_fragment`**, **`support_assign_ticket`**, **`_annotate_tickets_sla`**; **`test_super_views_support.py`**; removed dead **`_now`** in dashboard |
| BR-12 super_views AI split | **`super_views_ai.py`**: **`ai_model_hub`**, **`global_ai_version`**, **`global_ai_version_progress`**; **`test_super_views_ai.py`** |
| BR-12 super_views impersonation split | **`super_views_impersonation.py`**: **`switch_to_tenant`**, **`_get_client_ip`**, **`_can_impersonate`**; consolidated **`log_control_plane_action`** / **`AuditLog`** imports at module top; **`test_super_views_impersonation.py`** |
| BR-12 super_views runtime/workflow split | **`super_views_runtime_ops.py`**: **`super_runtime_inspector`**, **`super_workflow_simulator`**; **`test_super_views_runtime_ops.py`** |
| BR-12 super_views platform monitoring split | **`super_views_platform_monitoring.py`**: **`super_usage`**, **`super_pulse`**, **`super_tenant_health`**, **`super_tenant_360`**, **`super_control_health_dashboard`**; removed dead imports from **`super_views`** (**`TenantApiUsage`**, **`TenantQuotaLimit`**, **`get_lifecycle_snapshot`**) after move; **`test_super_views_platform_monitoring.py`** |
| BR-12 super_views billing console split | **`super_views_billing_console.py`**: **`billing_dashboard`**; **`test_super_views_billing_console.py`** |
| BR-12 super_views command center HTML split | **`super_views_command_center_views.py`**: **`super_command_center`**, **`super_command_center_v2`**; **`safe_platform_incidents_url`** centralized in **`super_views_helpers`** (replaces duplicate **`_safe_platform_incidents_url`** in **`super_views`**); **`test_super_views_command_center_views.py`** |
| BR-12 super_views overview surfaces split | **`super_views_overview_surfaces.py`**: **`super_schools_list`**, **`super_analytics_overview`**; removed unused **`Paginator`** / **`require_GET`** imports from **`super_views`** where obsolete; **`test_super_views_overview_surfaces.py`** |
| BR-12 super_views dashboard + exports split | **`super_views_dashboard_helpers.py`** (shared helpers incl. **`safe_registry_url`** → **`super:registries_overview`**); **`super_views_dashboard_surfaces.py`** (**`super_dashboard`**, **`super_dashboard_v2`**, **`api_super_dashboard_layout`**); **`super_views_exports.py`** (**`export_schools_csv`**, **`export_revenue_csv`**, **`export_super_dashboard_pdf`**); **`test_super_views_dashboard_surfaces.py`**, **`test_super_views_exports.py`**; **`verify_sot_pillar_evidence`** paths — **`super_views.py`** still holds **`create_school_wizard`** + re-exports; umbrella **[ ]** |
| N5 RESILIENT_EDGE audit export draft | **`templates/schools/super_audit_export.html`** — **`form-draft-save.js`** on date-range GET form; **`test_resilient_edge_wiring`** |

---

## §0.1.5 — still open

| SOT anchor | Summary | Category |
|------------|---------|----------|
| Wave 4 | Ops **depth / deep retail** (beyond POS stub) | **PRODUCT** |
| Wave 6 | **Open:** native / full mobile capture. **Closed in SOT:** roll-call `form-draft-save.js` wiring + tests. | **NEXT_CODE** / **PRODUCT** |
| Serious | SiteSettings/siteconfig ownership migration | **NEXT_CODE** |
| Serious | Long/critical forms draft/offline (**partial** in SOT — see N5 / Serious rows) | **NEXT_CODE** |

## Wave 8 / foundation — still open

| ID | Summary | Category |
|----|---------|----------|
| N2 | Delight/polish sitewide | **PRODUCT** |
| N3 | WCAG 2.1 AA critical paths | **COMPLIANCE** + **NEXT_CODE** |
| N5 | Offline/degraded reads + sync | **NEXT_CODE** |
| N7 | Progressive disclosure depth | **PRODUCT** |
| N10 | CWV CI gates + BI dashboards | **OPS** + **NEXT_CODE** |
| N22 | RTL + regional UX | **NEXT_CODE** |
| N23 | Inclusive terminology & imagery | **PRODUCT** |
| N24 | Full observability / on-call | **OPS** |
| N28 | Predictive/proactive depth | **PRODUCT** |
| Foundation | Structural tech debt (mega-files) | **NEXT_CODE** |
| Foundation | SiteSettings decomposition (full field split) | **NEXT_CODE** |
| §0.3 Pillar 1 | “No remaining structural tech debt” umbrella | **NEXT_CODE** |

**BLOCKED:** Clever/ClassLink **native** vendor APIs — BR-11 substitute only.

**External milestone (not a code checkbox):** SOC 2 / ISO **certificate on file** — follow [N16_SOC2_ISO_EXECUTION_PROGRAM.md](N16_SOC2_ISO_EXECUTION_PROGRAM.md) phase 4–5.

---

## How to use

1. Implement → flip SOT `[ ]` → `[x]` with path/test → delete row here.  
2. `python scripts/verify_sot_pillar_evidence.py` — includes N16 program path.  
3. `bash scripts/pre_deploy_gate.sh` before release.

**Related:** [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md), [PROGRAM_EXECUTION_REMAINING.md](PROGRAM_EXECUTION_REMAINING.md).
