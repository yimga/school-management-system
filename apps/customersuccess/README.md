# apps/customersuccess

> Operator-side tenant intelligence: health and maturity scoring, risk alerts,
> auto-created tickets, onboarding nudges, and k-anonymous peer benchmarking.

**Tenancy:** SHARED (public schema; rows are scoped by an explicit `school` FK,
not by a Postgres schema)
**Scale:** 11 models · 6 migrations · 17 test modules · ~6.9k LOC

## What this app owns

This is the app that watches the tenants. Where the rest of the platform serves
a school, customersuccess answers questions *about* schools on the operator's
behalf: is this tenant healthy, is it maturing, has its admin gone quiet, did
its workflows start failing, should someone reach out — and how does it compare
to its peers? It owns tenant health scores, maturity scores, risk alerts,
intervention suggestions, forecast scenarios, and the rules that turn any of
those signals into a support ticket automatically.

The defining design decision is **peer benchmarking is k-anonymous by
construction**. `BenchmarkCohortMetric` publishes percentiles (p25/p50/p75/avg)
for a cohort only when at least K member schools contributed a value — K
defaults to 5, overridable via `--min-members` or
`BENCHMARK_COHORT_MIN_MEMBERS`. Small cells are suppressed, so no individual
school's figure is recoverable from what a peer sees. This matters because
cross-tenant aggregation is the one thing a multi-tenant platform must never
get casually wrong: a cohort of two schools publishing a "peer average" is just
telling each one the other's number. When suppression bites, callers fall back
to on-the-fly averages rather than showing nothing.

The second decision is **compute and persist are separated**.
`compute_tenant_health_score(school)` returns `(score, dimensions)` and
deliberately **does not save** — the caller persists a `TenantHealthScore` if it
wants one. That keeps the scoring rules unit-testable without a DB and lets the
same function back a live preview and a nightly sweep.

The third is a **shared soft-failure discipline**: this app defines explicit
exception tuples (`CUSTOMER_SUCCESS_SOFT_FAILURES`,
`OPTIONAL_ONBOARDING_STEP_FAILURES`) rather than catching broadly, because
observing a tenant must never break it.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `TenantHealthScore` | `customersuccess_tenanthealthscore` | Stored 0–100 health score + dimension breakdown |
| `TenantMaturityScore` | `customersuccess_tenantmaturityscore` | Operational maturity score per tenant, optionally per dimension |
| `TenantRiskAlert` | `customersuccess_tenantriskalert` | Amber/red tenant risk: low adoption, payment issues, workflow failures |
| `TenantInterventionSuggestion` | `customersuccess_tenantinterventionsuggestion` | Suggested action: enable module, run onboarding, contact CS |
| `AdminInactivityAlert` | `customersuccess_admininactivityalert` | Fires when a tenant has had no admin activity past a threshold (e.g. 14 days) |
| `WorkflowFailureEvent` | `customersuccess_workflowfailureevent` | A workflow run with one or more failed actions — an input to health scoring |
| `AutoTicketRule` | `customersuccess_autoticketrule` | When to auto-create a support ticket (workflow failure, health below X, inactivity) |
| `BenchmarkCohort` | `customersuccess_benchmarkcohort` | Peer group definition: region, size band, institution type |
| `BenchmarkCohortMetric` | `customersuccess_benchmarkcohortmetric` | The k-anonymous published aggregate — one row per `(cohort, metric_key)` |
| `ForecastScenario` | `customersuccess_forecastscenario` | Stored per-tenant forecast (enrollment, revenue, capacity) |
| `HelpcenterSource` | `customersuccess_helpcentersource` | First-class promotion of the `school.settings["customersuccess"]["helpcenter_sources"]` ledger |

All 11 declared models are listed.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `sweep_tenant_health_scores` | Periodic health recompute + persist |
| Celery task | `compute_maturity_scores` | Maturity scoring sweep |
| Celery task | `run_auto_ticket_rules` | Drives `AutoTicketRule` evaluation; returns a per-rule count map |
| Celery task | `recompute_benchmark_cohorts_task` | Cohort membership + k-anonymous metric recompute |
| Celery task | `deliver_onboarding_day_n_nudges` | Iterates active schools, computes due nudges, emits via `communication.channel_adapter` |
| Management command | `recompute_benchmark_cohorts` | Same as the task; `--min-members` sets the k floor |
| Management command | `promote_helpcenter_ledger_to_first_class` | Migrates the JSON ledger into `HelpcenterSource` rows |
| Module | `services` | Health/maturity scoring, benchmark reads, onboarding step links |
| Module | `auto_ticket_runner` | `run_all_rules()` — creates a `FeedbackSubmission` with `source="auto_ticket_rule"` |
| Module | `onboarding_day_n_nudges` | Pure `compute_due_nudges` kernel + task wrapper |
| Module | `certified_administrator` | Certified Administrator program: track + module + exam registry |
| Module | `views_super`, `views_dashboard`, `views_tenant` | Operator + tenant-facing surfaces |
| Module | `bulk_csv_student_import`, `helpcenter_wizard_kernel`, `pricing_billing_clarity` | Guided-onboarding support surfaces |

No `urls.py` — views are routed by the shells that mount them.

## Before you change this

- **Never publish a cohort metric below the k-anonymity floor.** The suppression
  in `recompute_benchmark_cohorts` is the only thing standing between "peer
  benchmarking" and "leaking one school's numbers to another". `member_count`
  on a published row is `>=` the floor by contract. If you add a new
  `metric_key`, it inherits the same rule — do not add a fast path that skips it.
- **`compute_tenant_health_score` must stay non-persisting.** Callers save. If
  you make it write, the preview surfaces start mutating scores as a side effect
  of being looked at.
- **This is a SHARED app whose whole job is cross-tenant reads.** Nearly every
  query here intentionally spans schools, which is exactly the shape
  `scan_tenant_queryset_safety` flags. That does not make it exempt — a query
  crossing tenants here needs a real `# tenant-isolation-allow: <reason>` with a
  reason that survives `scan_tenant_isolation_marker_quality`, and a *tenant*-
  facing view in this app (`views_tenant.py`) must still scope to one school.
- **Auto-tickets land as `FeedbackSubmission` rows**, not a bespoke ticket model
  — that is the platform's canonical support-ticket equivalent, and the
  `source="auto_ticket_rule"` flag is how they are told apart. A rule that
  triggers on every sweep will spam the real feedback queue, so idempotency is
  the rule author's responsibility.
- **The nudge scheduler's anti-double-send state is JSON, not a table.**
  `School.settings["customersuccess"]["nudges_sent"]` holds `"<task_key>:<day>"`
  markers, which is why the whole nudge kernel ships zero migrations. Clearing
  that key re-sends the tapered schedule to a real school's real inbox.
- **Catch narrowly.** The module-level soft-failure tuples exist because a broad
  `except` here would silently pin a health score or a count to zero forever —
  the exact class of bug the platform's gates were built around. Add to the
  tuple; do not widen to `Exception`.
- **`intelligence.py` is a stub, not a feature.** `customer_success_signals`
  returns `{"signals": []}` and `continuous_improvement_suggestions` returns
  `[]` unconditionally (G6/G7 placeholders). Nothing is computed. Do not build a
  surface that presents their output as real analysis, and do not read the empty
  list as "this tenant has no signals".
- `helpcenter_services.py`'s docstring still describes the ledger as awaiting
  "future incremental work" to become a first-class model — **that promotion has
  already happened**: `HelpcenterSource` exists and
  `promote_helpcenter_ledger_to_first_class` migrates the JSON ledger into it.
  Trust the model and the command over that docstring.
