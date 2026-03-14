# Redundancy and plan index

Single entry point so the codebase has **one plan** and **one completion reference**; redundancy is reduced and clear.

**Canonical authority (per BACKLOG_AND_DEFERRED_CLOSURE §2c):** Strategy and completion updates go **only** to the four docs in "Single plan and completion" below. Do not create new overlapping strategy or roadmap files.

## Single plan and completion

- **Plan (execution source of truth):** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) — single execution source of truth; §12 gates; evidence table §12.1.
- **Backlog/closure:** [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md) — every unchecked/deferred item closed with status + closure note.
- **Completion ledger:** [docs_truth_ledger.md](docs_truth_ledger.md) — item → DONE / PARTIAL / NOT DONE.
- **Numbered checklist:** [NEXT_50_EXECUTION_STEPS.md](NEXT_50_EXECUTION_STEPS.md) — implementation order; status per step.
- **Superseded (reference only):** [RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md](RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md) and [PLAN_COMPLETION_CHECKLIST.md](PLAN_COMPLETION_CHECKLIST.md) — use for historical context only.
- **Deployment:** [RUNMYCAMPUS_DEPLOYMENT.md](RUNMYCAMPUS_DEPLOYMENT.md) or [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) — schema-per-tenant, pre-deploy, health; no duplicate deployment plan docs.

## Other gap/audit docs (scope)

These are **not** duplicates of the single plan; they cover specific areas. For "is the plan complete?" use RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH §12 and docs_truth_ledger.

| Doc | Purpose |
|-----|---------|
| [CODE_REVIEW_GAPS_REDUNDANCIES.md](CODE_REVIEW_GAPS_REDUNDANCIES.md) | Structural and feature-level code review; TODOs and placeholders. |
| [GAPS_AND_REDUNDANCY_AUDIT.md](GAPS_AND_REDUNDANCY_AUDIT.md) | Templates, locale, placeholder TODOs. |
| [GAPS_SECTION8_AND_TAGGING.md](GAPS_SECTION8_AND_TAGGING.md) | Section 8 and information tagging. |
| [PREMIUM_FRONTEND_AUDIT.md](PREMIUM_FRONTEND_AUDIT.md) | Backlog/deferred status and premium frontend assessment for marketing, superadmin, workflow hub, dashboard manager. |
| [REPORTS/AUDIT_LOG.md](../REPORTS/AUDIT_LOG.md) | Technical audit (tenant scope, i18n, rate limiting, jobs, audit trail). |

## Premium frontend (selected surfaces)

Use a **premium frontend** for: **marketing**, **superadmin** (manager), **workflow hub**, **dashboard manager** (tenant backend + dashboard hub). Standards: design tokens, clear hierarchy, WCAG AA where applicable. See [PREMIUM_FRONTEND_AUDIT.md](PREMIUM_FRONTEND_AUDIT.md) for assessment, backlog/deferred confirmation, and references to [THEME_COMPONENT_KITS.md](THEME_COMPONENT_KITS.md) and hub shell (`static/css/hub-premium.css`).

## Redundancy addressed

- **No duplicate “single plan”:** Only RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md is the execution source of truth; BACKLOG, docs_truth_ledger, and NEXT_50 are the canonical closure/checklist. Other roadmap docs (e.g. RUNMYCAMPUS_SINGLE_PLAN_COMPLETE) are reference or superseded.
- **Master Table List:** One doc ([MASTER_TABLE_LIST.md](MASTER_TABLE_LIST.md)); onboarding references it; no second list elsewhere.
- **Audit trail:** One design doc (AUDIT_TRAIL_TRIGGER_BASED.md); one revoke command (revoke_audit_log_permissions); REPORTS/AUDIT_LOG section 11 points to both.
