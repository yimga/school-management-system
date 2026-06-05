# AI Agentic Actions — Design & Safe Rollout

**Status:** **Phase 1 IMPLEMENTED (read-only), flag-gated default-off** (2026-06-05).
Phases 2–3 remain design-only pending the Open Decisions in § 4.
**Author:** platform AI validation audit, 2026-06-05.

## Phase 1 — as shipped (2026-06-05)

Read-only agentic insights, gated by `RMC_AI_AGENTIC_ENABLED` (default off) **and**
the platform AI gate (`RUNMYCAMPUS_AI_ENABLED` + tenant `ai_policy`). All four gaps closed:

- **G1/G2** — the kernel self-seeds specs (`services/ai_agentic.py::_seed_default_actions`)
  and the read-only runner bridge (`services/ai_agentic_runners.py`) binds 3 of them
  (attendance summary, outstanding-fees summary, draft-only announcement).
- **G3** — orchestration in `services/ai_agentic_service.py`: `agentic_phase1_enabled`,
  `available_readonly_actions` (read-only ∩ bridged only), `propose` (drops any
  non-read-only / unbridged proposal — even if the LLM/mock names one), `execute`
  (hard-refuses non-`read_only` impact, binds the read-only runner, sets
  `ctx.confirmed_by` **server-side** from the authenticated user, never the body).
  Operator surface at `/super/ai-center/agentic/` (`apps/apicenter/views_ai_center_super.py::ai_center_agentic`,
  super-access gated), propose→execute two-step, off-state explains how to enable.
- **G4** — durable append-only audit: `apps/platform_runtime/models_agentic_audit.py::AIAgenticActionAudit`
  (migration `0080`), one row per attempt (ok/blocked/error), actor + params hashed,
  no PII; surfaced as a most-recent-first tail on the operator page.

Tests: `apps/platform_runtime/tests/test_ai_agentic_phase1.py` (gates, read-only
filter, mutating-refusal, server-side confirm, audit append-only).

**Phase 1 below is the original design; it now reflects what shipped.**

---

**Original status:** Design (no wiring). **Author:** platform AI validation audit, 2026-06-05.
**Subject:** how to safely make `services/ai_agentic.py` (+ `ai_agentic_runners.py`,
`ai_agentic_runners_mutating.py`) live. Today the kernel exists and is well-built,
but **nothing invokes it** — no actions are registered, no runners are bound, and
no UI surface calls `propose_actions` / `execute_action`. It is inert.

This document exists because wiring "AI executes actions" is a **security decision**,
not a mechanical fix. Do not wire any mutating path without the gates below.

---

## 1. What already exists (verified)

The kernel in `services/ai_agentic.py` is sound and already encodes the right model:

- **Impact tiers** (`:36-38`): `read_only` / `mutating` / `destructive`.
- **Declarative `ActionSpec`** (`:41-51`): `required_roles`, `reversible`,
  `requires_confirmation`, `parameters` — every action self-describes its risk.
- **`register_action` registry** (`:54-60`): apps register specs at startup.
- **`verify_permission`** (`:200-208`): blocks when the caller's roles don't
  intersect the action's `required_roles`, before any runner runs.
- **`propose_actions`** (`:215-249`): mock keyword router by default; live mode
  routes through `services.ai_helpers.invoke_json_task` (gateway boundary honored,
  `:11-13`). Live proposals are dropped unless the action name is registered
  (`_parse_helper_response` `:304`).
- **`execute_action`** (`:326-…`): refuses to run when the action is unregistered,
  fails `verify_permission`, OR `requires_confirmation` is true and
  `ctx.confirmed_by` is empty (`:339-359`). Takes an injectable `runner` and
  `audit_sink`.

**Core guarantee, already in code:** the agent *proposes*; a human *confirms*;
a runner *executes*; permission is verified first. This is the correct shape.

## 2. What is missing (the 4 gaps that keep it inert)

