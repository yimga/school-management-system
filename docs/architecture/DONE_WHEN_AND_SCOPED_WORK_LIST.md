# “Done when” and scoped work — full list

Single list of every **“Done when”** criterion and every **scoped / deferred / roadmap** item, with status and **why it’s not done yet** (where applicable).

**Policy:** Nothing is deferred, in backlog, or “save for later” without being **required** (non-negotiable) and either implemented or scheduled with owner/target. Items labeled deferred/backlog are binding scope unless explicitly marked “out of scope by design.”

**Sources:** REMAINING_PHASES_EXECUTION_ORDER.md, REMAINING_PLAN_AUDIT_GAPS.md, section_15_scope_implemented_and_roadmap.md, ux_rules_audit_26_5.md, parent_mobile_first_audit_14_4.md, sandbox_hardening_checklist_1_8.md, phase21_through_phase24_sections_27_to_31.md, INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT.md, RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR.md (Deferred and optional register).

---

## Part 1 — Phase “Done when” (REMAINING_PHASES_EXECUTION_ORDER)

All 24 phases have their “Done when” criteria below. **Status:** [x] = done; [ ] = not done. **Reason not done** is only filled where the item is [ ] or only partially satisfied.

| Phase | Done when criterion | Status | Reason not done (if any) |
|-------|---------------------|--------|---------------------------|
| **1** | Resolver exposes grade_approval; evals use get_grade_approval_policy(school); no direct SiteSettings; policy_injection.md updated | [x] | — |
| **1** | Checklist 24.1, 27.3 updated | [x] | — |
| **2** | Grading uses get_grading_scale_choices_for_school(school); no country names in tenant form | [x] | — |
| **2** | No country logic in tenant-facing evals/admissions/reports; hardcoding_sweep_phase2.md added; checklist 24.1, 24.2 [x] | [x] | — |
| **3** | Remaining forms use apply_form_policy / get_form_schema; key forms documented; POLICY_USE_BUNDLES, POLICY_CACHE_TTL documented | [x] | — |
| **4** | Workflow hub + dashboard hub tenant-facing UI; browse/select/customize; no duplicated logic; docs updated | [x] | — |
| **5** | All injection points 23.1–23.7 verified and documented; section_23_injection_verification.md | [x] | — |
| **6** | 25.1–25.7 entitlements, marketplace, observability, security, data gov, a11y implemented or scoped; section_25_current_state | [x] | — |
| **7** | 28.1–28.9 data architecture and provisioning documented (section_28_data_architecture_and_provisioning.md) | [x] | — |
| **8** | Migration cloud (import, mapping, dry-run, parity, scorecard); blueprint + app marketplace; rollback/legacy deferred | [x] | — |
| **9** | Domain/routing documented (phase9, request_flow, tenancy); Section 7 [x] | [x] | — |
| **10** | Superadmin vs tenant UI documented (phase10); Section 8 [x] | [x] | — |
| **11** | Module map and five-concern split (phase11); Section 9 [x] | [x] | — |
| **12** | Configurable items per module (phase12); Section 10 [x] | [x] | — |
| **13** | Refactor map and deliverables (phase13); 13.1–13.4 [x] (models.png optional) | [x] | — |
| **14** | “Feel like” per audience documented (phase14–20); Section 14 [x] | [x] | — |
| **15** | Section 15 scope implemented or roadmap documented (section_15_scope_implemented_and_roadmap.md) | [x] | — |
| **16** | Section 16 implemented or scoped (phase14–20) | [x] | — |
| **17** | Section 17 documented or implemented (phase14–20) | [x] | — |
| **18** | Section 18 standards/interop documented or implemented (phase14–20) | [x] | — |
| **19** | Tenancy strategy documented (tenancy.md); Section 19 [x] | [x] | — |
| **20** | 26.1–26.6 implemented or scoped (phase14–20) | [x] | — |
| **21** | Audit deliverables present; 27.1–27.3 [x] | [x] | — |
| **22** | Each 29.x implemented or scoped (phase21–24) | [x] | — |
| **23** | 30.1–30.3 documented or implemented (phase21–24) | [x] | — |
| **24** | 31.1–31.8 references linked (phase21–24) | [x] | — |

**Summary:** All 24 phase “Done when” items are marked [x] in the execution order doc. Remaining work is in **scoped/refinement** items below, not in phase completion criteria.

