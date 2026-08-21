# Tenant sync schedules

How a school decides when its box syncs, and why the design looks the way it does.

Surface: **Sync Center → Sync schedule**. Code: `apps/sync_engine/schedule.py` (the
evaluator), `apps/sync_engine/models_schedule.py` (the rows),
`apps/sync_engine/schedule_policy.py` (precedence + the display summary),
`apps/siteconfig/forms_sync_schedule.py` (the editor).

---

## What a tenant can set

Two shapes, both readable back in plain English:

| Mode | Means | Example |
|---|---|---|
| `INTERVAL` | Every N minutes, inside a window, on chosen days | *Every 30 minutes, 7:00 AM to 6:00 PM, Monday to Friday* |
| `AT_TIMES` | Once at each listed time, on chosen days | *At 6:00 AM and 10:00 PM, every day* |

A tenant may hold several rules and the schedule is their union — term time and school
holidays are two rules, not two products. Overnight windows are supported: `22:00–02:00`
is one window that belongs to the day it OPENS on.

**Not cron.** The person filling this in runs a school. `0 */2 7-18 * * 1-5` is not
something they should ever see, and a field that accepts it will be filled in wrong.

## The default: nothing

A tenant who never opens the screen gets the adaptive cadence exactly as before this
feature existed — continuous, faster when there are changes, backing off when the cloud is
unreachable. `rules_for(school) == []` means *fall back to the adaptive cadence*, and
every caller reads it that way. It never means "do not sync".

---

## Why the cloud cannot just trigger a sync at 09:00

A sovereign box sits behind NAT. **The cloud can never open a connection to it.** Every
transfer is box-initiated. So the schedule has two halves:

- **Authoring** on the cloud, where the tenant administrator is.
- **Execution** on the box, which must already hold the schedule when the moment arrives,
  because at 09:00 nobody is going to tell it.

`SyncSchedule` is therefore replicated like any other row — `client_offline_id` anchor +
`auto_now` `updated_at`, registered in `_DERIVED_ENTITY_SPECS` — and evaluated LOCALLY by
the box against its own copy. That is also what keeps it working while the cloud is
unreachable, which is the entire premise of a sovereign box.

**Consequence, stated rather than hidden:** a schedule change reaches the box on its NEXT
cycle, not instantly. The Sync Center says so in those words, and the status payload
carries the same sentence so every surface tells the same truth. Saving a change also
raises a wake and bumps the change beacon, so "next cycle" is usually seconds — but the
UI does not promise that, because on a box that is asleep or offline it is not true.

---

## Precedence — who wins

| Situation | What wins | Why |
|---|---|---|
| Explicit wake (operator "Sync now", a queued directive, a local write) | the wake | A human asked. Making them wait for a window is how a feature becomes a complaint. |
| Consecutive failures | backoff | A schedule is not permission to hammer a cloud that is down. |
| Inside a configured window | the tenant's interval | Their decision, their deployment. |
| Two overlapping windows | the SHORTER interval | Row order must never decide behaviour. |
| Outside every window | the idle ceiling | Never zero — see below. |
| No schedule | adaptive cadence | The zero-configuration default. |

### The idle ceiling — the tenant's number, with its consequence stated

A tenant who asks for "06:00 and 18:00 only" still gets a check-in in between.
`EdgeSyncDirective` is the only cloud→box channel and it is collected by the box ASKING, so
the ceiling is also the worst case on an operator's "Queue full resync" reaching this box:
twelve hours without asking means twelve hours before an instruction lands, and from the
cloud that is indistinguishable from a box that has been switched off.

Until v4.06.75 this was a deviation the product made silently — the only knob was an
environment variable on a host the school cannot see. It is now set on the Sync Center and
replicated to the box like every other decision here (`SyncPolicy`), and every choice in
the picker states its consequence rather than leaving it to be discovered.

| Resolution order | Source |
|---|---|
| 1 | `RMC_EDGE_SYNC_IDLE_CEILING_SECONDS` — the operator's pin for ONE box. An operator debugging a box in front of them has to be able to hold it still. |
| 2 | The tenant's `SyncPolicy.idle_ceiling_minutes`. |
| 3 | One hour. |

Bounded at **24 hours**. That is a safety limit, not a preference: beyond a day a box
cannot be reached at all. The value is clamped on read as well as on save, so a row from
an older build cannot put a box outside the bounds the surface enforces.

