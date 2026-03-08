# Scoped work — verification (all done vs deferred)

**Purpose:** Single place to verify that every scoped item is either **fully done** (code-verified) or **explicitly deferred** (no partial state).

**Last verification:** After sprint-by-sprint implementation cycle.

---

## 1. Completed (code-verified)

| # | Item | Verification (where to confirm) |
|---|------|----------------------------------|
| 1 | **Pack versioning (tenant minimal)** | `apps/siteconfig/views_dashboard_config.py`: `pack_update_available = applied_pack.schools_with_outdated_bundle().filter(pk=school.pk).exists()`; `templates/siteconfig/get_blueprints.html`: "Newer version available" + link to manager marketplace. |
| 2 | **26.5 Document library CSV** | `apps/portal/views_documents.py`: `if request.GET.get("format") == "csv"` → CSV response; `templates/portal/document_library_manage.html`: "Export CSV" link with `format=csv`. |
| 3 | **26.5 Applicants list (search/filter/export)** | `apps/people/views_backend.py`: `backend_applicant_list` — `q`, `stage` filters; `format=csv` → CSV response; template has search, stage select, Export CSV link. |
| 4 | **26.5 Application form Save draft** | `apps/people/forms_backend.py`: `ApplicantCreateForm`; `views_backend.py`: `FORM_DRAFT_KEY_APPLICATION_FORM`, `_application_form_draft_initial`, `backend_applicant_create` (draft load/save/clear); `templates/people/backend_applicant_create.html` (draft alert, Save draft/Discard JS); `accounts/urls.py`: `backend/applicants/create/`; applicant list has "Add applicant" → create. |
| 5 | **Control plane runbooks/canary** | `.env.example`: `CONTROL_PLANE_RUNBOOKS_URL` commented; `docs/architecture/preview_release_canary.md`: ops note for runbooks + canary; health dashboard already links when set (`apps/schools/super_views.py`: `runbooks_url`). |
| 6 | **Student 360 transcript/archive** | `apps/student360/views.py`: `transcript_archive`, `transcript_archive_year`, `transcript_freeze`; `portal/urls.py`: routes; `templates/student360/transcript_archive*.html`; `student_360_page.html`: "Transcript & archive" button and summary link; redirects use `portal:transcript_archive` and `portal:student_360_page`. |
| 7 | **15.3 Payment plans (doc only)** | No code added; `section_15_scope_implemented_and_roadmap.md` 15.3 and `SCOPED_WORK_NOT_DONE.md` §5 document current state (advanced_payments.py reference, migration 0045); scope for future re-introduction. |
| 8 | **Baseline report / CI gate** | Documented done in DONE_WHEN Part 3 and baseline_report.md. |
| 9 | **DynamicField admin** | DynamicFieldDefinitionAdmin, DynamicFieldValueAdmin in siteconfig admin; models in metadata (0134). |
| 10 | **Sandbox origin check** | sandbox_embed origin validation (Referer/Origin vs ALLOWED_HOSTS); sandbox hardening checklist updated. |
| 11 | **Tenant app billing (6.3/29.10)** | `apps/billing/services`: record_app_install_for_billing (PlatformLedgerEntry on install); invoice_lines_from_app_ledger(school, period_start, period_end) for invoice line generation. Optional proration/usage-based per product. |
| 12 | **Get blueprints tenant entry (11.2)** | Tenant entry at `siteconfig:get_blueprints` (/get-blueprints/); "Blueprints" in portal sidebar (Admin Panel). Pack versioning minimal: "Newer version available" when outdated; link to manager marketplace. |
| 13 | **Parent mobile-first audit (14.4)** | parent_mobile_first_audit_14_4.md: viewport meta, touch targets, responsive, 320px verified; checklist items marked Verified. |
| 14 | **Classes/sections list (26.5)** | `apps/people/views_backend.py`: `backend_classroom_list` — search (q), filter (academic_year, department), format=csv; `templates/people/backend_classroom_list.html`; URL `accounts:backend_classroom_list` at backend/classrooms/. |
| 15 | **Student onboarding step-level draft (26.5)** | `apps/portal/views_onboarding.py`: FormDraft key `student_onboarding`; load draft on GET step 1 when no session; POST action=save_draft merges POST into session and saves to FormDraft; clear draft on successful submit; template has "Save draft" button and "Draft restored" alert. |
| 16 | **Migration run rollback UI** | `apps/accounts/views.py`: `migration_rollback(request, run_id)` POST-only; `migration_run_list.html`: "Rollback" button when `run.can_rollback`; URL `accounts:migration_rollback`. |
| 17 | **Pack versioning "Request update" button** | `templates/siteconfig/get_blueprints.html`: when `pack_update_available`, "Request update" button linking to `portal:support_request`. |
| 18 | **Migration cloud legacy data cleaner + read-only legacy view** | `apps/accounts/views.py`: `legacy_data_cleaner_view`, `migration_legacy_view`; `legacy_data_cleaner.py` (detect_legacy_issues, clean_legacy_data); MigrationRun.legacy_snapshot; URLs `accounts:legacy_data_cleaner`, `accounts:migration_legacy_view`. |
| 19 | **Control plane SLO dashboard (HTML)** | `apps/observability/views.py`: SLO data returned as HTML when `format=html` or Accept: text/html; template `observability/slo_dashboard.html`; health hub links to SLO dashboard (HTML). |
| 20 | **Support queue assignment** | `GlobalSupportTicket.assigned_to` (FK, migration 0141); `support_assign_ticket` view; fragment shows assignee and Assign to me/Unassign; URL `super:support_assign_ticket`. |
| 21 | **Test matrix by blueprint family** | test_matrix_by_blueprint.md; test_runtime_by_blueprint_family.py; test_runtime_from_real_school_fixture (School in DB). |
| 22 | **Control-plane access/roles** | control_plane_access_and_roles.md (require_super_access + is_superuser). |
| 23 | **Sweep A/B/C** | scripts/run_sweep_ab.py (runs check_no_hardcoding + lint_tenant_settings). |
| 24 | **Form/view refactor (pattern + slice)** | Form_view_refactor_guide.md; portal: get_site_display_name in _whatsapp_invite_link and my_digital_id. |
| 25 | **External connection points** | EXTERNAL_CONNECTION_POINTS.md (Ed-Fi, CEDS, WebAuthn, Offline, EMIS, Commercial); convert_quote_to_subscription stub in billing.services. |

