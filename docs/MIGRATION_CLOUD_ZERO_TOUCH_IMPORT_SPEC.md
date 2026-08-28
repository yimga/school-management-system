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

**3 — A remediation pass runs before a human is ever shown anything. ✅ DONE 2026-08-28 (repo-scope)**
Machine-resolvable classes resolve themselves:
- `source_deletion` — correct outcome, auto-closed, never shown
- `duplicate` — landers upsert by external id, so this is already-applied,
  auto-closed
- `invalid_ref` where the referent landed later in the same bundle — replay the
  row, since wave ordering is the cause, not the data
- `missing_required` where the field has a defensible default — apply it, audited
- PDF/stat lines with no importable identity — auto-dismissed (not waived)

> Shipped in `apps/migration_cloud/auto_remediate.py`:
> `auto_remediate_after_apply` (post-apply + pre-repair),
> `auto_remediate_on_review_open` (held-review GET + API `?autopilot=1` +
> `run_autopilot` action), bounded by `MAX_AUTO_REMEDIATE_PASSES = 2`.
> Audit: `migration.quarantine.auto_resolved` events + `mapping_summary.auto_remediation`.
> Reversal: `reopen_auto` action restores auto-resolved rows to `PENDING`.

**4 — Only genuinely ambiguous rows reach a person**, with the source row shown,
the reason in plain language, and a one-click decision that writes back. **✅ DONE 2026-08-28 (repo-scope)**
— held-first card stack, autopilot-on-open, inline edit + accept/replay, missing-field
highlighting on edit grid, toast errors (no raw `window.alert`), mapping/drift in
collapsed `<details>` only when held work remains.

**5 — The counters cannot disagree.** **✅ DONE 2026-08-28 (repo-scope)**
— `quarantine_caps` per artifact when engine cap truncates (banner + export CTA),
`review_gap` when apply held ≠ DB pending, inferred control totals flagged for
confirmation, cutover/finance banners on review page.

## External / counsel-blocked (cannot close in-repo)

| Item | Status |
|------|--------|
| MAA v2.0 flip | **BLOCKED** — counsel signoff PDF (`docs/MAA_V2_PROMOTION_CHECKLIST.md`) |
| FACTS/Skyward write paths | **BLOCKED** — `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` |
| HSM audit root signatures | **PARTIAL** — `local-env-key` AND `hashicorp-vault` are implemented (`services/hsm_vault.py`, v3.40.0). `aws-kms` / `azure-keyvault` / `gcp-kms` remain reserved and raise `NotImplementedError`. This row previously said all cloud bridges were reserved; verified against `RESERVED_BACKENDS_HSM` on 2026-08-28. |
| Live vendor connector certification | **BLOCKED** — needs sandbox credentials per vendor |

Verified 2026-08-28 that each of these is blocked ONLY externally — a thing
can be waiting on counsel and also be missing the code that would make the
signature useful:

* **MAA v2.0** — `resolve_active_version_for_tenant` and
  `resolve_preview_version_for_tenant` are wired, `promote_maa_v2` exists,
  `MIGRATION_CLOUD_MAA_DEFAULT_VERSION` is `v1.0` and `v2.0` is in the draft
  set. `docs/legal/maa_v2_signoff.pdf` is absent. One config flip away.
* **FACTS / Skyward** — the block holds. Both companion vendor modules still
  carry their `honest-stub` write markers and no feature flag routes round
  them. The 2026-08-28 wave added `Courses.csv` / `courses.csv` column maps to
  both accelerators and seeded both connector profiles, all read-direction:
  `supported_methods: ["file_export"]`, `known_limitations: "Read-path CSV
  only; write paths counsel-blocked."` Both sit at `PILOT_READY`, the same
  level as PowerSchool / Blackbaud / Veracross, so no new claim was made.
* **Live vendor certification** — still needs sandbox credentials per vendor.
  Seven vendor mapping templates exist; none has been run against a live
  tenant of that vendor.

## Hard rules — definition of done

- [x] **No count may exceed what is durably recorded** without displaying the gap.
      (`quarantine_caps` on bundle + `review_gap` banner.)
- [x] **A class that needs nobody is never counted as needing someone.**
      (Autopilot dismiss/replay before held-review render.)
- [x] **Auto-remediation is idempotent and reversible**, and every automated
      resolution is audited with what it changed and why.
      (`migration.quarantine.auto_resolved` + `reopen_auto`.)
- [x] **No new retry loop without a stated, tested ceiling.**
      (`MAX_AUTO_REMEDIATE_PASSES = 2`.)
- [x] **Remediation must not depend on the LLM being reachable.**
      (Rules-only path in `auto_remediate.py`; AI explain is optional overlay.)
- [ ] **Every claim about behaviour is backed by a state read**, not by reading
      the code and reasoning about it. **The one rule still open**, and the one
      the "bundle N will clear on first open" claim depends on.

      Running the real pass to find out is not a state read -- it changes the
      state, and on a live tenant it closes rows in order to tell you whether it
      would close them. So:

      ```
      python manage.py profile_bundle_quarantine --bundle-id N   # what is held
      python manage.py preview_quarantine_autopilot --bundle-id N  # what autopilot does
      ```

      Both are read-only and safe against production. The preview reports three
      outcomes, and the middle one is the one that gets over-claimed: a replay is
      ATTEMPTED, the row is re-landed, and a failed land stays held. It also
      counts how many automated decisions rest on an `issue_class` guessed from
      the error text rather than declared by the lander.

      Ticking this box needs the output of those two commands against a real
      bundle, pasted somewhere durable. Nothing in the repo can do it -- the
      development database holds zero bundles.

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
