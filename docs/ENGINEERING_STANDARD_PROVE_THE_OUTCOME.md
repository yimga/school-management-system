# Prove the outcome, not the mechanism

*Adopted 2026-08-20, after four defects of the same shape were found in one day.*

## The rule

> **A health signal must prove the outcome it claims. Proving that the mechanism
> exists is not the same thing, and is the single most expensive class of bug this
> platform has shipped.**

Every instance below passed its own check, reported success, logged nothing, and
cost a tenant real time. None of them raised an exception. That is the whole
danger: this defect class is *silent by construction*, so it is never found by
watching for errors.

## The four instances

| Check | What it proved | What it claimed | What actually happened |
|---|---|---|---|
| `check_edge_readiness` crypto key | The env var is non-empty | "At-rest encryption key is set" | A 15-byte key. `Fernet(key)` raises on every write. Booted clean for weeks. |
| `redrive_dead_letters` | A durable queue exists | "Nothing is dropped" | Redrive delivered through the console backend, marked each row sent, reached nobody. |
| `applying_stale_by_time` self-heal | The apply stopped heartbeating | "Recover the wedged import" | No ceiling. A 44-second import re-ran ~48 times in 24 hours. |
| `_import_flight` | An outbox row is open | "An import is running" | One orphaned row pinned a *completed* import at "Running", then "Failed (Stuck)". |

Read the middle column again. Every one is *true*. The check was not lying about
what it measured — it was measuring the wrong thing.

## What "prove the outcome" means in practice

**Construct the thing.** Don't read the setting that configures it.
`Fernet(key)` — not `if key:`. `mail.get_connection()` and ask whether that
backend can deliver — not `if EMAIL_BACKEND:`.

**Every retry loop declares its ceiling.** A self-heal that cannot give up is not
a self-heal. State the maximum, count attempts durably, and define the terminal
state reached at the ceiling. "It will recover eventually" is not a design.

**Every state machine verifies it landed.** After writing a terminal status,
re-read it. If the persisted value is not terminal, that is an ERROR-level event
naming the status that survived — not a silent return.

**Absence and success must not look alike.** An all-zero summary that means
"blocked" is indistinguishable from one that means "nothing to do". If a
degraded path returns the same shape as the happy path, say so explicitly in
the output.

**Nothing accumulates without a retention policy.** Succeeded rows, events,
snapshots. Five rows for one import reads as five imports.

## The debugging doctrine

**No mechanism claim without a state read.**

Code can prove a bug is *possible*. Only production state proves it is
*happening*. During this investigation a plausible, arithmetically sound
worker-recycle theory was written up before a single row was queried — and it was
wrong. The row states pointed somewhere else entirely.

The order is:

1. **Read the state first.** One cheap read-only query beats a page of reasoning.
2. **Timestamps are the story.** The gap between "apply finished 20:32:40" and
   "apply started 21:03:25" was 1845s. `_APPLYING_STALE_SECONDS` is 1800. That
   single subtraction was the diagnosis.
3. **A theory that explains some evidence is not a diagnosis.** Four applies had
   status `succeeded`. Any theory requiring them to have died was already dead.
4. **Say when you were wrong, immediately and plainly.** A wrong theory left
   standing costs more than the time to retract it.

## Definition of done

A fix in this class is not done until:

- [ ] The check constructs or exercises the real thing, not its configuration
- [ ] Every loop it touches has a stated, tested ceiling
- [ ] The failure path is distinguishable from the success path in the output
- [ ] There is a test that **fails against a planted mutant** restoring the old
      behaviour — a passing test proves nothing about what it would catch
- [ ] The tenant-facing message says what happened, what it means for their data,
      and what to do next
- [ ] Pre-existing tests over the same surface still pass, and the count is reported

## Using this as a prompt

Paste from **The rule** through **Definition of done** ahead of any audit,
review, or debugging task. Then add:

> Apply this standard to <area>. For every health check, status field, retry
> loop, and progress indicator: state what it proves, what it claims, and
> whether those are the same. Read production state before asserting any
> mechanism. Report the gaps you find with the evidence for each, and say
> explicitly which claims you could not verify.
