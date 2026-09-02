# Migration Cloud + Edge AI: production state read and what it found

**2026-08-28 to 2026-09-02.** Closes the zero-touch spec's last hard rule by
actually performing the read, and records the six defects the read exposed that
reading the code had not.

Everything below is on `main` and verified by content against `origin/main`
after 117 intervening peer commits. **None of it is deployed** -- see
[Deployment risk](#deployment-risk).

---

## 1. The state read (production, 2026-08-30)

The spec's final hard rule is *"every claim about behaviour is backed by a state
read, not by reading the code and reasoning about it."* The read:

```
 id   held  status      label / school
 85     88  APPLIED     Upload - 8 file(s) / Gilead Technical High School
 84    111  RECONCILED  / Gilead Technical High School
 83  75600  RECONCILED  Upload - 3 file(s) / Gilead Technical High School
 82      0  FAILED
 81    400  APPLIED     Student Record / New Test High School
 78    274  RECONCILED  Upload - 8 file(s) / New Test High School
```

### Bundle 85 -- the "88 rows will clear" claim

```
88  missing_required  academics  school_stats_2026-01-18 22_47_25.679938.pdf
88 auto_close | 0 auto_replay | 0 needs_person | rule: pdf_noise
```

**The claim held.** It is trustworthy for three reasons the totals alone do not
show:

* **No replays.** A replay is *attempted* -- the row is re-landed and a failed
  land stays held. Nothing here rests on that uncertain outcome.
* **Zero decisions on a guessed class.** The preview prints
  `auto_decided_on_guessed_class` only when non-zero and stayed silent, so all 88
  carry `reason_source: declared` -- the lander named the class, `classify_message`
  did not guess it from error text.
* **One artifact, one domain, one class.** No minority of real records hiding in
  a mixed population.

### Per-artifact yield for bundle 85

```
school_stats_...22_47_25.pdf    fmt=pdf   row_count=88   held=88   <- produced nothing
school_stats_...22_47_32.xlsx   fmt=xlsx  row_count=40   held=0    <- skipped as a report
specialties_...csv              fmt=csv   row_count=13   held=0
specialties_...xlsx             fmt=xlsx  row_count=13   held=0
student_...xlsx                 fmt=xlsx  row_count=200  held=0
subjects_...xlsx                fmt=xlsx  row_count=121  held=0
subjects_...csv                 fmt=csv   row_count=121  held=0
teachers_...csv                 fmt=csv   row_count=39   held=0
```

---

## 2. What the read found (all fixed, all mutation-proven)

| # | Defect | Fix |
|---|--------|-----|
| 1 | Box copilot answered from rules: `host.docker.internal` does not resolve on Linux Docker | `extra_hosts` host-gateway in `deploy/selfhost/docker-compose.yml` |
| 2 | ...and once it resolves, Ollama's `127.0.0.1` bind still refuses the container | `_is_loopback()` splits the causes; readiness names `OLLAMA_HOST=0.0.0.0` |
| 3 | `Bundle N not found` was a dead end where these commands actually run | Both commands list bundles and still exit non-zero |
| 4 | A page open ran five queryset passes (two of which WRITE) over 75,600 rows | `REVIEW_OPEN_ROW_BUDGET`; `remediate_quarantine_batch` for the batch path |
| 5 | The PDF-noise rule fired on a `.csv` named `school_stats*` | Extension gate first; the filename shortcut deleted as redundant |
| 6 | An artifact that produced no records left an APPLIED bundle with an empty queue | `artifact_yield_overview()`; three distinct answers, not one list |

### Why #4 mattered most

`QUARANTINE_RECORD_CAP = 2000` reads like a ceiling. It is applied as
`result.errors[:CAP]` -- **per artifact, per pass** -- so a bundle accumulates far
past it. Bundle 83 is 37x it. The page-open pass had no size guard, so that
request burned a worker until the proxy killed it, and a pass killed mid-flight
leaves *some* rows closed and the rest held, silently.

The budget belongs to the **trigger**, not the work: `enforce_row_budget=True`
protects the page open, and the batch command passes `False` because it runs
outside any request. A guard that left 75,600 rows unresolvable would have been
the same bug, refused politely.

### Why #5 mattered

A filename substring -- operator-supplied -- decided whether real rows were
discarded. Verified by running it, not reading it:

```
True   school_stats_export.csv     <- dismissed by a PDF-noise rule
True   school_stats.xlsx
False  academics_export.csv        <- control
```

That is exactly the population the operator said must reach a human. Derived
reports already have a stronger owner: `is_derived_report()` reads the HEADERS.
Bundle 85 is deliberately unchanged (its artifact IS a PDF) and a test pins that.

### Why #6 needed three answers, not one

"Contributed nothing" has three causes and only one is a fault:

* **Produced NO records** -- every discovered row was quarantined. A real concern.
* **Skipped as a derived report** -- zero is correct by design (`report_lander`).
* **Could not be read at all** -- the profiler already recorded
  `unreadable_reason`; it was simply never surfaced.

A by-design zero listed beside a mapping failure is how a warning list becomes
noise nobody reads.

---

## 3. Commands this added

```bash
# discovery -- no id needed; lists bundles with held counts as triage order
python manage.py profile_bundle_quarantine
python manage.py preview_quarantine_autopilot --all      # every holding bundle, read-only

# per bundle
python manage.py profile_bundle_quarantine --bundle-id 85    # + zero-yield sections
python manage.py preview_quarantine_autopilot --bundle-id 85 # read-only, three outcomes

# bundles too large to triage on page open (bundle 83)
python manage.py remediate_quarantine_batch --bundle-id 83 --dry-run
python manage.py remediate_quarantine_batch --bundle-id 83

# the box
python manage.py check_edge_readiness    # resolves + probes; FAIL / WARN / OK
```

---

## 4. Verification

Re-verified against `origin/main` on 2026-09-02, **after 117 peer commits**:

* All 7 commits are ancestors of `origin/main`; every change survived.
* **38 tests pass** in an isolated worktree at `origin/main` (9+6+5+5+13 -- every
  test in all five new modules).
* **65/65 boundary gates green** on `origin/main`, real exit code.
* Behavioural probes still answer correctly: bundle 85's real artifact still
  clears; the `.csv`/`.xlsx` fail-open stays closed; loopback split correct.
* All four management commands register.

Every fix is mutation-proven -- the guard removed, the predicate inverted, the
cap deleted -- and each turns its tests red.

---

## 5. Deployment risk

**Render was last seen on `0409f3397`.** Every fix above is unshipped, including
the page-open budget -- so **bundle 83's held-review page will still hang a worker
on the live box.** The code is correct and on `main`; it needs a deploy. Confirm
with `echo $RENDER_GIT_COMMIT` and check whether auto-deploy is enabled.

---

## 6. Open -- decisions, not code

1. **Duplicate upload.** `specialties` and `subjects` each arrived as BOTH `.csv`
   and `.xlsx` with identical row counts and **zero** held rows. Either the
   landers upserted by identity (benign) or the data double-imported. No queue
   would ever show this. Check: `Subject.objects.count()` -- 121 clean, 242 not.
2. **Route PDFs through `is_derived_report`.** The export tool emits `school_stats`
   as both PDF and XLSX. The XLSX is correctly skipped at classification; the PDF
   is not, and instead yields 88 rows of page furniture that autopilot cleans up
   afterwards. Fixing at source changes classification for every tenant.
3. **`QUARANTINE_RECORD_CAP` retention.** Rows beyond the cap still leave only a
   count. Storage / retention / PII decision.
4. **The narrow `school_stats` case in `row_is_unstructured_text_fragment`.** It
   keeps the non-PDF escape, but far more strictly. Tested: the realistic
   unmapped-CSV shape is **safe**; only a pre-flattened dotted-key row slips
   through, and there is no evidence that shape occurs. Closing it would also
   start holding genuinely-empty rows in `school_stats*.csv`. Cost/benefit call.

---

## 7. Process hazards worth fixing

Two cost real time this session and will recur:

* **The shared checkout.** A peer reset the index between a `git add` and a
  `git commit`; git reported both *"no changes added to commit"* and *"ahead by 1
  commit"*, neither true. Nothing was lost, but trusting either message would have
  dropped work. Peers' uncommitted edits also failed gates on unrelated pushes,
  and untracked peer files aborted a merge. **An isolated worktree per agent
  removes this entire class of problem.**
* **Piped exit codes.** `git push ... | grep | tail` returned the pipe's status:
  a push that was rejected with `cannot lock ref` reported **exit code 0**. Same
  trap as `pytest | tail`. Write to a log and echo `$?`.

---

## Related

* `docs/MIGRATION_CLOUD_ZERO_TOUCH_IMPORT_SPEC.md` -- all 6 hard rules now checked
* `docs/audits/ZERO_TOUCH_AUTOPILOT_AUDIT_2026_08_28.md` -- the four findings that
  preceded this read
* `docs/OLLAMA_OPERATIONS_AND_UPDATES.md` -- the Linux/Docker trap, both halves
