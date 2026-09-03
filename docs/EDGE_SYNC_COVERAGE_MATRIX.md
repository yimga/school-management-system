# Edge-sync coverage matrix — what rides, what is held, what nobody has decided

Status: **live gate**, seeded 2026-08-31.
Machine-readable source: [`apps/sync_engine/rail_coverage.py`](../apps/sync_engine/rail_coverage.py)
Auditor: [`scripts/audit_rail_coverage.py`](../scripts/audit_rail_coverage.py)
Baseline: `var/edge-sync-rail-coverage-baseline.json`

---

## The number, stated plainly

The edge appliance replicates **about 4.6%** of the tenant model surface.

| | |
|---|---|
| Entities on the delta rail | **21** |
| …of which are tenant business models | **17** (``incident`` and ``student_guardian`` joined 2026-09-03) |
| …of which are the rail's OWN config (`sync_engine.SyncSchedule`, `sync_engine.SyncPolicy`, a SHARED app) | **2** |
| …of which are the school-defined custom-field EAV pair (`metadata.DynamicFieldDefinition`, `metadata.DynamicFieldValue`, a SHARED app; added 2026-09-02) | **2** |
| Models across the 15 apps in `TENANT_APPS` | **326** |
| Coverage | **17 / 326 = 5.2%** |

So *"the school keeps working offline"* means, precisely: **attendance, marks, the
academic backbone, the staff roster, and read-only invoices.** A box cannot send a
message, produce a report card, log a behaviour or safeguarding incident, or run
payroll and have any of it converge back to the cloud.

**This document does not argue for wiring 300 models onto the rail.** That would be
reckless — several of the absences are correct, and one of them
(`finance.Payment`) is correct for two independently sufficient reasons. The defect
this gate closes is different and narrower: **most of the absence carried no
recorded decision at all.** Eleven of the fifteen tenant apps had zero entities and
zero written rationale, so the shape of offline mode was true by accident, and
nothing would have noticed a new model quietly joining that silence.

### Where the counts come from — and the mistake this gate made first

Model counts come from **migration state** (the migration files on disk, no
database connection), never from the runtime app registry and never from grepping
`class X(models.Model)`.

That is not a stylistic preference. The first version of this gate walked the
runtime registry and **was wrong in a way that produced a confident,
truthful-looking zero**:

* `apps/portal/models_forums.py` defines three MIGRATED tenant models
  (`CommunityForumCategory` / `Topic` / `Reply`, tables created by
  `portal/migrations/0038_community_forums_1357.py`) but it is imported **lazily**,
  by `views_forums.py` rather than by `portal/models.py`.
* A `django.setup()` registry walk therefore returns **323** tenant models in a
  cold process and **326** once anything has touched a forum view. The declaration
  was seeded from the cold number, silently missed all three, and the auditor
  reported **0 undeclared** — against an incomplete denominator.
* It surfaced only when the whole `apps/sync_engine/tests/` directory ran in one
  process: an earlier test imported a forum view, and **six** of these tests went
  red naming exactly those three models.

This is a known trap in this repo, not a novel one.
`apps/schools/tests/test_rls_tenant_table_coverage.py` already derives its tenant
table set "from MIGRATION STATE (not the runtime app registry) so it is
import-order-proof — it sees models defined in lazily-imported modules
(`apps/portal/models_forums.py`…)". This gate now does the same, and
`test_enumeration_sees_lazily_imported_models` seals it against those three real
models with no mocking.

Migration state is also the right filter in the other direction, and it gets for
free what the registry walk had to argue for: `apps/evals/models_enhanced.py`
defines 12 classes that were never migrated — `apps/evals/urls.py` calls one of
them "abandoned" — so a grep reports 22 models for `evals` while migration state,
and the database, have 10. **A model with no table cannot ride anything.**
Force-importing every `models*.py` would be worse than either: that module raises
`RuntimeError: Conflicting 'evaluationevidence' models` partway through, leaving
three abandoned models half-registered.

`TENANT_APPS` itself is read from the **source** of `config/settings.py` by AST,
not from `django.conf.settings`. The setting is only *assigned* inside the
`USE_DJANGO_TENANTS` branch, so under the default `config.settings` — a developer's
machine, and the RLS-mode CI job — `hasattr(settings, "TENANT_APPS")` is `False`.
An auditor that read the attribute would report zero tenant models on exactly the
machine you run it on. `scripts/scan_cross_tenancy_fk.py` already takes the same
approach for the same reason.

---

## The three postures

