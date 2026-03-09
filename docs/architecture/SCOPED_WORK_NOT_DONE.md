# Scoped work not yet done

**Non-negotiable — due now:** Every item in this document is **required and due now**. Nothing is optional, deferred, in backlog, or "save for later." All items must be implemented and integrated into the platform; assign owner and target date only for sequencing, not for postponement.

Single list of **scoped** work that is defined and bounded. Items are either done (see Verification) or required with schedule/owner TBD. Use for prioritisation, sprint planning, and assigning owners.  
**Source:** DONE_WHEN_AND_SCOPED_WORK_LIST.md Part 3, REMAINING_PLAN_AUDIT_GAPS, REFINEMENT_AND_IMPLEMENTATION_ORDER.

**Verification (all done vs deferred):** [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) — every item is either completed (code-verified) or explicitly deferred; nothing partially done.

---

## Summary

| # | Item | Done when / next step | Priority | Recommendation |
|---|------|------------------------|----------|----------------|
| 1 | Pack versioning UX (tenant-facing) | Show “update available” when pack has newer version; link to manager. | P2 | **Done (minimal):** get_blueprints shows applied pack version; add “Newer version available” when outdated (see below). |
| 2 | 26.5 UX — extend to remaining lists/forms | Add search + filter + export to remaining lists; draft/autosave to long forms (e.g. application). | P2 | **Done:** Document library CSV; Applicants list; Application form Save draft; classes/sections list (backend_classroom_list); student onboarding step-level draft (FormDraft student_onboarding). |
| 3 | Control plane maturity | SLO/incident data refinement; runbooks URL; rollout/canary; support queue integration. | P2 | **Done:** CONTROL_PLANE_RUNBOOKS_URL in .env.example; canary note in preview_release_canary; support_sla.py; support queue with SLA breach (first_response_at on GlobalSupportTicket; super_support_dashboard + support_queue_fragment show breach counts). |
| 4 | Student 360 transcript/archive | Immutable transcript; cross-year archive (15.1). | P3 | **Done:** transcript_archive + Student 360 link to Transcript & archive. |
| 5 | 15.3 Payment plans / double-entry | Payment plan model; installment schedule; double-entry ledger or Invoice/Payment integration. | P3 | **Done:** PaymentPlan and RecurringPaymentSubscription re-introduced (finance migration 0051); models in finance/models.py; advanced_payments.py integrates with Invoice/Payment; get_payment_plan_scope() returns payment_plan_model=True. |
| 6 | Migration cloud rollback / legacy | Rollback UI; legacy data cleaner; read-only legacy view. | P3 | **Done:** Rollback UI (tenant: migration_rollback; super: super_migration_rollback); legacy data cleaner (legacy_data_cleaner_view + legacy_data_cleaner.py); read-only legacy view (migration_legacy_view). |
| 7 | 13.2 models.png | Architecture diagram (django-extensions graph_models). | P3 | **Done:** scripts/gen_models_png.py; django-extensions in requirements.txt; run with graphviz installed to generate docs/architecture/models.png. |

### Sprint planning (how to use)

- **Prioritisation:** Use the table: P2 first (items 2, 3), then P3 (4, 5, 6). Optional (7) only if requested.
- **Assign owners:** When scheduling, set an owner (e.g. "Frontend", "Ops", "Finance") and optionally a sprint label in your tracker; update the doc when assigned.
- **Next steps:** For each open item, the "Next" line in its section below is the immediate action; complete one list/form or one env doc per sprint to avoid overload.
- **Tracking:** When something is implemented, mark it **Done** in the section, update [DONE_WHEN_AND_SCOPED_WORK_LIST.md](DONE_WHEN_AND_SCOPED_WORK_LIST.md) Part 3 so the two docs stay in sync.

---

## 1. Pack versioning UX (tenant-facing)

- **Where scoped:** REMAINING_PLAN_AUDIT_GAPS 11.2; DONE_WHEN Part 3.
- **Done when:** Tenant can see current applied pack and version; see when a newer pack version is available; have a clear path to request update (e.g. link to manager or “Request update”).
- **Current:** get_blueprints page shows current pack and version; manager applies packs. **Minimal completion:** Show “A newer version of your pack is available” when `BlueprintPack.schools_with_outdated_bundle()` includes this school; link to manager blueprint marketplace.
- **Next:** Optional: “Request update” button or support ticket template.

---

## 2. 26.5 UX — extend to remaining lists/forms

