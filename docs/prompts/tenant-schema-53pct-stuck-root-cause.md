# Why provisioning ALWAYS stuck at ~53% (tenant_schema)

Step progress: `admin_user` → `profile` → **`tenant_schema`** → `seed_data` → `activate`.
`tenant_schema` is step 3/5 (~53%). That step runs a multi-minute schema migrate.

## Root cause (recurring)

1. Owner onboarding called provisioning from the **HTTP/gunicorn request thread**.
2. With `CELERY_TASK_ALWAYS_EAGER` (no broker / web-only), `.delay()` ran the migrate **inline on that request**.
3. Gunicorn kills the request at ~120s → SIGKILL mid-migrate → `WorkflowRun` left `running`/`stuck` at `tenant_schema` forever. Requeue without pre-heal often hit the same wall or raced a second card (RUNNING + STUCK).

## Prevention (shipped)

- Eager mode → daemon background thread (never own the HTTP request).
- Owner onboarding → `kick_complete_provisioning_background` only.
- Pre-heal schema drift before migrate; heal chain =
  `cancel_duplicate_run` → `repair_tenant_schema_drift` → `requeue_provision`.
- Dead `running` rows expose executable Auto fix (not Diagnostic only).
- Autopilot applies the healing chain when policy allows.

See also: `docs/prompts/tenant-schema-provisioning-selfheal-world-class.md`
