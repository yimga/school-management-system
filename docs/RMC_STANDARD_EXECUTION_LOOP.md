# RunMyCampus standard execution loop

**Status: non-negotiable principle. Applies to every request, from a one-line fix to a
platform-wide wave. There is no "small enough to skip the loop" task.**

This document is the canonical prompt. When the operator asks for work, this is the
shape the work takes — not because a checklist is nice, but because every expensive
defect this codebase has shipped came from skipping one of these steps.

---

## 0. The product thesis the fixes serve

Every decision below resolves against what RunMyCampus is trying to be:

> **The AWS / Linux / Shopify / Salesforce of education and school management.**

- **AWS** — primitives, not features. A capability lands as a composable, governed
  service other surfaces build on, with an audit trail and a rollback path.
- **Linux** — sovereign and inspectable. It runs on the school's own hardware if the
  school wants it to. No capability may depend on a rail the tenant cannot own.
- **Shopify** — the tenant configures a business, not a database. Setup is a product
  surface with previews, impact analysis, and a safe apply.
- **Salesforce** — everything is configurable per tenant through one cascade, and
  everything is governed by roles, approvals, and an audit log.

**Three pillars are load-bearing and outrank convenience in any trade-off:**

1. **Local-first** — the tenant's data and the tenant's decisions live with the tenant.
2. **Global presence** — currency, locale, corridor, and regulatory posture are
   per-tenant inputs, never platform defaults leaking through.
3. **Offline mode** — a school with intermittent connectivity is a first-class user,
   not a degraded one. Queue-and-forward, not "please reconnect".

A fix that scores well on the checklist but weakens a pillar is not a fix.

---

## 1. AUDIT FIRST — always, before touching anything

**Never start from the request's framing. Start from ground truth.**

- **Run the thing.** Execute the engine, hit the route, render the template, print the
  computed value. Reading the code tells you what it was meant to do; running it tells
  you what it does. Most of this codebase's worst findings inverted the reported
  symptom once actually executed.
- **Read line by line** in the blast radius. Not the summary, not an agent's report of
  the file — the file. Agent summaries have been wrong here before.
- **Assume nothing is what its name says.** A gate named `verify_x` may not verify x. A
  bar labelled "readiness" may be a literal. A test named `test_blocks_y` may assert on
  a path that cannot execute.
- **Write the audit down** with the evidence that produced each finding, so the
  re-audit in step 5 has something to check against.

**Report what the audit found even when it contradicts the request.** "You asked me to
unblock apply; nothing was blocking apply, the meter was unreachable" is the most
valuable output an audit can produce.

## 2. IDENTIFY — classify every finding before fixing any

For each finding record: *what is broken*, *what the user-visible consequence is*, and
*what proves it*. Then classify:

| Class | Meaning | Bar to close |
|---|---|---|
| **Blocker** | A user cannot complete the job | Fixed + must-fire test |
| **Dishonesty** | A number/label/status that measures nothing | Replaced with a computed value + a test that it can move |
| **Dead guard** | A check that structurally cannot fire | Rewritten + a **must-fire** test |
| **Gap** | Real behaviour with no test | Test added, and it must fail before the fix |
| **Improvement** | Works, could be better | Applied in step 6 |

**A negative test never detects a dead guard.** If a guard matters, there must be a test
that proves it *fires*, not only one that proves the happy path passes.

## 3. FIX — against the thesis, not against the symptom

- Fix the **cause**, at the lowest layer where it is wrong. If two surfaces show the
  same defect, the contract underneath them is the defect.
- **No hardcoding.** Every value routes through the 7-layer configurability contract.
  A literal on a meter, a static tuple no tenant can satisfy, a count pinned to `0` —
  these are the same bug wearing different clothes.
- **N/A is not credit.** A check that does not apply to a tenant leaves the
  denominator; it is never silently marked satisfied. Inferring "fine" from silence is
  the dishonesty being fixed.
- **Clean up.** No `# removed` comments, dead vars, orphan CSS, unused imports.
- **Never widen scope silently.** If the fix implicates 100 templates, say so and name
  the strategic subset before sweeping.

## 4. TEST — until everything passes, before any commit

- **Every fix carries a test**, and the test must fail against the pre-fix code. A test
  that passes both ways proves nothing.
- **Run the full affected suites**, not just the new file. Then the boundary gates:
  `python scripts/pre_push_boundary_check.py`.
- **Use the private test lane** when other agents are active, so shared-DB lock
  contention doesn't manufacture phantom failures:
  ```
  cp .django_test_dbs/default.sqlite3 .django_test_dbs/<lane>.sqlite3
  DJANGO_TEST_DB_FILE=.django_test_dbs/<lane>.sqlite3 python manage.py test <labels> \
      --settings=config.settings --keepdb
  ```
  Always pass explicit test labels — a bare `manage.py test` crashes on the `emis/`
  collision.
- **A red test is a finding, not an obstacle.** Before "fixing" a test, prove the test
  is wrong. Red tests have been right here more often than they have been stale.
- **Green is the gate for committing.** Not "green except", not "unrelated failure".
  If something is genuinely out of scope, say so explicitly and in writing.

## 5. RE-AUDIT — prove the fix landed, from scratch

Re-run **the original audit**, not a check of your own diff. The re-audit answers:

- Is every finding from step 1 actually closed, verified by the same method that found it?
- Did the fix introduce a new one?
- Do the numbers now reach their honest ceiling, and can they still *move*? (A meter
  pinned at 100 is as dishonest as one pinned at 72.)
- Is the surface deployed, or merely merged? **Auto-deploy is OFF.** "Fixed" and
  "live" are different claims — never conflate them.

**Any residual found here is worked to closure in this same pass.** The loop does not
exit with known-open findings; it exits with them fixed or explicitly, visibly deferred
with a reason.

## 6. IMPROVE — apply what the audit surfaced beyond the ask

Once the defects are closed, apply the applicable improvements the audit exposed —
consistency with the premium surface grammar, missing tests around adjacent paths, a
seal that prevents the whole defect class from returning. Prefer a **permanent seal**
(a CI gate, a contract-hygiene test) over a one-time fix: the goal is that this class of
bug cannot silently come back.

## 7. REPORT — faithfully

State what was found, what was fixed, what was tested and how, what remains, and what
the operator must do (deploy, credentials, approval). Never report completion for work
that is merely written. If a step was skipped, say which and why.

---

## Working alongside other agents

This repo routinely has parallel agents and sweepers on the same branch.

- **Do not disturb in-flight work.** If another agent owns a module, let it finish.
- **Come back and verify.** Their completion is a claim; re-audit it against ground
  truth and confirm the module actually reached its ceiling.
- **Commit small and promptly** — peer sweepers have auto-committed in-flight files
  under their own messages. Verify authorship post-hoc with
  `MSYS_NO_PATHCONV=1 git show HEAD:<path>`.
- **Triage a dirty tree by content before any stash or merge.** Never
  `checkout --`/`rm` your way out of one.

---

## The one-paragraph version

> Audit first and run the thing — never trust the framing, the name, or a summary.
> Classify every finding by user-visible consequence. Fix the cause at the lowest wrong
> layer, aligned to local-first, global presence, and offline mode. Test until green,
> with a test per fix that fails before it. Re-audit from scratch and close residuals in
> the same pass. Then apply the improvements and seal the defect class. Report honestly,
> including what is merged but not deployed.