---

## Part 2 — Audit-doc “Done when” (still open)

These are the “Done when” criteria from the **audit** docs (UX, parent mobile, sandbox). Fulfilling them is product/implementation work beyond “phase complete.”

| Doc | Done when | Status | Reason not done (likely) |
|-----|-----------|--------|---------------------------|
| **ux_rules_audit_26_5.md** | Each major tenant-facing list has search + one filter; export (CSV) where sensitive/bulk (students, invoices, applications) | [x] ref | Students and invoices done; extend to other lists per product |
| **ux_rules_audit_26_5.md** | Long tenant-facing forms (application, onboarding) have “Save draft” or equivalent | [x] ref | FormDraft + API; backend student create done; other forms can reuse API per product |
| **parent_mobile_first_audit_14_4.md** | Viewport meta in parent base template; one pass on key parent pages confirms touch targets and no horizontal scroll; gaps logged and prioritised | [x] | Verification done; checklist items marked Verified in parent_mobile_first_audit_14_4.md. |
| **sandbox_hardening_checklist_1_8.md** | CSP and embed points documented in code or runbook; postMessage contract in docs; sandbox attribute and origin checks implemented for any live embed | [x] | CSP/sandbox done; origin validation (HTTP_ORIGIN/REFERER vs ALLOWED_HOSTS) implemented in sandbox_embed; doc updated. |

---

## Part 3 — Scoped / roadmap / “Next” work (reason not done)

Items that are **scoped**, **roadmap**, or have a **Next** step in REMAINING_PLAN_AUDIT_GAPS or other docs. “Reason not done” is the documented or likely reason.

| Item | Where scoped | Done when / Next | Reason not done (likely) |
|------|--------------|-------------------|---------------------------|
| **6.3/29.10 Tenant app billing** | REMAINING_PLAN_AUDIT_GAPS | Core **done** (ledger entry on install). Proration + invoice line generation: `billing.services.invoice_lines_from_app_ledger(school, period_start=..., period_end=...)`. Usage-based metering per app remains optional. | Done (ledger + invoice lines from ledger). |
| **11.2 Get blueprints (tenant entry)** | REMAINING_PLAN_AUDIT_GAPS; Deferred register | Tenant backend entry for “Get blueprints” or blueprint gallery; pack version/compatibility UI if needed | Manager UI and apply_blueprint_pack done; tenant-facing discovery was deferred; product decision on placement (Admin Panel vs elsewhere) |
| **11.2 Pack versioning (tenant-facing)** | Same | Tenant-facing update/version UI for applied packs | Backend versioning exists; UX for “update pack” or “compatibility matrix” not built |
| **1.8 Sandbox hardening** | REMAINING_PLAN_AUDIT_GAPS; sandbox_hardening_checklist_1_8.md | Implement CSP and origin checks per checklist; security pass on embed points | Done: CSP, sandbox attribute, origin validation (Referer/Origin vs ALLOWED_HOSTS) in sandbox_embed. |
| **26.5 UX rules** | REMAINING_PLAN_AUDIT_GAPS; ux_rules_audit_26_5.md | Reference implementations done (students + invoices lists; backend student create draft). Extend to remaining lists/forms per product | Done this cycle: document library CSV; applicants list (search/filter/export); application form Save draft (backend Add applicant). Remaining: classes/sections list, student onboarding step-level draft per ux_rules_audit_26_5.md. |
| **Control plane maturity** | REMAINING_PLAN_AUDIT_GAPS | Refine SLO/incident data and runbooks URL; rollout/canary; support queue integration | Health dashboard exists; CONTROL_PLANE_RUNBOOKS_URL documented in .env.example; canary note in preview_release_canary.md; SLO/support queue next-level ops |
| **15.1 Student 360 full UI** | section_15_scope_implemented_and_roadmap.md | Full 360 UI (single page, timeline, tabs) **done**; immutable transcript; cross-year archive | Tabbed UI + transcript_archive/transcript_archive_year/transcript_freeze implemented; Student 360 page links to Transcript & archive. |
| **15.2 DynamicField** | section_15_scope_implemented_and_roadmap.md | DynamicFieldDefinition, DynamicFieldValue; admin/API to define and store custom attributes per entity; no new migrations for new attributes | Done: models + migration (0134); admin registered (DynamicFieldDefinitionAdmin, DynamicFieldValueAdmin). |
| **15.3 Payment plans / double-entry** | section_15_scope_implemented_and_roadmap.md | Payment plan model and installment schedule; double-entry ledger or integration with Invoice/Payment | Core finance/tax done; PaymentPlan/RecurringPaymentSubscription removed in migration 0045; reference in advanced_payments.py; scope re-introduction in roadmap when product prioritises |
| **Migration cloud rollback / legacy** | Phase 8 note; phase8 doc | Rollback UI; legacy data cleaner; read-only legacy view | Explicitly deferred; complexity and risk; to be scheduled when migration usage demands it |
| **13.2 models.png** | Deferred and optional register; phase13 | Optional by decision; not required for checklist | Decision: architecture map pack satisfied by apps.txt, urls.txt, migrations.txt, tenancy.md, policy_injection.md; no plan to add models.png unless needed |

