# Platform Workflow Second-Pass Challenge (Phase 14)

_Generated 2026-05-22 — adversarial pass over earlier workflow-audit phases._

This document is the second-pass adversarial audit of every prior platform-workflow finding for the RunMyCampus codebase. It is **read-only**: no fixes were applied, no SOT updated, no commits made. Every challenge is cited to a file path and (where applicable) a line range.

## Inputs read

| Phase | Artifact | Status |
|---|---|---|
| 0 | `docs/generated/platform_workflow_code_truth_inventory.json` (+ `.md`) | LANDED — read |
| pre-existing | `docs/generated/workflow_click_reduction_audit.json` (+ `.md`) | LANDED — read |
| 1 | `docs/generated/platform_workflow_classification_matrix.json` | **MISSING** |
| 2 | `docs/architecture/RUNMYCAMPUS_WORKFLOW_HOW_TO_SYSTEM.md` | **MISSING** |
| 2 | `docs/generated/platform_how_to_system_audit.json` | **MISSING** |
| 3 | `docs/generated/platform_workflow_info_tags_audit.json` | **MISSING** |
| 5 | `docs/generated/operator_workflow_gear_up_audit.json` | **MISSING** |
| 6 | `docs/generated/tenant_workflow_gear_up_audit.json` | **MISSING** |
| 7 | `docs/generated/studio_os_workflow_gear_up_audit.json` | **MISSING** |
| 8 | `docs/generated/ai_workflow_assistant_audit.json` | **MISSING** |
| 9 | `docs/generated/workflow_help_kb_faq_audit.json` | **MISSING** |
| 10 | `docs/generated/workflow_productivity_scorecard.json` | **MISSING** |

Because Phases 1-10 specific artifacts had not landed, the challenge focuses on:

1. The 6 workflows listed in `workflow_click_reduction_audit.json` (the only earlier workflow audit on disk).
2. Workflows surfaced by Phase 0 inventory's per-app `likely_workflow_pages` lists.
3. Workflows the prompt's 12-question lens makes salient but earlier-phase artifacts entirely omit.

## Headline findings (counts)

| Metric | Count |
|---|---:|
| Challenges raised | 15 |
| Workflows added (missing from earlier phases) | 10 |
| Workflows overrated (earlier-phase strong, actually weak) | 3 |
| Workflows underrated (earlier-phase weak, actually fine) | 2 |
| Recommendations disputed | 4 |
| `fake-done` / placeholder claims caught | 5 |

## Single biggest fake-done smell

**`data-task="parent_payment_receipt"` does not exist anywhere outside the audit's own JSON file.** A grep across the entire `beta/school-management-system/` tree returns ONLY `docs/generated/workflow_click_reduction_audit.json` itself. The real parent-finance template (`templates/parent/finance.html:14`) uses `data-task="parent_payment"` and the Money Center dashboard (`templates/finance/dashboard.html:66-70`) uses `data-task="money_center"` with primaries `Generate fee invoices` / `Overdue` / `Payments` / `Trial balance` / `Payment Readiness Center`. There is no "Capture receipt" action surfaced anywhere on the platform. The whole `parent_payment_receipt` identifier is an audit-side invention that never landed in templates.

## Earlier-phase claims that are overrated (concrete)

### 1. `teacher_attendance` — claimed "next-action strip in place" — actually absent

- **Claim:** `workflow_click_reduction_audit.json` line 11: "Teacher Workspace next-action strip opens attendance for the active class."
- **Evidence against:** `templates/teacher/attendance.html:1-50` shows only `Export CSV` at page top. No `workflow_next_action` include, no `next_action_strip` include, no primary `Take attendance` button at the top. The primary verb the user came to do (mark roll) lives below the fold inside a roster form.
- **Severity:** high
- **Downstream impact:** the audit's `before_after_estimate: '3 to 1-2'` is not achievable in current code.

### 2. `parent_payment_receipt` — fully fake-done

- **Claim:** `data-task="parent_payment_receipt"` hook + "Money Center shows invoice, manual fallback, and receipt capture together" + primary action `Capture receipt`.
- **Evidence against:** 0 occurrences of the hook in templates; Money Center is a finance-staff page, not a parent page; no `Capture receipt` button anywhere.
- **Severity:** critical.

