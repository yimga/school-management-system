# Zero-touch autopilot — audit of "Close Migration Cloud zero-touch gaps end-to-end"

**Date:** 2026-08-28
**Subject:** the commit titled *Close Migration Cloud zero-touch gaps end-to-end*
(25 files; autopilot on held-review open, bulk action fixes, vendor profile
seeding, auto-inferred control totals, OCR deploy gate, held-first UX).
**Method:** ran the engine, not read it. Every finding below was reproduced
against a live predicate or a live code path before it was written down, and
every fix carries a test proven to fail without it.

The commit's own 38 tests pass. So do the 124 orchestrator / finance / cutover /
reconciliation tests. The three findings are all things no existing test asked.

---

## 1. Autopilot auto-dismissed held rows in every domain it does not understand

**Severity: data loss, silent, now reachable on page load.**

`row_is_pdf_noise_hold` decides whether a held `missing_required` row is page
furniture. For a `.pdf` artifact its answer is `not row_has_domain_identity(...)`
— and `row_has_domain_identity` returns `False` for two completely different
questions:

* the identity fields are empty (a real "no"), and
* `_DOMAIN_IDENTITY_KEYS` has no entry for this domain (an "I cannot tell").

The landers emit **28** domains. The map covers **7** — academics, students,
enrollment, grades, attendance, behavior, staff. For the other 21 the answer was
always `False`, so every held row off a PDF was classified as noise regardless of
what it carried. Reproduced:

```
finance      fee_schedule_2026.pdf   {student_external_id, invoice_number, amount, currency, due_date}   NOISE=True
payroll      payroll_august.pdf      {employee_number, full_name, gross_salary, period}                  NOISE=True
guardians    guardians.pdf           {full_name, phone, student_external_id}                             NOISE=True
transcripts  transcripts_2025.pdf    {student_external_id, subject_code, final_grade}                    NOISE=True
library      library.pdf             {isbn, title}                                                       NOISE=True
```

The predicate predates this commit and already ran during apply and repair. What
this commit changed is the trigger: `auto_remediate_on_review_open` now runs it
on a plain GET of the held-review page, so an invoice row is closed by nobody, on
page load, with no click.

**Fixed.** `row_is_pdf_noise_hold` now refuses to answer for a domain it has no
keys for (`domain_identity_is_known`). Genuine page furniture in those domains
still closes — the fragment test above it reads the ROW, not the domain, and was
verified to still catch `{"page": "2", "line": "totals"}` on a finance PDF, a
`raw_line` fragment on a payroll PDF, and an empty row on a library PDF. The fix
is deliberately not "map the other 21 domains": guessing identity keys for
domains nobody has looked at would reintroduce the same class of error with more
confidence behind it.

Tests: `apps/migration_cloud/tests/test_pdf_noise_domain_fail_closed_2026_08_28.py`
(6). Proven by neutralising `domain_identity_is_known` — 5 subtests go red.

## 2. Auto-inferred control totals disabled the switch that refuses unverified money

**Severity: a money control that silently stopped controlling.**

`auto_infer_expected_totals` sets `expected_totals = observed`, so the guardrail
that runs next compares a number to itself and can only agree. As a convenience
that is fine and the docstring says so. The problem was ordering:

```python
if not bundle.expected_totals:
    if finance_landed or students_landed or payroll_landed:
        auto_infer_expected_totals(bundle=bundle)   # writes expected == observed
        bundle.refresh_from_db()
    if not bundle.expected_totals:                  # now False -- never reached
        if finance_landed:
            _handle_unverified_finance(bundle)      # the branch with teeth
        return
```

`_handle_unverified_finance` is what raises `FinancialMismatchError` under
`RMC_MIGRATION_REQUIRE_FINANCE_TOTALS` — the flag a sensitive tenant sets so an
unverified finance import is REFUSED, marked FAILED and rolled back. Once
inference populates the totals, that branch is unreachable. The inference step
also did `summary.pop("finance_landed_unverified", None)`, erasing the durable
record that money landed unchecked.

The committed coverage in `test_finance_guardrail_scope_2026_08_16` stayed green
throughout, and the reason is worth keeping: its bundles have no landed rows, so
observed totals are all `"0"`, inference skips zeros, and the old path still
runs. The regression only appears once finance actually lands something — which
is every real import. Reproduced with non-zero observed totals: no exception
raised, marker gone.