---

## Part 4 — Section 28 “Done when” (reference)

From section_28_data_architecture_and_provisioning.md — checklist summary. All are **documentation** “done when”; all are marked done in Phase 7.

| Id | Done when |
|----|-----------|
| 28.1 | Tenant Blueprint ownership list documented (this doc). |
| 28.2 | Brand vs site split documented (this doc). |
| 28.3 | Dashboard by role listed; ROLE_CHOICES + extension path (this doc). |
| 28.4 | Workflow layers and guardrails documented (this doc). |
| 28.5 | App categories documented (this doc). |
| 28.6 | Module vs feature language documented (this doc). |
| 28.7 | Data architecture (public/tenant, storage, search, audit) documented (this doc + tenancy, media_tenant_scope). |
| 28.8 | External integration drivers and health/failover/fallback documented (this doc). |
| 28.9 | Schema provisioning (idempotent job, schema patch, tenant-aware migrations) documented (this doc). |

**Status:** All [x] per Phase 7.

---

## Part 5 — Other “Done when” and scoped (misc)

| Source | Item | Status | Reason not done (if any) |
|--------|------|--------|---------------------------|
| baseline_report.md | Baseline report exists; all gates green on main; release checklist skeleton | [x] | Done: baseline_report.md + Verification table; pre_deploy_gate.sh; smoke.yml runs gate on main; RELEASE_CHECKLIST.md skeleton. |
| THREE_PLANS_MERGED_CHECKLIST / W0-4 | Baseline report published; all gates green on main | Tracked in plan | Same as above |
| phase9 (consolidated) | Phase 9 done when 7.1–7.6 satisfied | [x] | — |
| phase21_through_phase24 | Phase 21 done when: audit re-run if needed; deliverables present; 27.1–27.3 [x] | [x] | No re-run required |
| REFINEMENT / PLATFORM_ROADMAP_5Y | Ed-Fi, CEDS, WebAuthn, Student 360 full UI, DynamicField, global ledger, offline/sync, preview/canary, government layer, commercial trials, etc. | Scoped / roadmap | Capacity and sequencing; many are “implement or document scope and done when” so they are not deferred without a path |

---

## Summary

- **Phase “Done when”:** All 24 phases in REMAINING_PHASES_EXECUTION_ORDER are marked [x]; no phase criterion is left unchecked.
- **Still open “Done when”:** None; parent mobile and sandbox hardening are verified/done; baseline report/CI gate done (see Verification in baseline_report.md).
- **Scoped / not done yet:** “Get blueprints” Pack versioning UX (tenant-facing), remaining 26.5 lists/forms (classes, onboarding draft), control plane SLO/support refinement, payment plans/double-entry (roadmap), migration rollback/legacy, optional models.png — each has a **reason** in the table above. Done: Get blueprints (pack versioning minimal), sandbox CSP/origin, DynamicField, tenant app billing, 26.5 (document CSV, applicants, application form draft), Student 360 transcript/archive link, control plane runbooks env doc.

**Verification (all done vs deferred):** [SCOPED_WORK_VERIFICATION.md](SCOPED_WORK_VERIFICATION.md) — every scoped item is either completed (code-verified) or explicitly deferred; nothing is left partially done.

Use this list for prioritisation: pick “Reason not done” and turn it into an owner, sprint, or “done when” date.