### 3. `report_generation` — primary action mismatch + telemetry fragmentation

- **Claim:** "Governed report builder exposes one primary generate/export action" with primary `Generate report`.
- **Evidence against:** `templates/analytics/governed_report_builder.html:54-87` exposes FOUR top-level actions (Preview / Export CSV / Export JSON / Save). None is labeled `Generate`. Telemetry splits between `data-task="report_generation"` (only on `decision_intelligence_dashboard.html`) and `data-task="governed_report_export"` (governed builder) — same workflow, two hook names.
- **Severity:** high.

## Earlier-phase claims that are underrated

### `offline_conflict_resolution` — actually one of the few worked-out empty states

- **Prior framing:** "404 to 1 explanatory action" (a dead-route patch).
- **Reality:** `templates/platform_runtime/manager_offline_sync_center.html:15-39` is genuinely best-in-class console-empty-state grammar. Explanatory text, intentional tenant-scope explanation, both primary and outline-secondary actions, breadcrumb back to founder command center. This is one of the few category-defining empty states in the repo.

### `tenant_onboarding` — Implementation Command Center is real

- **Prior framing:** hypothesis, 5-to-2 click reduction.
- **Reality:** `templates/platform_runtime/implementation_command_center.html:16-72` actually renders go-live score / 100 + readiness band + consolidated blockers list + primary-next-action button + adoption-signals event log + blockers JSON deep link. Strong workflow, undersold by the "hypothesis" label.

## Workflows missing entirely from earlier phases (10)

1. `studio_os_publish_blueprint` — 48 routes in `apps/studio_os`, completely unaudited.
2. `migration_cloud_first_pull` — most operationally critical multi-step workflow (92 routes).
3. `operator_webhook_subscription_create_and_test` — v3.37 ships full audit+replay; not in audit.
4. `tenant_meal_plan_low_balance_top_up` — parent workflow, v3.33 schoolops complete.
5. `operator_cockpit_configure` — v3.56 + v3.57.1 + v3.57.11; the operator's primary configuration surface.
6. `operator_audit_chain_verification` — v3.39 audit chain + signing.
7. `tenant_blueprint_install_from_marketplace` — `templates/marketplace/tenant_installed_apps.html`.
8. `operator_pulse_daily_review` — v3.58.6 PlatformPulseSnapshot landing.
9. `student_assessment_take` — `apps/evals` 22 routes / 5 templates; the primary STUDENT workflow.
10. `teacher_lesson_plan_publish` — `templates/academics/teacher_syllabus_hub.html`.

## Systemic findings across ALL workflows

1. **Telemetry hook fragmentation** — 3 of 6 click-reduction workflows have hook names that disagree with shipped templates. Analytics keyed on audit names will produce silent zero-event dropouts. Needs a hook-registry SOT + CI scanner.
2. **Help-coverage cliff** — Only 4 of 50 apps ship a help template (Phase 0 lines 112-114). The 6 click-reduction workflows ship **zero** contextual help. Prompt question 5 ("Is help / how-to available?") fails across the board.
3. **AI guidance is shell-level, not workflow-level** — AI Copilot rail (v3.56) is wired in `control_plane_skeleton` (operator), not in tenant workflow pages. `templates/teacher/attendance.html`, `marks_entry.html`, `parent/finance.html` have ZERO `ai-*` data hooks. Prompt question 6 fails for tenant audiences.
4. **Click-reduction audit is stale** — Dated 2026-05-05; CLAUDE.md tracks v3.57.11 (2026-05-22). The audit predates v3.28..v3.57 and the entire Migration Cloud + cockpit + observability progression.
5. **12-question lens systematically unaddressed** — The earlier audit only answers question 8 (low-click). Questions 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12 are not addressed per workflow.

## Disputed recommendations

