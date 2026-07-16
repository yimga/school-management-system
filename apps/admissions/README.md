# apps/admissions

> The admission application FSM, the required-document registry, and the
> Applicant → StudentProfile enrollment service.

**Tenancy:** SHARED (public schema; the kernel is passed a `school_id` and never resolves a tenant on its own)
**Scale:** 0 models · 0 migrations · 3 test modules · ~1.1k LOC

## What this app owns

Admissions lifts the funnel from "an `Applicant` row exists" to a guided
five-stage application: a document checklist, validated stage transitions with
history, and one canonical service that promotes an accepted applicant into a
real enrolled student. It also owns the read-side that backs the cockpit's
admissions queue-depth tile and its per-stage drill-down.

The defining decision is that this app is a **kernel over someone else's row**.
It adds no model. Every piece of extended state is written into the existing
`apps.people.models.Applicant.extra_data` JSONField under a top-level
`"application"` key, so the whole slice ships zero migrations. The kernel is also
deliberately Django-free where it can be: it re-declares the stage constants
rather than importing `Applicant.Stage`, and `enroll_applicant_to_student` takes
a `db_runner` seam, so the FSM and checklist logic are unit-testable without the
app registry primed.

Stage FSM:

```
LEAD -> APPLIED -> UNDER_REVIEW -> ACCEPTED -> ENROLLED   (terminal)
             |          ^   |          |
             +-> REJECTED --+          +-> UNDER_REVIEW   (officer changed their mind)
```

## Key models

**None — this app declares no Django models and ships no migrations.** Its state
lives in two places that already exist:

- **The applicant row itself**: `apps.people.models.Applicant` — `stage` is the
  model's own field; the document checklist, transition history, and metadata
  live in `Applicant.extra_data["application"]`.
- **The enrolled student**: `apps.people.models.StudentProfile`, created by
  `enroll_applicant_to_student`.

If you are looking for an `Application` or `AdmissionDocument` table, it does not
exist. The functions here take and return plain dicts; **the caller persists.**

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `application_kernel` | Document registry, stage FSM, `advance_stage`, `can_enroll`, `enroll_applicant_to_student` |
| Module | `queue_depth` | Read-only tile data: `compute_admissions_queue_depth`, `actionable_stage_codes`, `stale_lead_cutoff`, `stage_to_pill_variant` |
| Caller | `apps/people/views_backend.py` | The applicant list, stage-advance, and enroll views — this app's only write-side consumer |
| Caller | `apps/accounts/views.py` | Renders `admissions_queue_rows` on the cockpit |

This app has no `urls.py`, no Celery tasks, and no management commands. It is a
library; every HTTP surface that uses it lives in `apps.people`.

## Before you change this

- **`ENROLLED` is terminal and `_ALLOWED_TRANSITIONS[ENROLLED]` is empty on
  purpose.** Re-enrollment is a brand-new applicant, not a rewind. Reverting
  `ACCEPTED -> UNDER_REVIEW` *is* allowed (the officer changed their mind);
  reverting from `ENROLLED` is not. `require_transition` treats a no-op
  (`current == target`) as valid, so it is safe to call on an idempotent save.
- **The kernel writes nothing.** `advance_stage` and `attach_document_reference`
  return a *new* `extra_data` dict and leave persistence to the caller. If you
  add a rule here and the row does not change, you forgot to save in
  `apps/people/views_backend.py` — the kernel is not broken.
- **The stage constants mirror `Applicant.Stage` by hand.** That is deliberate
  (Django-free unit tests), which also means it is a drift hazard: change the
  model's choices and you must change `ALL_STAGES` here too.
- **`actionable_stage_codes()` is a single source of truth, not a convenience.**
  The cockpit tile's ACTIONABLE total and the applicant list's
  `?stage=ACTIONABLE` drill-down must read the same function. `ACTIONABLE` is not
  a real `Applicant.Stage` member, so when the list view's validity guard did not
  recognise it, filtering was silently skipped and the tile drilled into *every*
  applicant (`3b7b4bf55`). The same pairing applies to `stale_lead_cutoff()` and
  `?stale=1`: the chip's count must equal the list it lands on.
- **`can_enroll` is a pre-flight, and the blockers are structured strings**
  (`required_documents_outstanding:key1,key2`). Callers parse them. Do not
  reformat them into prose.
- **Enrichment inside enrollment is best-effort and must stay that way.**
  `_resolve_active_academic_year` swallows exceptions because a missing academic
  year must never block an enrollment. But the default runner deliberately
  *chains* the new student in (active year, classroom, admission number, status,
  applicant back-link) so an enrolled student is immediately visible in rosters
  and reports rather than a bare record.
- Document keys are validated against `_DOCUMENT_REGISTRY`; an unknown key
  raises. Only four of the seven specs are optional-safe to reorder — the five
  `required=True` entries drive `can_enroll`, so flipping one to optional changes
  who can be enrolled.
- Actual file upload is **not** owned here. Documents are referenced by URL or
  storage key (`storage_ref`); upload handling stays in the existing file-upload
  pattern.