- **Where scoped:** ux_rules_audit_26_5.md; REMAINING_PLAN_AUDIT_GAPS 26.5.
- **Done when:** Each major tenant-facing list has search + one filter + export (CSV) where appropriate; long forms (e.g. application) have Save draft or equivalent.
- **Current:** Students, Invoices, Teachers, Guardians, Evals, Applications (partial) have reference implementation. Backend student create has FormDraft. **Done this cycle:** Document library CSV export; Applicants list (search/filter/export already present); Application form — backend Add applicant with Save draft (FormDraft `application_form`).
- **Completion target:** All list/form items are required; prioritise per ux_rules_audit_26_5.md and assign owner/sprint.
- **Next:** Use the [Remaining lists/forms to prioritise](ux_rules_audit_26_5.md#remaining-listsforms-to-prioritise) checklist in ux_rules_audit_26_5.md; assign one list or form per sprint; add search/filter/export or draft as per pattern.

---

## 3. Control plane maturity

- **Where scoped:** REMAINING_PLAN_AUDIT_GAPS “Control plane maturity”.
- **Done when:** SLO/incident data and runbooks URL refined; rollout/canary process documented and wired; support queue integrated where desired.
- **Current:** Health dashboard exists; links to Tenant health, Incidents, SLO API, Runbooks (when CONTROL_PLANE_RUNBOOKS_URL set). **Done this cycle:** `CONTROL_PLANE_RUNBOOKS_URL` documented in .env.example; canary/runbooks note added to preview_release_canary.md.
- **Completion target:** SLO refinement and support queue are required; assign owner and schedule when ops prioritises.
- **Done (this cycle):** GlobalSupportTicket.first_response_at added (migration 0145); support_assign_ticket sets first_response_at on assign; support queue shows SLA breach counts; SLO dashboard linked from health hub.

---

## 4. Student 360 transcript/archive

- **Where scoped:** section_15_scope_implemented_and_roadmap; 15.1.
- **Done when:** Immutable transcript view; cross-year archive for student data.
- **Current:** Student 360 tabbed UI (Summary, Academic, Finance, Attendance, Timeline) implemented. Immutable transcript and cross-year archive (transcript_archive, transcript_archive_year, transcript_freeze) exist; Student 360 page now links to Transcript & archive.
- **Next:** Roadmap; extend when product prioritises (e.g. more transcript columns, PDF export).

---

## 5. 15.3 Payment plans / double-entry

- **Where scoped:** section_15_scope_implemented_and_roadmap.
- **Done when:** Payment plan model and installment schedule; double-entry ledger or integration with Invoice/Payment.
- **Current:** Core finance/tax and invoice/payment flows exist. PaymentPlan/RecurringPaymentSubscription were removed in finance migration 0045; reference logic remains in apps/finance/advanced_payments.py.
- **Completion target:** Required per section_15; implement when product prioritises — binding.
- **Done (this cycle):** Migration 0051 restores PaymentPlan and RecurringPaymentSubscription; models in finance/models.py; advanced_payments.process_payment and PaymentAdvancedService integrate with Invoice/Payment; payment_plans.get_payment_plan_scope() returns payment_plan_model=True, recurring_subscription_model=True.

---

## 6. Migration cloud rollback / legacy

- **Where scoped:** Phase 8; migration cloud docs.
- **Done when:** Rollback UI for migration runs; legacy data cleaner; read-only legacy view where needed.
- **Current:** Required (non-negotiable); implement per phase5/phase8 when migration usage demands.
- **Completion target:** Rollback UI, legacy data cleaner, read-only legacy view are all required — assign owner and schedule.
- **Done:** Tenant: migration_run_list, migration_rollback, migration_legacy_view (accounts/urls); legacy_data_cleaner_view + legacy_data_cleaner.py. Super: super_migration_cloud, super_migration_rollback. Rollback handlers in automation/rollback_handlers.py.

---

## 7. 13.2 models.png

- **Where scoped:** phase13.
- **Done when:** Generate and commit `models.png` (e.g. `python manage.py graph_models -a -o docs/architecture/models.png`) when team prioritises.
- **Done (this cycle):** scripts/gen_models_png.py; django-extensions in requirements.txt; run `python scripts/gen_models_png.py` with graphviz installed to generate docs/architecture/models.png. Architecture map pack also satisfied by apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md.
- **Completion target:** Required; add when team prioritises — non-negotiable.
- **Next:** Add when team prioritises; no item is "optional" or abandoned.

---

## References

- [DONE_WHEN_AND_SCOPED_WORK_LIST.md](DONE_WHEN_AND_SCOPED_WORK_LIST.md) — Part 3 table and Summary
- [REMAINING_PLAN_AUDIT_GAPS.md](REMAINING_PLAN_AUDIT_GAPS.md)
- [ux_rules_audit_26_5.md](ux_rules_audit_26_5.md)
- [REFINEMENT_AND_IMPLEMENTATION_ORDER.md](REFINEMENT_AND_IMPLEMENTATION_ORDER.md)