### Missed windows — catch up once

If the box was off or offline through a scheduled moment, it runs once when it comes back
and then resumes. One catch-up, not one per missed moment: a weekend outage produces one
run on Monday rather than forty-eight. A tenant who does not want this can turn it off
(`SyncPolicy.catch_up_missed`) — a 3am job landing at 7am is not always welcome.

The claim is held in the cache and keyed by the missed MOMENT, not inferred from "a run
happened". A cycle that FAILS still writes a run row and would otherwise count as having
made the moment up; a cycle that dies before writing one would otherwise catch up on every
tick. Backoff outranks catch-up, because a box catching up into a cloud that is down is
just the schedule finding another way to hammer it.

> Between v4.06.74 and v4.06.75 this section described behaviour that did not exist.
> `missed_run()` was correct and unit-tested, and nothing called it except the status
> panel's "missed window" flag — so the Sync Center said a sync would be caught up while
> the box waited for the next scheduled time. The function was never the bug; the wiring
> was absent, which is why a passing unit test hid it.

The Sync Center shows a missed window explicitly, because "next sync: 6:00 PM" beside a
last sync three days old is exactly the state a next-run label would otherwise paper over.

---

## Time is the school's, not the server's

"06:00" means six in the morning where the school is. Rules store `time` values and a
weekday set and are resolved against `School.timezone` at evaluation time — never stored
as UTC instants, which would silently shift by an hour twice a year.

**DST, decided and asserted in both directions:**

- **Spring forward.** A rule at a wall-clock time the day skips (02:30, where the clock
  jumps 02:00 → 03:00) still fires, at the instant that wall time would have denoted —
  02:30 EST *is* 03:30 EDT, the same absolute moment under a renamed clock. It is never
  dropped and never drifts by more than the gap; a nightly report that silently skipped
  one night a year would be blamed on anything but the clock.
- **Fall back.** A rule inside the hour the clock repeats fires ONCE, on the first
  occurrence. Firing twice would double a nightly job with no way to tell why.

---

## One implementation of "when is the next run"

`schedule_policy.planned_next_run()` is called by the scheduler to decide AND by the status
endpoint to display. There is deliberately no second implementation: a next-run label
computed by different code than the one that keeps it will drift, and a wrong label is
worse than none because it is the thing the user is planning around.

`apps/sync_engine/tests/test_sync_schedule_surface_2026_08_20.py::
test_15_the_displayed_next_run_equals_the_function_the_scheduler_acts_on` asserts the
displayed value against the FUNCTION, never against a hardcoded expectation.

---

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `SyncPolicy.idle_ceiling_minutes` (tenant, Sync Center) | `60` | Longest gap between check-ins when no scheduled run is due. Bounded 5 min – 24 h |
| `SyncPolicy.catch_up_missed` (tenant, Sync Center) | `True` | Sync once on return after sleeping through a scheduled time |
| `RMC_EDGE_SYNC_IDLE_CEILING_SECONDS` | unset | Operator pin for ONE box; overrides the tenant's ceiling |
| `RMC_EDGE_SYNC_INTERVAL_SECONDS` | unset | Operator pin for ONE box. Predates schedules and still wins — an operator debugging a box has to be able to hold it still |
| `MIN_INTERVAL_MINUTES` | `5` | Floor. A mis-typed "1" must not turn a box into a request loop |

---

## Conflict behaviour on the rail

`sync_schedule` is `causal_lww` and NOT protected. Converging two-way is right here: it is
the tenant's own configuration on their own deployment, and a sovereign box's administrator
may be sitting in front of the box rather than the cloud. Nothing here grants access, moves
money or changes a mark; the worst a stale write can do is sync at the wrong time, which
the next edit corrects. Marking it protected would turn every schedule change made during
an outage into a manual conflict for no safety gain.

---

## Deliberately not built

- **Per-entity schedules** ("students hourly, finance daily"). The model does not preclude
  it — a rule could gain an entity filter — but nothing implements it.
- **Blackout / maintenance windows.**
- **Cloud→box push.** It does not exist (see the NAT section) and inventing it is a
  different project.
- **A DST switch.** There is one defensible answer in each direction, so a setting would
  only let a school choose the wrong one for a decision they should never have to think
  about. The panel SHOWS what will happen instead — visible was the actual problem.
