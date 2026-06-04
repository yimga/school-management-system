# Platform Health — connective tissue (registries → AI workflow dock)

**Date:** 2026-06-03
**Status:** design + initial implementation (this wave)

## Why

The platform has three healthy-but-orthogonal accountability systems
(documented in depth via the registries explainer):

1. **Feature-Gap Register** (`apps/schools/feature_gap_register.py`) — the
   *promise* layer. Each `shipped` row names a proof (`proof_route_name` /
   `proof_model` / `proof_management_command` / `proof_ci_gate`). A test
   (`test_feature_gap_register.py`) fails when a shipped proof stops resolving.
2. **Backlog Registry** (`apps/platform_runtime/backlog_unlock_registry.json` +
   `backlog_unlock_engine.py`) — the *readiness* layer. Items "unlock" when
   their script/pytest criteria pass; an SLA marks items that sit too long in
   `waiting` / `ready_attention`.
3. **Assist Dock + Workflow Progress Bus** (`apps/assist_dock/*`,
   `apps/platform_runtime/views_workflow_progress.py`) — the *runtime UX* layer,
   the bottom-right floating rail.

They never talked to each other. A "shipped" feature whose route 500s, or a
backlog item that blew its SLA three weeks ago, was only visible if someone
*ran the test* or *opened the right dashboard*. Nothing surfaced it to the
operator **where they already are** — the dock.

This wave adds the **Platform Health** connective tissue: one operator-facing
aggregation that the bottom-right dock surfaces live, with a one-click action
that re-checks a broken feature-gap proof **as a tracked workflow** — so the
re-check itself shows up in the workflow chip. That's all three layers wired
into one loop.

## What it connects (and the constraints that shaped it)

| Source | Signal surfaced | How it's read (and why) |
|---|---|---|
| Feature-Gap Register | `shipped` rows whose proof does **not** resolve right now ("broken promises") | Resolved **in-request** — `reverse()` and `apps.get_model()` are cheap and side-effect-free. Mirrors the logic already in the manager feature-gap view, extracted into a reusable helper. |
| Backlog Registry | items currently **over SLA** (`sla_waiting_breached` / `sla_ready_attention_breached`) | Read from the **cached snapshot** (`snapshot_cache_key`) only — **never** `evaluate_all()` in a web request, because that shells out to scripts/pytest. If no snapshot is cached (eval never ran), Platform Health reports 0 backlog breaches and says so. |
| Workflow Progress Bus | the one-click **re-check** run | `begin_run` / `workflow_step` / `finalize_run` — **synchronous**, DB-backed, no threads, no subprocess. The re-check re-resolves a single feature-gap proof in milliseconds and appears in the workflow chip + history. |

### Hard rules honored
- **No subprocess / no `evaluate_all` in request path.** Backlog data is cache-only.
- **No threads in the request path.** (The existing `e2e_demo` thread spawner is
  DEBUG/env-gated; we don't add to that surface.) The re-check is synchronous.
- **Staff/operator-only.** The badge resolver returns `None` for non-staff; the
  center page is `@staff_member_required`; the quick action and dock slot are
  scoped to the `manager` surface (the control plane = the operator surface).
- **No hardcoding.** Severity thresholds + the workflow key are module constants;
  role/surface use the assist-dock + registry SOTs.
- **Graceful degradation.** Every cross-module read is wrapped so a missing
  cache, an unimportable model, or a malformed snapshot yields an empty/zeroed
  result, never a 500 — matching the dock context processor's defensive style.

## Components (this wave)

```
apps/platform_runtime/platform_health.py          # pure service (the real logic)
  ├─ feature_gap_broken_proofs()  -> list[BrokenProof]   (in-request, cheap)
  ├─ backlog_sla_breaches()       -> list[BacklogBreach] (cache-only)
  └─ platform_health_summary()    -> {feature_gap_broken, backlog_breaches, level}

apps/platform_runtime/views_platform_health.py
  ├─ platform_health_center        (GET, staff)  -> operator Decision Console page
  ├─ platform_health_badge         (GET, staff)  -> JSON {count, level, dot}
  └─ platform_health_recheck       (POST, staff) -> runs a tracked re-check workflow

apps/platform_runtime/urls.py                     # 3 routes under platform_runtime:
  platform_health_center / platform_health_badge / platform_health_recheck

apps/assist_dock/default_slots.py                 # + platform-health chip (manager surface)
apps/assist_dock/default_badges.py                # + platform_health badge resolver
apps/assist_dock/default_quick_actions.py (new)   # + one-click link to the center page

templates/platform_runtime/platform_health_center.html

apps/platform_runtime/tests/test_platform_health.py
```

### Severity contract
`platform_health_summary()["level"]`:
- **critical** — any broken feature-gap proof (a *shipped promise* is currently
  broken; this is the most serious signal).
- **warning** — no broken proofs but ≥1 backlog SLA breach.
- **success** — everything resolves and no SLA breaches.

The badge pill uses the same level; the dock paints no pill when count is 0
(matching the existing resolvers, which return `None` rather than a noisy `0`).

## Deliberate non-goals (this wave)
- **No autonomous gap *closing*.** Re-check verifies + re-surfaces; it does not
  attempt to fix code. (Auto-fix already exists for workflow failures via
  `workflow_fix_handlers`; wiring gap-closure playbooks into that is a future
  wave.)
- **No new `WORKFLOWS` seed entry.** `begin_run` degrades gracefully
  (label = title-cased key, empty route), so we use the key
  `platform_health_recheck` without editing the curated workflow-registry seed
  SOT (which has its own audit + count assertions).
- **No live backlog re-evaluation from the dock.** That stays the job of
  `python manage.py evaluate_backlog_unlocks --update-cache` (CLI/beat). The
  center page deep-links to each item's `doc_href` + shows its `action_hint`.

## Operational caveat — the backlog half is dark until the beat is on

The backlog SLA signal reads the **cached** snapshot, which is only populated by
`evaluate_backlog_unlocks --update-cache`. That runs on a daily Celery beat
(`backlog-unlock-evaluate-cache`) **only when `ENABLE_BACKLOG_UNLOCK_BEAT=1`** —
opt-in, default-off (and the free-tier deploy keeps beats minimal). So out of the
box Platform Health shows broken feature-gap proofs but **zero backlog breaches**,
and the center page renders an explicit "no snapshot cached — run … / set
`ENABLE_BACKLOG_UNLOCK_BEAT=1`" notice rather than implying a clean bill of
health. Enabling the beat (or running the command once) lights up the backlog
half.

## Performance note

`platform_health_summary(use_cache=True)` (used by the badge resolver, which runs
on every dock poll / SSE tick) serves a 45s-TTL cached copy so the ~45-feature ×
`reverse()` scan doesn't run every tick per staff tab — relevant given the
free-tier SSE thread budget. The center page and the one-click re-check compute
fresh; the re-check busts the cache so the badge updates promptly.

## Future waves (the loop this opens)
- Broken-proof → AI remediation playbook (route the broken proof through
  `services.ai_helpers` to draft the fix), surfaced as a real dock AI action.
- Over-SLA backlog item → one-click "enqueue re-evaluation" as a Celery-backed
  tracked workflow (so even the expensive eval shows in the chip).
- Promote Platform Health from a chip to a first-class operator SLO panel.
