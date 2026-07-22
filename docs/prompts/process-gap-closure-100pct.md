# Prompt — Process-gap closure 100% (provision / heal / MFA / topology)

**Acceptance:** 100% of listed P0–P2 items closed with code + named tests. Partial = FAIL.

## Non-negotiable rules

1. No multi-minute work on HTTP (migrate, bundle advance, schema heal).
2. Heal must mutate real stuck/dead-running states — never Diagnostic-only for provision.
3. Hard requirements (MFA) are wizard steps before “done”; middleware is backstop.
4. Topology honesty: broker without live beat/worker ⇒ red health (or in-process heal stays on).
5. One active provision run per school: cancel/claim before kick.

## Checklist (must all be DONE)

### P0
- [x] Broker set + stale/missing beat ⇒ health red OR in-process heal re-enabled
- [x] `dispatch_provision_school` queue-fail path never calls `provision_school_sync` on caller thread
- [x] Migration Cloud eager/broker-fail never runs `advance_bundle` on request thread
- [x] Watchdog cancels `running` AND `stuck` priors before resume; no dual zombies

### P1
- [x] Flight Deck repair/migrate auto-fix enqueues worker/background job (returns job id + poll)
- [x] Eager topology: failures not silently swallowed for provision heals; beat absence detectable
- [x] MFA is a required owner-onboarding step before done (not only CTA/middleware)
- [x] Autopilot policies seeded for every `STUCK_DEFAULT_FIX_BY_WORKFLOW` executable kind

### P2
- [x] Document + enforce: durable HeavyWorkOutbox (daemon thread only kicks drain)
- [x] Soft or hard single-flight claim before provision begin_run for same school
      (partial unique `uniq_active_provision_run_per_school` + outbox unique)

## Follow-on closure (remaining gaps)

- [x] Durable HeavyWorkOutbox + beat/periodic drain
- [x] Flight Deck heal returns `outbox_id` / `job_id`
- [x] MC operator advance/apply HTTP paths enqueue outbox
- [x] MC tenant repair HTTP path enqueue apply (`off_http=True`)
- [x] MC connector import HTTP path enqueue advance+apply chain
- [x] DB one-active provision constraint (after duplicate cleanup)
- [x] Student-transfer async FSM (`off_http` + APPLYING continue sweep)
- [x] MFA owner-onboarding step renders wizard chrome (not bare redirect)
- [x] `retry_failed_step` re-drives MC via outbox / Celery / stamp-running
- [x] SOT §11.4 + autonomous execution log

## Proof

Named tests: `apps/schools/tests/test_process_gap_closure_100pct.py`,
`apps/schools/tests/test_provisioning_dispatch.py`, healthz/periodic/scheduled_job_health updates,
`apps.accounts.tests.test_owner_onboarding_mfa_cta`, `apps.people.tests.test_transfer_async_continue`.