| Gap | Today | Needed to go live |
|---|---|---|
| **G1 — no registered actions** | `_REGISTRY` is empty at startup; the mock map names actions (`summarize_attendance_report`, `mark_student_absent`, `apply_fee_waiver`, …) that are never `register_action`'d | An `AppConfig.ready()` that registers a curated `ActionSpec` set, each with correct impact + `required_roles` from `apps.platform_runtime.role_registry` |
| **G2 — no runners** | `execute_action(runner=…)` is injectable; the only runners live in `ai_agentic_runners*` which nothing wires | A runner dispatch map binding each registered action to a real, idempotent implementation (read-only first) |
| **G3 — no UI / confirm flow** | nothing calls `propose_actions`/`execute_action` | A copilot surface: prompt → proposals list → explicit per-action **Confirm** → execute, with `ctx.confirmed_by = request.user.id` set ONLY on the confirm POST |
| **G4 — no audit persistence** | `audit_sink` is a callable param; no sink provided | A durable, append-only audit row per proposal + execution (actor, action, params hash, impact, verdict, reversed?) |

## 3. Safe rollout — phased, flag-gated

A single feature flag `RMC_AI_AGENTIC_ENABLED` (default **off**) gates all of it.
Each phase ships only after the prior one is validated in staging.

### Phase 1 — read-only only (low risk)
- Register **only `impact=read_only`** actions (summaries: attendance, outstanding
  fees, etc.). `requires_confirmation=False` is acceptable for read-only.
- Surface in the copilot as "suggested insights." No mutation path compiled in.
- Audit every proposal + execution (G4) even though read-only — establishes the
  audit habit before any write exists.

### Phase 2 — mutating, with mandatory human confirm (medium risk)
Gate every `impact=mutating` action behind **all** of:
1. `requires_confirmation=True` + the UI's two-step confirm (proposal → explicit
   Confirm button); `ctx.confirmed_by` set server-side from `request.user`, never
   from the client payload.
2. `required_roles` populated from `role_registry` and enforced by
   `verify_permission` (already does this) **and** re-checked at the view layer.
3. `reversible=True` only — irreversible actions are **not** eligible in Phase 2.
4. Per-tenant scope check: the action's target must belong to `request.school`
   (reuse the platform tenant-isolation guard; the kernel's `ActionContext` already
   carries `tenant_id`).
5. Durable audit row written **before** the runner executes and updated after.
6. Rate limit + the existing AI budget gate.

### Phase 3 — destructive (high risk) — dual control
- `impact=destructive` actions require **two distinct approvers** (mirror the
  existing dual-control pattern used for tenant offboarding / purge), a typed
  confirm phrase, and a reversal/runbook entry. Default: **not enabled** until a
  named owner signs off.

## 4. Open decisions (need an owner before Phase 2)
- **Which actions** are in scope, and their exact `required_roles` per
  `role_registry`. (Proposed read-only starter set: attendance summary, fees
  summary, draft-only announcement — drafting is read-only since it doesn't send.)
- **Audit model**: new `AIAgenticActionAudit` (append-only, like the migration_cloud
  audit log) vs. reuse an existing audit table.
- **Runner ownership**: confirm `ai_agentic_runners.py` is the intended runner home
  and bring it under test against the registry, or replace it.
- **Reversal**: for each mutating action, define the undo path (required by the
  `reversible` contract).

## 5. Explicit non-goals / guardrails
- **Never** set `ctx.confirmed_by` from request body — only from the authenticated
  session on an explicit confirm action.
- **Never** let live `propose_actions` execute directly — propose and execute are
  separate HTTP round-trips with a human in between.
- **Never** register a `destructive` action without dual-control + owner signoff.
- The kernel must keep routing AI through `services.ai_helpers` only (boundary
  scanner enforces; do not regress).

## 6. Recommendation
The kernel is good and the security model is right. Recommend: **build Phase 1
(read-only) only** as the next concrete step — it delivers value (copilot
insights) with no mutation risk and exercises the registry + audit plumbing.
Phases 2–3 require the Open Decisions above to be owned first. Until then,
`ai_agentic*` stays inert (it does not affect any working AI surface).
