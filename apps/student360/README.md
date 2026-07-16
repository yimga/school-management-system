# apps/student360

> The single per-student view: timeline, cross-domain summary, frozen
> transcripts, behavior ledger, records holds, and university pathways.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 1 model · 1 migration · 10 test modules · ~2.6k LOC

## What this app owns

Student360 is the page a head of year opens when they need to know everything
about one child at once. It does not own the underlying data — academics, people,
finance, evals, attendance, and reports each own theirs. What Student360 owns is
the **aggregation contract**: which domains contribute to the 360 view, how each
one is summarized, and what happens when a domain is not installed.

Beyond aggregation it owns four kernels that are genuinely its own: the behavior
ledger (recognitions and infractions as two faces of one point-scored ledger),
the records-hold policy gate that decides whether a transcript may be released,
the dual-identity matrix that projects one student into their school and degree
program contexts, and the immutable transcript snapshot.

The recurring design decision is **storage minimalism**. Three of the four
kernels persist to `School.settings` JSON buckets rather than new tables —
`behavior` (FIFO cap 5000 events) and `records_holds` are explicit about shipping
zero migrations. The app has exactly one model as a result.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `ImmutableTranscript` | `student360_immutabletranscript` | Frozen snapshot of one student's transcript for one academic year — scores, terms, ranks, and locale metadata as JSON. Created by an explicit freeze action; the cross-year archive and audit/compliance surfaces read it. Unique per `(student, academic_year)`. |

That is the app's entire persistence surface. The behavior ledger, records holds,
and the university pathway registry deliberately have no tables — see above.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | Timeline feed, 360 summary, export pack, transcript freeze/read |
| Module | `behavior_kernel` | Recognition/infraction ledger, point totals, house aggregates, escalation suggestions |
| Module | `records_hold_kernel` | `can_release` gate over financial / disciplinary / library / academic / counsel_review holds |
| Module | `dual_identity` | Projects one student into school + degree-program contexts |
| Module | `university_apps_registry` | Read-only pathway specs (UCAS / Common App / WAEC / IB / Joint Admissions) |
| Module | `views` | The 360 surface views |

No `urls.py`, no celery tasks, and no management commands — the views are routed
by the surfaces that embed them.

**Not delivered:** `university_apps_registry` is a *registry only*. It declares
what each platform requires and drives the Pathway tab, the completeness check,
and the migration adapter's export shape. The actual export adapters do not
exist — the module states they land once counsel-signed agreements with each
platform are in place. Do not describe "export to UCAS" as a shipped feature.

## Before you change this

- **Never call `django.apps.apps.is_installed("finance")`.** It matches the full
  dotted app *name* (`"apps.finance"`), not the label — so those guards were
  always `False` and silently blanked the finance / evals / attendance / reports
  sections of the 360 view. Use `services.app_installed(label)`, which resolves
  via `get_app_config(label)`. This is a real bug that shipped (`46f2a3574`); the
  fix lives in a helper precisely so nobody reintroduces it inline.
- **Voided invoices are excluded from the finance headline, on purpose.** A
  voided invoice still carries a positive `total_amount`, so summing all statuses
  overstated the 360 number. The exclusion matches the authoritative balance
  runner (`finance/family_billing_aggregator.py::_default_balance_runner`). If
  you change one, change both — divergence here means the 360 view and the
  finance page disagree about what a family owes.
- **"Immutable" means no in-place edit path, not write-once.** The model docstring
  says the snapshot is never updated in place, and no field-level edit surface
  exists. But `create_immutable_transcript` uses `update_or_create` so an explicit
  re-freeze *replaces* the snapshot for that `(student, academic_year)` pair.
  Know which of those two properties you are relying on before you change either.
- **Service helpers swallow their typed exception set and return `None`/empty.**
  `_STUDENT360_SERVICE_ERRORS` is deliberately broad because a 360 view must
  render with a missing domain rather than 500. The cost is that a genuine bug in
  a contributing domain shows up as a silently absent section — check
  `log_exception_with_context` output before concluding a section "isn't wired".
- **The behavior ledger is a capped FIFO (5000 events per school).** It is not an
  audit log and must not be treated as one. If you need retention guarantees for
  behavior data, that is a new table and a real migration, not a bigger cap.
- Records-hold severity is **jurisdiction-dependent and counsel-pending** for some
  categories (disciplinary is `soft` + `counsel_pending`). The docket is
  `docs/RECORDS_HOLD_COUNSEL_REVIEW.md`. Do not harden a category to `hard`
  without that review.
