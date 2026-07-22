# Prompt — World-class tenant-schema provisioning + mandatory self-heal

**Use when:** provisioning stalls at `tenant_schema` (“Preparing your campus workspace”), Recovery intelligence shows **Auto fix: Diagnostic only**, or self-heal does not remediate.

**Non-negotiable:** Auto fix must **execute** repairs (mutate schema + requeue). Diagnostic-only is a defect, not a product mode.

---

## Mission

Make school provisioning spotless at the **tenant schema** layer. Operators and owners must never wait forever on a dead `running` row. Self-healing is **required**, not optional.

## Symptom contract (what “broken” looks like)

| Field | Bad (forbidden) | Good (required) |
| --- | --- | --- |
| State | `Running` forever at `tenant_schema` with frozen/missing heartbeat | Flips to `stuck` within ~`PROVISION_RESUME_STALE_SECONDS` (~120s), or watchdog resumes |
| Auto fix | `Diagnostic only` | Executable kind (`requeue_provision`) + healing chain `repair_tenant_schema_drift → requeue_provision` |
| Apply | Missing / no-op | Apply runs healing chain and re-drives provisioning |
| Autopilot | Shadow-only / never applies | `WorkflowAutopilotPolicy` enables `requeue_provision`; stuck/failure paths call **healing chain**, not a single blind requeue |
| Watchdog | Blind to dead `running` | Heartbeat + wall-clock liveness; cancel zombie; kick idempotent resume |

## Root causes to seal (do not regress)

1. **Dead `running` ≠ failed/stuck** — UI remediation used to upgrade only `failed|stuck|cancelled`, so heartbeat-dead `running@tenant_schema` showed Diagnostic only.
2. **Stuck sweep too slow for provision** — `1.5 × 600s` expected left operators waiting ~15 minutes; provision must use watchdog stale window.
3. **Requeue without schema heal** — requeue alone leaves partial/missing tables; chain must repair drift first.
4. **Autopilot applied a single kind** — must run `apply_healing_for_run` so repair steps execute.
5. **Web-only topology** — `/health/`-tick `schools.resume_stuck_provisions` must keep firing without Celery beat.

## Implementation checklist (agent must execute, not narrate)

1. `resolve_effective_remediation` — dead `running` provision runs (via `provision_workflow_run_is_live`) get executable remediation + `healing_chain` when step is `tenant_schema`.
2. Classifier / healing overrides — `tenant_schema` step → `repair_tenant_schema_drift` then `requeue_provision`.
3. Taxonomy — schema already-exists / missing-relation → `auto_fix_available=True` (never diagnostic-only for provision).
4. Stuck sweep — provision uses `provision_resume_stale_seconds`; include null heartbeats; stamp stuck remediation; `try_auto_apply_on_stuck` uses healing chain.
5. Failure autopilot — `try_auto_apply_on_failure` uses healing chain when supported.
6. `run_tenant_migrations` auto-fix — schema-scoped via `schema_context` when `tenant_schema` known.
7. Watchdog — heartbeat + wall-clock; single-flight resume; periodic registry wired.
8. Detail UI — Auto fix shows kind + chain when available; never blank Diagnostic when `auto_fix_available`.
9. Tests — dead-running remediation, tenant_schema classifier chain, flight-deck Apply, watchdog suite.
10. Proof — named tests green; no “Diagnostic only” for dead provision@tenant_schema.

## Proof commands

```bash
python scripts/run_sqlite_memory_tests.py \
  apps.platform_runtime.tests.test_workflow_flight_deck \
  apps.platform_runtime.tests.test_workflow_error_classifier \
  apps.platform_runtime.tests.test_stuck_autopilot \
  apps.schools.tests.test_provision_watchdog \
  apps.platform_runtime.tests.test_provisioning_autopilot_policy
```

## Definition of done

- Recovery intelligence on a heartbeat-dead `running` / `stuck` provision at `tenant_schema` shows **`requeue_provision`** (and healing chain), never Diagnostic only.
- Apply / autopilot **repairs schema drift then requeues**.
- Watchdog or stuck sweep recovers without an operator within the stale window when policy is enabled.
- No new parallel strategy docs — record proof in SOT §11.4 + autonomous log only after green tests.

## Banned outcomes

- Leaving Auto fix as Diagnostic only for tenant_schema stalls.
- Requeue-only “heal” that skips schema repair when tables/columns are missing.
- Claiming self-heal works when status stays `running` with a dead heartbeat and no remediation.
