# Zero-touch import — the standard Migration Cloud must meet

*Written 2026-08-21, after bundle 84 held 442 of 547 rows "for review" with nobody
able to review them.*

## The goal, stated once

> **An import either completes, or it explains itself in terms a school can act on.
> A human is involved only where judgement is genuinely required — never to
> compensate for the system failing to keep the evidence it needs.**

"Held for review: 442" is not a review queue. It is a count of things the system
gave up on and could not describe. Migration Cloud is the product's biggest
promise; this is the part of it that has to be immaculate.

## What is actually blocking it

Four findings, each verified in the code, not inferred.

**1. There is no remediation loop. At all.**
`apps/automation/quarantine_services.py` defines `mark_repaired()` and
`get_repaired_rows()` — the repair-and-replay pair. Both have **zero callers**.
The review page is read-only. So the honest answer to "who reviews these — an
automated pass or an admin?" is **neither**. Held rows sit forever, and the only
way to retry one is to re-run the whole import.

**2. Most landers throw away the row that failed.** — *CLOSED 2026-08-21, see step 1.*
`_quarantine_errors` can only attach `source_row` when a lander called
`record_row_error`. **6 of 35 lander files do.** For the other 29, a held row is
an English error string and a `row_index` that is *the position in the error
list*, not the position in the source file. **You cannot replay a row you did not
keep** — which makes automated remediation impossible by construction, no matter
how good the remediator is.

**3. Quarantine was silently truncated.**
`result.errors[:200]` capped durable records at 200 per artifact while the board
counted every one. One artifact in bundle 84 held 326 rows — 126 of them left no
record at all. Now reported loudly (`QUARANTINE_RECORD_CAP`), but reporting a
gap is not closing it.

**4. Classification is substring-matching on English.** — *CLOSED 2026-08-21, see step 2.*
`_classify_quarantine_issue` decides whether a row needs a human by searching the
error text for `"duplicate"`, `"not found"`, `"missing"`. A lander that phrases an
error differently lands in `lander_error` and is treated as needing a person. The
single most consequential routing decision in the pipeline is made by
`if "invalid" in e`.

**5. A held row and a durable record were never the same number.** *(found while
closing 1; CLOSED 2026-08-21)* — 12 lander sites appended to `result.errors`
without incrementing `result.quarantined`. The board counts the second; the
quarantine writer iterates the first. So partial-write diagnostics ("custom
attributes sweep failed for staff 12") became "held for review" rows a school was
asked to act on, and the two counts on the same page disagreed by construction.

## Required end state

Ordered. Each is independently shippable and independently valuable.

**1 — Every lander keeps the row it rejected. ✅ DONE 2026-08-21**
Extend the lander contract so a per-row failure carries `(source_row, reason_code,
field)`. Enforce with a gate that fails when a lander appends a bare string. This
is the prerequisite for everything below; without it, steps 3 and 4 cannot exist.

> Shipped. `_helpers.record_row_error(result, row, msg, *, reason_code, field)` is
> the whole contract, and **all 106 per-row failure sites across 33 lander files
> now use it** (was 6 files). `scripts/scan_lander_row_error_contract.py` is a
> zero-baseline gate on three shapes: a bare `result.errors.append`, a bare
> `result.quarantined += 1`, and a `record_row_error` with no `reason_code`.
>
> Two defects surfaced while wiring it:
>
> * **Rows were paired to errors by MESSAGE.** `_quarantine_errors` built a
>   `{error_string: row}` dict, so two rows failing with the same message
>   collapsed onto one entry and every row but the last lost its snapshot. Most
>   messages do not interpolate the row, so most multi-row failures hit it. Now
>   paired by index, with a guarded fallback when the lists do not correspond.
> * **12 sites appended to `errors` without incrementing `quarantined`.** Each
>   minted a quarantine record the board's held count never included, so the
>   banner and the table disagreed and a school was shown a partial-write warning
>   as though a row had been rejected. Those are now `record_row_note` — still
>   durable, still logged, no longer counted as rows anyone must review.

**2 — Classification becomes structured. ✅ DONE 2026-08-21**
Landers emit a `reason_code` enum. `_classify_quarantine_issue` becomes a mapping,
and substring-matching survives only as a fallback for legacy landers, logged as
such so the backlog is visible.

> Shipped. `landers/reason_codes.py` holds the vocabulary — deliberately the same
> five classes the review surface already speaks, so no tenant is shown a label
> nobody wrote. `classify_message` survives as the fallback, has ONE
> implementation now (the orchestrator delegates to it rather than keeping a
> second copy), and every record stores `reason_source: declared | fallback` so a
> remediation pass can refuse to act automatically on a guess.
>
> **What it changed, measured:** the matcher sent 60 of 106 sites to
> `lander_error` — the bucket meaning "a person must look at this". Declaring the
> codes moved **11 sites out of it** (60 → 49):
>
> | Class | matcher | declared |
> |---|---|---|
> | `source_deletion` | 2 | 2 |
> | `duplicate` | 0 | 0 |
> | `invalid_ref` | 13 | **22** |
> | `missing_required` | 31 | **33** |
> | `lander_error` | 60 | **49** |
>
> The clearest case: `no team named X (catalog not landed yet)` matched neither
> `"not found"` nor `"no such"`, so a wave-ordering reference failure — the one
> class step 3 can replay without asking anybody — read as a crash.

**3 — A remediation pass runs before a human is ever shown anything.**
Machine-resolvable classes resolve themselves:
- `source_deletion` — correct outcome, auto-closed, never shown
- `duplicate` — landers upsert by external id, so this is already-applied,
  auto-closed
- `invalid_ref` where the referent landed later in the same bundle — replay the
  row, since wave ordering is the cause, not the data
- `missing_required` where the field has a defensible default — apply it, audited

**4 — Only genuinely ambiguous rows reach a person**, with the source row shown,
the reason in plain language, and a one-click decision that writes back.

**5 — The counters cannot disagree.** Held total, durable records, and rows shown
are one number or the difference is displayed.

## Hard rules — definition of done

- [ ] **No count may exceed what is durably recorded** without displaying the gap.
- [ ] **A class that needs nobody is never counted as needing someone.**
- [ ] **Auto-remediation is idempotent and reversible**, and every automated
      resolution is audited with what it changed and why.
- [ ] **No new retry loop without a stated, tested ceiling.**
      See `docs/ENGINEERING_STANDARD_PROVE_THE_OUTCOME.md` — a self-heal that
      cannot give up is a loop, and one already cost a tenant 24 hours.
- [ ] **Remediation must not depend on the LLM being reachable.** As of
      2026-08-21 the cloud deployment is pointed at `ollama` — a local-only
      provider that does not exist on Render — so every AI call fails, the
      circuit opens, and everything falls back to rules. Deterministic rules are
      the product; AI is an enhancement on top, never the mechanism.
- [ ] **Every claim about behaviour is backed by a state read**, not by reading
      the code and reasoning about it.

## The prompt

Paste this, with the two standards above it:

> Make Migration Cloud imports zero-touch, in the order given in
> `docs/MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC.md`. Start by reading the actual
> quarantine distribution from production — `issue_class` and `domain` counts for
> the affected runs — and let that decide which class to automate first; do not
> pick based on what the code suggests.
>
> For each class you automate: state what evidence proves the row can be resolved
> without a person, what happens when that evidence is absent, and how the
> resolution is reversed if it turns out wrong. Ship one class at a time, each
> with tests that fail against a planted mutant.
>
> Do not reduce a held-row count by hiding rows. The only acceptable way for the
> number to fall is that the rows were genuinely resolved, and the audit trail
> shows how.
