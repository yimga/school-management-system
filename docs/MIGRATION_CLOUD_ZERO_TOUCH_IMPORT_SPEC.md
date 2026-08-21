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

**2. Most landers throw away the row that failed.**
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

**4. Classification is substring-matching on English.**
`_classify_quarantine_issue` decides whether a row needs a human by searching the
error text for `"duplicate"`, `"not found"`, `"missing"`. A lander that phrases an
error differently lands in `lander_error` and is treated as needing a person. The
single most consequential routing decision in the pipeline is made by
`if "invalid" in e`.

## Required end state

Ordered. Each is independently shippable and independently valuable.

**1 — Every lander keeps the row it rejected.**
Extend the lander contract so a per-row failure carries `(source_row, reason_code,
field)`. Enforce with a gate that fails when a lander appends a bare string. This
is the prerequisite for everything below; without it, steps 3 and 4 cannot exist.

**2 — Classification becomes structured.**
Landers emit a `reason_code` enum. `_classify_quarantine_issue` becomes a mapping,
and substring-matching survives only as a fallback for legacy landers, logged as
such so the backlog is visible.

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
