# Sweep verification — complete (no assumptions)

**Purpose:** Every scoped item is verified in code or config; nothing is assumed or overlooked. Use this as the single checklist to confirm implementation.

**Policy:** [PLAN_POLICY.md](PLAN_POLICY.md) — everything non-negotiable, due now.

---

## 1. Code-verified (exact locations)

| # | Item | Verified in |
|---|------|-------------|
| 1 | Pack versioning (tenant minimal) | `apps/siteconfig/views_dashboard_config.py`: `pack_update_available`, `schools_with_outdated_bundle()`; `templates/siteconfig/get_blueprints.html` |
| 2 | 26.5 Document library CSV | `apps/portal/views_documents.py`: `request.GET.get("format") == "csv"`; template Export CSV link |
| 3 | 26.5 Applicants list | `apps/people/views_backend.py`: `backend_applicant_list` (q, stage, format=csv); `accounts/urls.py`: `backend_applicant_list` |
| 4 | 26.5 Application form Save draft | `apps/people/forms_backend.py`, `views_backend.py`: `FORM_DRAFT_KEY_APPLICATION_FORM`, `backend_applicant_create`; `templates/people/backend_applicant_create.html` |
| 5 | Control plane runbooks/canary | `.env.example`: `CONTROL_PLANE_RUNBOOKS_URL`; `apps/schools/super_views.py`: `runbooks_url` in health dashboard |
| 6 | Student 360 transcript/archive | `apps/student360/views.py`: `transcript_archive`, `transcript_archive_year`, `transcript_freeze`; `portal/urls.py`; templates |
| 7 | 15.3 Payment plans integration | `apps/finance/payment_plans.py`: `get_payment_plan_scope()`, `schedule_installment_due_dates()`; `apps/finance/services.py`: `get_finance_capabilities()` calls `get_payment_plan_scope()` |
| 8 | Baseline report / CI gate | `baseline_report.md`; `scripts/pre_deploy_gate.sh` |
| 9 | DynamicField admin | siteconfig admin: DynamicFieldDefinitionAdmin, DynamicFieldValueAdmin; metadata app |
| 10 | Sandbox origin check | sandbox_embed origin validation; `sandbox_hardening_checklist_1_8.md` |
| 11 | Tenant app billing | `apps/billing/services.py`: `record_app_install_for_billing`, `invoice_lines_from_app_ledger` |
| 12 | Get blueprints tenant entry | `apps/siteconfig/urls.py`: `get-blueprints/`, `get_blueprints`; `apps/siteconfig/portal_sidebar_items.py`: "Blueprints" in Admin Panel; `config/tenant_urls.py`: siteconfig included |
| 13 | Parent mobile-first audit | `parent_mobile_first_audit_14_4.md`; viewport in `templates/portal_base.html` |
| 14 | Classes/sections list (26.5) | `apps/people/views_backend.py`: `backend_classroom_list` (q, academic_year, department, format=csv); `accounts/urls.py`: `backend_classroom_list` |
| 15 | Student onboarding step-level draft | `apps/portal/views_onboarding.py`: FormDraft `student_onboarding`, action=save_draft; template Save draft |
| 16 | Migration run rollback UI | `apps/accounts/views.py`: `migration_rollback`; `accounts/urls.py`: `migration_rollback`; template Rollback button |
| 17 | Pack versioning "Request update" | `templates/siteconfig/get_blueprints.html`: Request update button → `portal:support_request` |
| 18 | Legacy data cleaner + legacy view | `apps/accounts/views.py`: `legacy_data_cleaner_view`, `migration_legacy_view`; `legacy_data_cleaner.py`; URLs in `accounts/urls.py` |
| 19 | Control plane SLO dashboard | `apps/observability/views.py`: `api_operational_slo_dashboard` (format=html); `apps/schools/super_views.py`: health hub link to SLO dashboard; `config/urls.py`, `manager_urls.py`, `tenant_urls.py`: route |
| 20 | Support queue assignment | `GlobalSupportTicket.assigned_to` (migration 0141); `apps/schools/super_views.py`: `support_assign_ticket`; `super_urls.py`: `support_assign_ticket`; fragment template |
| 21 | Support queue SLA | `apps/siteconfig/support_sla.py`: `SUPPORT_SLA_*`, `ticket_response_breach`, `ticket_resolution_breach`; `apps/schools/super_views_support.py`: `_annotate_tickets_sla`, dashboard + fragment pass SLA (re-exported via `super_views`); `templates/schools/super_support_queue_fragment.html`: SLA column; `super_support_dashboard.html`: SLA alert |
| 22 | Test matrix by blueprint family | `test_matrix_by_blueprint.md`; `apps/platform_runtime/tests/test_runtime_by_blueprint_family.py` |
| 23 | Control-plane access/roles | `docs/architecture/control_plane_access_and_roles.md`; `require_super_access` in super views |
| 24 | Sweep A/B/C | `scripts/run_sweep_ab.py` |
| 25 | Form/view refactor | `Form_view_refactor_guide.md`; portal `get_site_display_name` |
| 26 | External connection points | `EXTERNAL_CONNECTION_POINTS.md`; `convert_quote_to_subscription` in billing.services |
| 27 | 13.2 models.png | `scripts/gen_models_png.py`; `apps/siteconfig/management/commands/generate_models_diagram.py`: `python manage.py generate_models_diagram` |
| 28 | Policy cache + bundles (default on) | `config/settings.py`: `POLICY_USE_BUNDLES` default `"1"`, `POLICY_CACHE_TTL` default `300`; `apps/policies/resolver.py` uses both; `invalidate_policy_cache` called from policy_registry, siteconfig, marketplace, etc. |
| 29 | Get blueprints placement | Implemented: Blueprints in Admin Panel via `portal_sidebar_items.py`; tenant URL `/siteconfig/get-blueprints/` via `config/tenant_urls.py` + `siteconfig/urls.py` |

---

## 2. Config / docs verified

| Item | Verified in |
|------|-------------|
| .env.example policy | `POLICY_USE_BUNDLES`, `POLICY_CACHE_TTL` commented with "required" / default on |
| PLAN_POLICY | `docs/PLAN_POLICY.md` |
| SCOPED_WORK_VERIFICATION | `docs/architecture/SCOPED_WORK_VERIFICATION.md` — §1 completed list; §2 updated to match this sweep |

---

## 3. No-assumption rule

- Every row above has a **Verified in** path. If something is not in this list, it is not considered verified.
- When adding new scoped work, add a row here with the exact file(s) and symbol(s) before marking done.
- Run this sweep after any major change: grep for the key symbols above and confirm they exist.