| Posture | Meaning | Requirements |
|---|---|---|
| **RIDES** | Registered on the edge delta rail. | **Never written by hand.** Derived from the live registry in `apps/api/sync_services.py` on every call, so registering an entity changes this report with no edit to the declaration. |
| **HELD** | A deliberate, argued exclusion. | **Requires** a written `rationale` **and** an `argued_in` pointer to where the decision is made (a doc, a policy row, a test). Missing either is a hard failure. |
| **NOT_YET** | Honest backlog. Nobody has decided. | Carries **no** rationale and **no** pointer. Declaring one is a hard failure — if you have the argument, the posture is HELD. |

The asymmetry is the whole point. An unargued "HELD" is a `NOT_YET` wearing a
badge, and a `NOT_YET` with a paragraph attached is a decision someone made without
recording where it was made. Both blur the only distinction this matrix exists to
keep sharp: **which absences are choices.**

`RIDES` is deliberately not a declarable value. You cannot type it. A model that
rides is simply absent from `DECLARATIONS`, and the auditor fails if a model both
rides and carries a hand-written entry (`held_but_riding`) — because that is
somebody writing "must not ride" and then wiring it.

---

## Current state, per app

| App | Models | RIDES | HELD | NOT_YET | What rides |
|---|---:|---:|---:|---:|---|
| `portal` | 31 | 0 | 0 | 31 | — nothing — |
| `academics` | 48 | 9 | 0 | 39 | `academic_year`, `attendance`, `classroom`, `department`, `specialty`, `specialty_subject`, `subject`, `subject_assignment`, `term` |
| `people` | 31 | 4 | 0 | 27 | `applicant`, `student`, `student_note`, `teacher` |
| `schoolops` | 38 | 0 | 0 | 38 | — nothing — |
| `finance` | 57 | 1 | 2 | 54 | `invoice` |
| `evals` | 10 | 1 | 0 | 9 | `evaluation` |
| `reports` | 11 | 0 | 0 | 11 | — nothing — |
| `communication` | 30 | 0 | 0 | 30 | — nothing — |
| `feedback` | 14 | 0 | 0 | 14 | — nothing — |
| `analytics` | 21 | 0 | 0 | 21 | — nothing — |
| `payroll` | 11 | 0 | 0 | 11 | — nothing — |
| `school_events` | 6 | 0 | 0 | 6 | — nothing — |
| `student360` | 1 | 0 | 0 | 1 | — nothing — |
| `athletics` | 16 | 0 | 0 | 16 | — nothing — |
| `studio_os` | 1 | 0 | 0 | 1 | — nothing — |
| **total** | **326** | **17** | **2** | **307** | **5.2%** |