**Fixed.** The unverified-finance question is answered first, while
`expected_totals` is still genuinely empty; inference then runs as before. The
marker is left in place — inferring a total from the import is not verifying the
import, and the review banner already prefers the "needs confirmation" wording
when both flags are set.

Tests: `apps/migration_cloud/tests/test_inferred_totals_do_not_verify_2026_08_28.py`
(4) — two red before the fix, and two that pin the convenience the inference was
added for so the fix cannot be "undo it".

## 3. Review-open autopilot was a state-changing GET

**Severity: CSRF-reachable state change on tenant import data.**

Opening the held-review page now closes held rows. CSRF protection does not
reach a GET — Django cannot require a token for one, and browsers send cookies
with every sub-resource request. A third-party page carrying

```html
<img src="https://<tenant>/portal/configure/migration/8/review/">
```

would run the triage as whoever is signed in, on a bundle they never opened, and
the audit event would record the victim as the actor. A link prefetch does the
same for a page nobody visited. The equivalent POST endpoint is CSRF-protected,
so this was opened by moving the work onto the GET, not inherited.

**Fixed.** Autopilot now runs only for a request that looks like a navigation:
`Sec-Fetch-Dest` absent or `document`, and no declared prefetch. Every browser
capable of mounting either attack sends fetch-metadata; a client that sends none
(curl, the test client, an old browser) is still allowed through on purpose —
the point is to remove the attack, not to invent a new way for the page to stop
working. A cross-site link click is still a real person navigating and is
unaffected.

Tests: `apps/migration_cloud/tests/test_review_open_is_not_csrf_reachable_2026_08_28.py`
(5). Proven by deleting the guard — the three attack tests go red, the two
"still works" tests stay green.

---

## Not fixed — reported

**`reason_source` is recorded and never read.** `orchestrator.py` stores whether
a held row's `issue_class` was *declared* by the lander or *guessed* by matching
the error string, and its own comment states the contract: "a remediation pass
must be able to tell a class the lander asserted from one a matcher guessed, and
to refuse to act automatically on a guess." No remediation pass consults it.
`auto_dismiss_pdf_noise_holds`, `auto_dismiss_unstructured_fragments` and
`auto_enrich_and_replay_missing_required` all filter on
`issue_class="missing_required"` and act identically on a guess. Honouring it
would be a one-line filter, but it could stop clearing rows the zero-touch pass
is currently expected to clear, so it is a product call, not a defect fix.

**Bundle 8's 88 rows could not be checked here.** The local development database
holds zero `MigrationBundle` rows, so "they should clear on first page open" is a
prediction, not a measurement. After the fix in §1 the prediction holds for
academics/students PDF noise and no longer holds for any finance, payroll,
guardian, transcript or library row that carries real fields — which is the
correct outcome and matches the stated expectation that real gaps still need
human judgement.

## What now closes the last open rule

The spec's definition of done has one unchecked box: *every claim about
behaviour is backed by a state read, not by reading the code and reasoning
about it*. It could not be honoured with the real pass, because running
autopilot to find out what it would do closes rows in order to answer.

    python manage.py profile_bundle_quarantine --bundle-id N     # what is held
    python manage.py preview_quarantine_autopilot --bundle-id N  # what autopilot does

The second is new here, read-only, and reports three outcomes rather than two:

| outcome | meaning |
|---|---|
| `auto_close` | a dismissal rule matches; the row closes |
| `auto_replay` | a replay rule matches; the row is **re-landed and the land can fail** |
| `needs_person` | nothing touches it, with the class, domain and artifact named |

Keeping the middle column separate is the point. Folding an attempted replay
into "will clear" is the same shape of over-claim as the three defects above.
It also counts how many automated decisions rest on an `issue_class` guessed
from the error text rather than declared by the lander -- the `reason_source`
gap reported above, made visible without acting on it.

A preview of a rules engine is a second implementation of that engine, so what
keeps it honest is not shared code but
`test_preview_agrees_with_the_real_pass`: predict, run the real pass on the same
bundle, require every `auto_close` prediction to have happened and every
`needs_person` row to still be held. Proven by mutating `_preview_one` to
over-claim -- three tests go red.

---

## Standing reds, unchanged

`test_landers_fk_resolution.GradesLanderFKResolutionTests.test_assignment_without_teacher_quarantines`
and `GuardianLanderRelinkTests.test_no_identity_quarantines_precisely` both fail
here. Verified pre-existing by running the module at the parent commit; both are
already registered in `var/known-red-tests.json`. `scripts/triage_test_run.py`
reports **NEW: 0** across the 367-test relevant run.
