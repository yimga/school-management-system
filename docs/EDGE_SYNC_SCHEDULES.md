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

### The idle ceiling — the one place this does not do exactly what was typed

A tenant who asks for "06:00 and 18:00 only" still gets a check-in at most
`RMC_EDGE_SYNC_IDLE_CEILING_SECONDS` apart (default **3600**). `EdgeSyncDirective` is the
only cloud→box channel and it is collected by the box ASKING. A box that goes twelve hours
without asking cannot receive the operator's "Queue full resync" for twelve hours, and from
the cloud it is indistinguishable from a box that has been switched off.

Raise the ceiling if a tenant genuinely wants twice-daily-and-nothing-else, and accept that
operator instructions will queue for that long.

### Missed windows — catch up once

If the box was off or offline through a scheduled moment, it runs once when it comes back
and then resumes. One catch-up, not one per missed moment: the state is a single next-due
marker, so a weekend outage produces one run on Monday rather than forty-eight.

The Sync Center shows a missed window explicitly, because "next sync: 6:00 PM" beside a
last sync three days old is exactly the state a next-run label would otherwise paper over.

---

## Time is the school's, not the server's

"06:00" means six in the morning where the school is. Rules store `time` values and a
weekday set and are resolved against `School.timezone` at evaluation time — never stored
as UTC instants, which would silently shift by an hour twice a year.

**DST, decided and asserted in both directions:**

- **Spring forward.** A rule at a wall-clock time the day skips (02:30, where the clock
  jumps 02:00 → 03:00) fires at the first instant that DOES exist. It is never dropped — a
  nightly report that silently skipped one night a year would be blamed on anything but
  the clock.
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
| `RMC_EDGE_SYNC_IDLE_CEILING_SECONDS` | `3600` | Longest gap between check-ins when no scheduled run is due |
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
- **`RuntimeDefaults` first-class field for the idle ceiling.** It is an env var today,
  which is layer 2 of the configurability cascade; promoting it to the tenant cascade needs
  the full first-class-field chain and is a follow-up.