---

## 2. Explicitly deferred (backlog — not partial)

These are **not** partially done; they are deferred with a clear "when" or "owner".

| # | Item | Reason deferred / next |
|---|------|--------------------------|
| 1 | **Support queue SLA / next-level ops** | Assignment done; SLA targets, escalation, and richer workflow when productised. |
| 2 | **Payment plan model re-introduction** | DB models removed (0045); re-scope in finance roadmap when product prioritises. |
| 3 | **13.2 models.png** | Optional; script `scripts/gen_models_png.py` generates when django-extensions + graphviz available; not required for checklist. |
| 4 | **Get blueprints tenant entry placement** | Entry exists at get_blueprints; placement (Admin Panel vs elsewhere) is product decision. |

---

## 3. Other deferred / roadmap / scoped (in other docs)

These appear as **deferred**, **roadmap**, **scoped**, or **optional** in other architecture/plan docs. They are **not** in §2 above; they live in the docs below. Use this section to avoid missing any deferred work.

| Source doc | Items (short) | Where to read |
|------------|----------------|---------------|
| **SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md** | Deferred: section_11 (support co-pilot, guided onboarding, shadow sessions, admin inactivity); offline_first_sync_16_5 (full offline UI); government_district_intelligence (EMIS). Roadmap: Ed-Fi, CEDS, WebAuthn; global ledger; offline/canary/government/commercial; RUNMYCAMPUS_SINGLE_PLAN (legacy wizard, accreditation, PODs, marketing CMS, demo env); MARKETING_PUBLIC_SURFACE_BACKLOG (later queue). Partial: phase12 rows; blueprint_registry; operational_identity; runmycampus_gap_ledger. Optional: Get blueprints optional entry; policy caching when scaling. Pending/placeholder: runmycampus_gap_ledger; seating chart; TENANT_MEDIA full canvas. | §2.3–2.8 |
| **PLATFORM_ROADMAP_5Y_AND_MODULE_ROLLOUT.md** | §4 Prioritised backlog; §6 Year→focus (Y1–Y5). E.g. Ed-Fi/CEDS, WebAuthn, global ledger, offline/sync, preview/canary, government layer, commercial (Y3–Y5). | §4, §6 |
| **REFINEMENT_AND_IMPLEMENTATION_ORDER.md** | Priority 3–4: Ed-Fi, CEDS, WebAuthn; Student 360 (done); DynamicField (done); global ledger; offline/sync; preview/canary; government; commercial. | Priority 3–4 table |
| **phase14_through_phase20_sections_14_to_26.md** | 14.4 PWA/offline; 14.5 Government EMIS; 14.6 developer portal/SDK; 16.1 regional tax / 195 currencies; 16.3 GraphQL; 16.5 sync engine; 17.x SoR/Experience, Ed-Fi, Wind-Down, security status, RPO/RTO; 18.x Ed-Fi, CEDS. | Per-section status |
| **phase21_through_phase24_sections_27_to_31.md** | 29.1 Passkeys/WebAuthn, step-up, masking; 29.2 traces/SLOs; 29.3 control-plane search; 29.5 CMS, page builder; 29.6 exception queue; 29.7 OAuth/monitoring; 29.8 design tokens governance; 29.9 AI guardrails; 29.10 commercial; 30.2 segmented journeys; 30.3 win-condition checklist; 31.2 Ed-Fi/CEDS; 31.7 OpenFeature. | Per-item status |
| **PLAN_COMPLIANCE.md** | Control-plane roles (deferred; use require_super_access); full impersonation flow deferred; Sweep A/B/C deferred; CI/lint scanner deferred; test matrix deferred; form/view refactors deferred; per-app refactor deferred. | Phase 9–13 tables, Summary |
| **section_11_category_killers.md** | Support co-pilot, guided onboarding, shadow sessions with masking, admin inactivity detection. | Product roadmap / deferred |
| **offline_first_sync_16_5.md** | Full offline UI (service worker, queue UI). | Partial / deferred |
| **government_district_intelligence.md** | Full EMIS pipeline. | Product roadmap / deferred |
| **DONE_WHEN_AND_SCOPED_WORK_LIST.md** | Part 3 table: Get blueprints, pack versioning, 26.5 remaining, control plane, 15.1–15.3, migration rollback/legacy, 13.2 models.png. Part 5: REFINEMENT/PLATFORM_ROADMAP_5Y (Ed-Fi, CEDS, WebAuthn, etc.). | Part 3, Part 5 |
| **RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md** | “Deferred and optional items register” table (11.2, 6.3, 29.10). Implementation notes: migration cloud rollback/legacy; blueprint pack versioning/tenant Get blueprints; tenant app billing. | § Deferred and optional register |

**Single place for “what’s deferred”:** §2 above is the **canonical short list** of explicitly deferred items. This §3 points to **all other** deferred/roadmap/scoped mentions so nothing is missed.

---

## 4. Summary

- **Nothing is left partially done:** Every scoped item is either in §1 (completed, code-verified) or §2 (explicitly deferred with reason).
- **Other docs:** §3 lists all other deferred/roadmap/scoped items mentioned in plans, roadmaps, and architecture docs so no deferred work is missed.
- **Cross-references:** [SCOPED_WORK_NOT_DONE.md](SCOPED_WORK_NOT_DONE.md) (per-item sections), [DONE_WHEN_AND_SCOPED_WORK_LIST.md](DONE_WHEN_AND_SCOPED_WORK_LIST.md) (Part 3 table), [ux_rules_audit_26_5.md](ux_rules_audit_26_5.md) (remaining table), [SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md](SWEEP_DONE_WHEN_SCOPED_DEFERRED_AND_SIMILAR.md) (full sweep).
