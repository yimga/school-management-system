# Redundancy and plan index

Single entry point so the codebase has **one plan** and **one completion reference**; redundancy is reduced and clear.

## Single plan and completion

- **Plan:** [RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md](RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md) — the only canonical roadmap for RunMyCampus (Parts 0–6, 4.1–4.11).
- **Closure:** [PLAN_COMPLETION_CHECKLIST.md](PLAN_COMPLETION_CHECKLIST.md) — every implementable item is **Done**; only product/external Roadmap items remain deferred.
- **Deployment:** [RUNMYCAMPUS_DEPLOYMENT.md](RUNMYCAMPUS_DEPLOYMENT.md) — schema-per-tenant, pre-deploy, health; no duplicate deployment “plan” docs.

## Other gap/audit docs (scope)

These are **not** duplicates of the single plan; they cover specific areas. For “is the plan complete?” use the completion checklist.

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

- **No duplicate “single plan”:** Only RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.md is the plan; other roadmap docs (e.g. RUNMYCAMPUS_GAP_ANALYSIS_AND_ROADMAP, ROADMAP_TOKEN_SUMMARY) are summaries or phase-specific.
- **Master Table List:** One doc ([MASTER_TABLE_LIST.md](MASTER_TABLE_LIST.md)); onboarding references it; no second list elsewhere.
- **Audit trail:** One design doc (AUDIT_TRAIL_TRIGGER_BASED.md); one revoke command (revoke_audit_log_permissions); REPORTS/AUDIT_LOG section 11 points to both.