| Workflow | Earlier recommendation | My alternative |
|---|---|---|
| `teacher_attendance` | "Add next-action strip on Teacher Workspace" | Two-part fix: (a) wire `components/workflow_next_action.html` into teacher dashboard; AND (b) add an `.rmc-bottom-sheet` primary `Save attendance` to the page itself with mobile-sticky placement. |
| `parent_payment_receipt` | "Money Center shows invoice, manual fallback, and receipt capture together." | Money Center is a finance-STAFF surface; conflating it with a parent surface is a role/tenancy error. Rename workflow `parent_invoice_pay`. Primary: `Pay invoice {id}` (PSP) OR `Mark paid (manual)` with receipt upload. Use a single `data-task='parent_invoice_pay'` hook; retire the fragmentation. |
| `report_generation` | "Governed report builder exposes one primary generate/export action." | Pick a verb. Either `Preview` is primary OR rename to `Generate`. Align hook. Retire duplicate `data-task='report_generation'` on `decision_intelligence_dashboard.html`. |
| `offline_conflict_resolution` | "Manager route explains tenant scope and sends operator to school selector." | Add second workflow `tenant_offline_conflict_apply` covering the actual fix-the-data UX at `templates/portal/offline_sync_queue.html:75-90`. Operator-side is just routing. |

## Truth-up verdict per workflow

| Workflow | Verdict |
|---|---|
| `teacher_attendance` | not_yet |
| `marks_entry` | partial |
| `report_generation` | partial |
| `parent_payment_receipt` | not_yet |
| `offline_conflict_resolution` | partial |
| `tenant_onboarding` | partial |
| `studio_os_publish_blueprint` | external_blocked_or_unaudited |
| `migration_cloud_first_pull` | partial |
| `operator_webhook_subscription_create_and_test` | partial |
| `tenant_meal_plan_low_balance_top_up` | partial |
| `operator_cockpit_configure` | partial |
| `operator_audit_chain_verification` | partial |
| `tenant_blueprint_install_from_marketplace` | not_yet |
| `operator_pulse_daily_review` | partial |
| `student_assessment_take` | not_yet |
| `teacher_lesson_plan_publish` | not_yet |

## Category-defining test per workflow (does it beat the AWS / Salesforce / Shopify / Linux / Amazon bar?)

| Workflow | 10x? | Honest reason |
|---|---|---|
| `teacher_attendance` | NO | Apple Classroom / Google Classroom open the roster with one tap and the primary action is taking attendance for today. RMC's page makes Export CSV the most prominent top-level button. |
| `marks_entry` | partial | Grid + OCR is competitive with Powerschool, but data-task name mismatch breaks productivity telemetry. No in-page help vs Salesforce. |
| `report_generation` | NO | Tableau / Looker / Snowflake open a saved report with one click + Refresh as primary. RMC fragments into two surfaces with two hooks. |
| `parent_payment_receipt` | NO | Shopify Pay / Stripe Checkout are the bar: one URL, one card form, done. RMC leads with Print / Request finance access / Jump to invoices — none of which is the action the parent came to do. |
| `offline_conflict_resolution` | partial | Operator-side empty state is best-in-class; tenant-side conflict-resolve UX is unaudited. |
| `tenant_onboarding` | partial | go-live score + blockers + primary-next-action + adoption metrics is closer to AWS Account Onboarding than to Salesforce Setup. With AI-suggested next step (currently absent), could be 10x. |

## Verdict

**`PHASE_14_SECOND_PASS_CHALLENGE_READY`**

Earlier-phase confidence cannot be sustained: 5 fake-done or placeholder claims caught with hard code evidence (most importantly, `data-task="parent_payment_receipt"` is an audit-side invention that never shipped). 3 of 6 click-reduction workflows have hook strings that disagree with templates and will silently produce zero-event analytics. 10 first-class workflows are missing from earlier phases entirely (studio_os, migration_cloud, marketplace, evals, academics-publish, schoolops top-up, cockpit, audit-chain, pulse, webhook-subscription). The 12-question prompt lens is answered only for question 8 (low-click) in any earlier artifact; questions 1-7 and 9-12 are unaddressed.

Re-running Phases 1-10 with the prompt's full 12-question lens, against the v3.57.11 codebase (not v3.26), is the minimum viable next move.
