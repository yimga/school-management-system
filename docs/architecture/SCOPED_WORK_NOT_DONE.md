# Scoped work not yet done

Single list of **scoped** work that is defined and bounded. Items are either done (see Verification) or explicitly deferred. Use for prioritisation, sprint planning, and assigning owners.  
**Source:** DONE_WHEN_AND_SCOPED_WORK_LIST.md Part 3, REMAINING_PLAN_AUDIT_GAPS, REFINEMENT_AND_IMPLEMENTATION_ORDER.

**Verification (all done vs deferred):** [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) — every item is either completed (code-verified) or explicitly deferred; nothing partially done.

---

## Summary

| # | Item | Done when / next step | Priority | Recommendation |
|---|------|------------------------|----------|----------------|
| 1 | Pack versioning UX (tenant-facing) | Show “update available” when pack has newer version; link to manager. | P2 | **Done (minimal):** get_blueprints shows applied pack version; add “Newer version available” when outdated (see below). |
| 2 | 26.5 UX — extend to remaining lists/forms | Add search + filter + export to remaining lists; draft/autosave to long forms (e.g. application). | P2 | **Done (this cycle):** Document library CSV; Applicants list; Application form Save draft. **Deferred:** Classes/sections; Student onboarding step-level draft. |
| 3 | Control plane maturity | SLO/incident data refinement; runbooks URL; rollout/canary; support queue integration. | P2 | **Done (this cycle):** CONTROL_PLANE_RUNBOOKS_URL in .env.example; canary note in preview_release_canary. **Deferred:** SLO refinement; support queue. |
| 4 | Student 360 transcript/archive | Immutable transcript; cross-year archive (15.1). | P3 | **Done:** transcript_archive + Student 360 link to Transcript & archive. |
| 5 | 15.3 Payment plans / double-entry | Payment plan model; installment schedule; double-entry ledger or Invoice/Payment integration. | P3 | **Deferred:** Scope in section_15; re-introduce when product prioritises. |
| 6 | Migration cloud rollback / legacy | Rollback UI; legacy data cleaner; read-only legacy view. | P3 | **Deferred:** Schedule when migration usage demands. |
| 7 | 13.2 models.png | Optional architecture diagram (django-extensions graph_models). | Optional | **Deferred:** Not required; add only if needed. |

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
- **Next:** Use the [Remaining lists/forms to prioritise](ux_rules_audit_26_5.md#remaining-listsforms-to-prioritise) checklist in ux_rules_audit_26_5.md; assign one list or form per sprint; add search/filter/export or draft as per pattern.

---

## 3. Control plane maturity

- **Where scoped:** REMAINING_PLAN_AUDIT_GAPS “Control plane maturity”.
- **Done when:** SLO/incident data and runbooks URL refined; rollout/canary process documented and wired; support queue integrated where desired.
- **Current:** Health dashboard exists; links to Tenant health, Incidents, SLO API, Runbooks (when CONTROL_PLANE_RUNBOOKS_URL set). **Done this cycle:** `CONTROL_PLANE_RUNBOOKS_URL` documented in .env.example; canary/runbooks note added to preview_release_canary.md.
- **Next:** Refine SLO dashboard data; optional support queue integration.

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
- **Next:** Scope in finance roadmap (section_15_scope_implemented_and_roadmap.md 15.3); re-introduce or redesign payment plan model and double-entry when product prioritises.

---

## 6. Migration cloud rollback / legacy

- **Where scoped:** Phase 8; migration cloud docs.
- **Done when:** Rollback UI for migration runs; legacy data cleaner; read-only legacy view where needed.
- **Current:** Explicitly deferred; complexity and risk.
- **Next:** Schedule when migration usage demands it.

---

## 7. 13.2 models.png

- **Where scoped:** Deferred and optional register; phase13.
- **Done when:** Optional: generate and commit `models.png` (e.g. `python manage.py graph_models -a -o docs/architecture/models.png`).
- **Current:** Architecture map pack satisfied by apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md.
- **Next:** Add only if team decides it’s needed.

---

## References

- [DONE_WHEN_AND_SCOPED_WORK_LIST.md](DONE_WHEN_AND_SCOPED_WORK_LIST.md) — Part 3 table and Summary
- [REMAINING_PLAN_AUDIT_GAPS.md](REMAINING_PLAN_AUDIT_GAPS.md)
- [ux_rules_audit_26_5.md](ux_rules_audit_26_5.md)
- [REFINEMENT_AND_IMPLEMENTATION_ORDER.md](REFINEMENT_AND_IMPLEMENTATION_ORDER.md)