Plus four rail entities in SHARED apps, reported separately so business
coverage is not overstated: `sync_schedule` and `sync_policy` (`sync_engine` —
the rail's own configuration) and `dynamic_field_definition` /
`dynamic_field_value` (`metadata` — school-defined custom fields, added
2026-09-02). Custom-field VALUES name their target row by pk string, so bundle
rows carry the target's sync anchor and every apply path resolves it
anchor-first; an unresolvable target is refused (`dfv_target_unresolved`), never
attached by integer coincidence. Platform-wide definitions (`school=NULL`) do
not ride — they are seeded by code on both sides.

**Eleven apps have nothing on the rail:** `portal`, `schoolops`, `reports`,
`communication`, `feedback`, `analytics`, `payroll`, `school_events`,
`student360`, `athletics`, `studio_os`.

---

## The two argued holds

Everything currently marked `HELD` is defensible from the repo. Nothing was
invented to make the matrix look finished.

### `finance.Payment` — HELD

Argued in [`EDGE_SYNC_FINANCE_HOLD.md`](EDGE_SYNC_FINANCE_HOLD.md), sealed by
`apps/sync_engine/tests/test_edge_sync_finance_down_only_2026_08_17.py`, and
consistent with `policy_registry.POLICIES['payment_settlement']`.

Two independently sufficient reasons, both verified rather than predicted:

1. **No delta cursor exists.** `finance.Payment` has no `updated_at` column at all,
   and the incremental bundle filters `updated_at__gt=since`, so registering it
   raises `FieldError` rather than degrading. Adding `auto_now` is not a benign
   additive migration — it rewrites the value on every save of the money ledger,
   the table most likely to be reconciled and audited byte-for-byte.
2. **It holds live settlement state** (`gateway_transaction_id`,
   `gateway_response`, `external_reference`, `completed_at`, `failed_at`,
   `compliance_checked`), and the platform already declares `payment_settlement`
   `ONLINE_REQUIRED`: *executing a charge against a gateway is a live
   transaction.* A two-way rail would contradict the platform's own rule.

### `finance.PaymentProofUpload` — HELD

Same document. Held for the first of the same reasons — no `updated_at`, so the
incremental delta cannot even query it — plus a second obstacle: a delta bundle
carries column values, never file bytes, so a synced receipt path would point the
box at a file that does not exist there.

### Everything else is `NOT_YET`, on purpose

309 models carry `NOT_YET` with no rationale. That is not laziness in the
declaration; it is the accurate record. **A fabricated rationale would be worse
than an empty one**, because it would make an undecided absence look reviewed and
would stop anyone from revisiting it. When someone actually makes the call, they
move the entry to `HELD` and write down where the argument lives.

### `NOT_YET` on this rail does not mean "no offline story anywhere"

The edge delta rail is not the platform's only offline mechanism. There is a
separate browser/PWA path — the WAL stream plus `offline_workflow_apply` — with
its own capture models (`evals.OfflineMarkEntry`, `finance.OfflinePaymentIntent`,
`finance.FinanceOfflineCaptureRecord`, `payroll.PayrollOfflineCaptureRecord`); see
`docs/OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md` and `docs/WAL_STREAM.md`.

Those are a different rail with different guarantees, and this matrix deliberately
does **not** credit them here. A model being reachable through the PWA queue says
nothing about whether an appliance in a school with no internet converges it back
to the cloud, which is the only question this document answers. Conflating the two
is exactly how a coverage number stops meaning anything.

---

## The gate

```
python scripts/audit_rail_coverage.py                  # report
python scripts/audit_rail_coverage.py --compare        # CI: fail on NEW findings
python scripts/audit_rail_coverage.py --update-baseline
python scripts/audit_rail_coverage.py --json
```

**Hard failures** (exit 1; never absorbed by a baseline):

| Kind | Meaning |
|---|---|
| `undeclared` | A tenant model with no posture at all. |
| `held_without_rationale` | `HELD` with nothing written down. |
| `held_without_pointer` | `HELD` with no `argued_in` reference. |
| `not_yet_with_rationale` | An argument recorded under `NOT_YET`. |
| `held_but_riding` | Declared `HELD` yet actually registered on the live rail. |
| `invalid_posture` | Includes hand-writing `RIDES`, which is derived. |
| `unknown_model` | A declaration key matching no live tenant model (typo, rename, deletion). |
| `tenant_apps_drift` | The settings source and the running settings disagree about `TENANT_APPS`, so the denominator is unreliable. |

**Baselined backlog** (`--compare`): the `NOT_YET` set. The 309 undecided models
that exist today must not block the build, but the backlog may only **grow**
through a deliberate `--update-baseline` commit, so a new model landing as "nobody
has decided" shows up in the diff instead of vanishing into the count.

`--update-baseline` **refuses** (exit 1, file untouched) while any hard violation
stands. A baseline snapshotted over an undeclared or unargued model records the
backlog as though the matrix were sound, and the next `--compare` is then green
about a question nobody answered — which is the failure mode this whole gate
exists to prevent, arriving through its own escape hatch.

### Wired into CI (2026-08-31)

The gate is enforced in four places, and the fourth is the one this repo insists on:

1. `.github/workflows/ci.yml::django-tests` runs
   `python scripts/audit_rail_coverage.py --compare`. It rides that job rather
   than the deps-free boundary workflow because it resolves the rail registry out
   of `apps.api.sync_services` and therefore needs the live Django app registry.
2. `scripts/pre_push_boundary_check.py::DJANGO_GATES` carries it as
   `edge-rail-coverage`. **This is the arm that actually bites today** -- the
   pre-push hook enforces by default, whereas GitHub Actions has run no jobs
   since the billing interruption, so the `ci.yml` step is correct but currently
   inert.
3. `scripts/verify_ci_gate_wiring.py::REQUIRED_GATES` lists
   `scripts/audit_rail_coverage.py`, so the gate cannot later be quietly
   un-wired without a reviewed edit to that tuple.
4. `scripts/verify_gates_can_fail.py::MUTATIONS["edge-rail-coverage"]` carries the
   planted defect that proves the gate does something. A gate cannot enter
   `DJANGO_GATES` in this repo without one; `verify_gates_can_fail --list` fails
   the push otherwise.

The mutation is a **migration**, not a class in `models.py`, and that distinction
is the gate's own lesson turned back on itself: `tenant_models()` reads migration
state, so a bare model class would not be seen and the harness would report a
false DEAD -- its own notes warn at length about exactly that mistake. Planted, the
auditor exits 1 naming `student360.gateproofundeclaredtenantmodel`; removed, it
returns to 0.

### The detector was proved before its zero was trusted

A scan reporting "0 problems" in this repo has been wrong before because the scan
itself was broken. This one was made to fail on purpose, five ways, before its
green was believed:

1. A declaration line was deleted from `DECLARATIONS` → exit **1**,
   `[undeclared] portal.announcement`.
2. A `HELD` entry was replaced with `Declaration(posture=HELD)` (no rationale, no
   pointer) → exit **1**, `[held_without_rationale]` + `[held_without_pointer]`.
3. A model was added to the enumeration — the genuine migration state **plus one
   row**, which is how a new tenant model actually arrives → `evaluate()` and the
   auditor's own `main()` both returned **1** with `[undeclared]` naming it, and
   that app's row moved from `1 model / 0 undeclared` to `2 / 1`.
4. A declaration line was removed and the auditor run as a **real subprocess**:
   exit **1**, `[undeclared] portal.communityforumtopic`; and with that same plant
   `--update-baseline` returned **1** and left the baseline byte-identical — the
   escape hatch does not open over a broken declaration.
5. And the seals were checked the same way: disabling the `undeclared` branch of
   `evaluate()` turned exactly the two detector tests red, and reverting the
   enumeration to a runtime-registry walk turned **eight** red — including
   `test_enumeration_sees_lazily_imported_models`. Both were restored and verified
   byte-identical by sha256.

What each plant proves is different, and worth stating. Plants 1, 2 and 4 run the
auditor as a **real subprocess** — fresh interpreter, fresh `django.setup()` — so
they prove the shipped command-line path end to end. Plant 3 stubs only the
*source* of the model list, and stubs it with the genuine migration state plus one
row. A runtime-registered model would prove nothing there: it exists only in the
test process's memory, and a subprocess could never see it. That the enumeration
itself is correct is proved separately and **without any mocking** by
`test_enumeration_sees_lazily_imported_models`.

The auditor uses **no git at all** — it reads migration files and the entity
registry — so the "an untracked planted file is invisible to `git ls-files`" trap
does not apply here. Plant 3 is kept permanently as
`apps/sync_engine/tests/test_edge_sync_rail_coverage_2026_08_31.py::RailCoverageDetectorBitesTests`,
so the gate's teeth are re-proved on every test run rather than in a one-off.

---

## How to change a posture

All four moves happen in
[`apps/sync_engine/rail_coverage.py`](../apps/sync_engine/rail_coverage.py).

### A new tenant model appears

The auditor fails with `undeclared`. Add one line to `DECLARATIONS`:

```python
"schoolops.newthing": _NOT_YET,
```

If it is `NOT_YET`, also run `--update-baseline` and commit the baseline change, so
the backlog growing is a visible act.

### NOT_YET → HELD (you made the call)

Replace the entry with a `_held(...)`. **Both fields are required and both are
checked**, and `argued_in` must point at a file that exists:

```python
_HELD_SOMETHING = _held(
    rationale=(
        "Why an offline copy must not converge — the mechanism, not the vibe."
    ),
    argued_in="docs/EDGE_SYNC_SOMETHING_HOLD.md; apps/sync_engine/tests/test_...py",
)
...
"schoolops.something": _HELD_SOMETHING,
```

Write the document first. A pointer at a doc that does not exist fails
`test_held_pointers_resolve_to_files_that_exist`.

### NOT_YET/HELD → RIDES (you put it on the rail)

**Do not edit this module first.** Register the entity in
`apps/api/sync_services.py::_DERIVED_ENTITY_SPECS` (the Slice notes there explain
the `client_offline_id` + `updated_at` prerequisites). The report shows it under
`RIDES` on the very next run, because the set is read, not transcribed —
registering an entity can never fail this gate.

Then **delete** the model's line from `DECLARATIONS`. A leftover `NOT_YET` on a
riding model is reported as housekeeping ("now RIDE but still carry a NOT_YET
line"), deliberately **not** a failure: nobody claimed it should stay off, so
there is no contradiction, and blocking the registration on a tidy-up in a second
file would be the wrong trade. A leftover **`HELD`** is different and *does* fail
(`held_but_riding`) — that is somebody's written "must not ride" being
contradicted by the wiring, and it needs a person.

Then run `--update-baseline`: the backlog just shrank, and locking that in is what
stops it from silently growing back.

### A model is deleted or renamed

The stale key fails with `unknown_model`. Remove it, and refresh the baseline.

---

## Related

- [`EDGE_SYNC_FINANCE_HOLD.md`](EDGE_SYNC_FINANCE_HOLD.md) — why `Payment` and `PaymentProofUpload` are held.
- [`EDGE_SYNC_IDENTITY_HOLD.md`](EDGE_SYNC_IDENTITY_HOLD.md) — why `teacher` rides two-way for the roster and down-only for pay and authorization, and why a box-created teacher is refused.
- `apps/sync_engine/policy_registry.py` — the conflict/CRDT policy per entity, including the `ONLINE_REQUIRED` class. Distinct from this matrix: a policy says *how* an entity converges if it rides; a posture says *whether* it rides at all.
- [`LOCAL_FIRST_SYNC_SEMANTICS.md`](LOCAL_FIRST_SYNC_SEMANTICS.md), [`EDGE_SYNC_OPERATIONS.md`](EDGE_SYNC_OPERATIONS.md).
