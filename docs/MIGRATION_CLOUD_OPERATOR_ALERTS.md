# Migration Cloud — Operator Alert Routing (v3.40.0)

Email-only alerts (the v3.39 baseline) are not enough for production
on-call rotation. `apps.migration_cloud.alerts.alert()` fans out to up
to three channels driven by severity:

| Severity   | Log | Email | Slack | PagerDuty |
|------------|:---:|:-----:|:-----:|:---------:|
| `info`     |  *  |       |       |           |
| `warning`  |  *  |   *   |   *   |           |
| `critical` |  *  |   *   |   *   |     *     |

PagerDuty pages the on-call engineer for `critical` only. Slack is
informational + actionable for both `warning` and `critical`. Email is
the durable record (and the fall-through channel — when Slack +
PagerDuty are unconfigured, `warning` and `critical` still email).

## Alert sources wired in v3.40.0

| Source                              | Severity | Dedupe key                          | File                                                  |
|-------------------------------------|----------|-------------------------------------|-------------------------------------------------------|
| Audit chain broken (exit 1)         | critical | `audit-chain-broken-global`         | `apps/migration_cloud/tasks_audit.py`                 |
| Audit signature mismatch (exit 2)   | critical | `audit-sig-mismatch`                | `apps/migration_cloud/tasks_audit.py`                 |
| Nightly smoke non-clean             | warning  | `smoke-nightly-failure-exit{code}`  | `apps/migration_cloud/tasks_smoke.py`                 |
| Token rotation overdue              | warning  | `token-overdue-{token_id}`          | `apps/migration_cloud/tasks_alerts.py` (beat: daily 03:30 UTC) |
| Throttle saturation (deferred)      | warning  | `throttle-sat-{bucket}`             | _Deferred — see `rate_limiting.py` integration below_ |

Throttle saturation is **deferred to v3.41**. The existing
`MigrationCloudGlobalThrottle` logs `migration_cloud_global_throttle_reject`
but does not yet emit a saturation alert. The plan: add a
`record_throttle_saturation(bucket, ratio)` hook in
`rate_limiting.py` that the throttle calls when a bucket reaches 95%
in a one-minute window; the hook calls into `alerts.alert(...)` with
severity `warning`. The hook is intentionally not yet shipped — the
existing throttle file is owned by another agent's in-flight surface
and the saturation event is not yet defined upstream.

## Settings

All four env vars are read via `os.environ.get()` in `config/settings.py`.
The alerts module reads `settings.*` first (so `@override_settings` works
in tests) and falls back to env if absent.

```bash
# Slack incoming webhook URL — empty = channel disabled.
export OPERATOR_ALERT_SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T.../B.../..."

# PagerDuty Events API v2 integration (routing) key — empty = channel disabled.
export OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# DRY RUN is ON by default. Flip to "0" deliberately in production.
export OPERATOR_ALERT_DRY_RUN="1"

# Per-hour cap on distinct dedup_keys. Default 50.
export OPERATOR_ALERT_RATE_LIMIT_PER_HOUR="50"

# Email recipient — reuses v3.39 setting; either of these works.
export OPERATOR_ALERT_EMAIL="oncall@example.com"
# (legacy alias, still honored)
export MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL="oncall@example.com"
```

## Dry-run toggle (essential for staging)

`OPERATOR_ALERT_DRY_RUN=1` (the default) makes every channel **log the
would-send payload but not actually POST**. You'll see lines like:

    operator_alert_slack_dry_run severity=critical webhook_sha=abc123... blocks=3
    operator_alert_pagerduty_dry_run severity=critical integration_key_sha=def456... dedup_key_sha=...

Confirm log emission against staging traffic, then flip
`OPERATOR_ALERT_DRY_RUN=0` in production to enable the actual POSTs.

## Rate limit semantics

- **Per-hour cap**: 50 distinct `dedupe_key` values per rolling hour
  (configurable via `OPERATOR_ALERT_RATE_LIMIT_PER_HOUR`). The 51st key
  is dropped and a single `operator_alert_rate_limit_reached` warning
  log fires (then suppressed until the window rolls over). This blocks
  e.g. a 200-overdue-token stampede from drowning Slack.
- **Per-key dedupe**: when the same `dedupe_key` re-fires within the
  one-hour TTL, the alert still dispatches (PagerDuty handles upstream
  dedupe via `dedup_key`), but a `operator_alert_dedupe_repeat` log line
  marks the repeat for observability.
- **Worker restart**: the dedupe table is in-process. A Celery worker
  restart drops the table, so a burst of overdue tokens after restart
  could re-emit. PagerDuty's upstream dedupe absorbs this — by design.

## PagerDuty setup

1. In PagerDuty, create a service for Migration Cloud (escalation
   policy: your on-call rotation).
2. Add an integration of type **Events API v2**.
3. Copy the **Integration Key** (32 hex chars).
4. Set `OPERATOR_ALERT_PAGERDUTY_INTEGRATION_KEY=<that-key>` in the
   production environment.
5. Flip `OPERATOR_ALERT_DRY_RUN=0`.
6. Test-fire a critical alert (see _Test-fire procedure_ below) and
   confirm an incident appears in PagerDuty + the on-call engineer's
   pager.

## Slack setup

1. In Slack, create an Incoming Webhook for the `#migration-cloud-ops`
   (or equivalent) channel.
2. Copy the webhook URL — treat it like a secret (anyone with the URL
   can post messages to your channel).
3. Set `OPERATOR_ALERT_SLACK_WEBHOOK_URL=<that-url>`.
4. Flip `OPERATOR_ALERT_DRY_RUN=0`.
5. Test-fire a warning alert and confirm a card appears in the channel
   with the header + body + links section.

## Incident response decision tree

```
  Alert fires
       |
       v
  +--------------+   critical    +----------------------------+
  | severity?    |-------------->| Page on-call (PagerDuty)   |
  +--------------+               | -> security engagement     |
       |                         |    if audit-sig-mismatch   |
       | warning                 +----------------------------+
       v
  +----------------------------------+
  | Slack acknowledgement within 30m |
  | -> investigate via runbook       |
  +----------------------------------+

  Per source:

  audit-chain-broken-global    -> docs/MIGRATION_CLOUD_AUDIT_LOG.md
  audit-sig-mismatch           -> docs/SECURITY_KEYS.md + security on-call
  smoke-nightly-failure-*      -> docs/MIGRATION_CLOUD_UAT_RUNBOOK.md
  token-overdue-*              -> revoke + re-issue the affected token
  throttle-sat-* (v3.41)       -> docs/MIGRATION_CLOUD_RUNBOOK.md (capacity)
```

## Privacy + secret hygiene (hard guarantees)

The alerts module enforces these invariants and the test suite locks
them in:

- Webhook URL **never** logged in clear — only as `webhook_sha=<12-hex>`.
- PagerDuty integration key **never** logged in clear — only as
  `integration_key_sha=<12-hex>`.
- Body content **never** logged in dry-run logs — only the structured
  fields (severity, title, dedupe_key sha-prefix, link labels).
- Tests in `apps/migration_cloud/tests/test_alerts.py` assert these
  guarantees via `assertLogs` + `assertNotIn(secret, joined)`.

Title and body must be PII-free at the call site. Audit / payload
identifiers must be sha256-prefixed before being passed into `alert()`.

## Test-fire procedure

To prove an alert end-to-end against the real channels (after flipping
`OPERATOR_ALERT_DRY_RUN=0`):

```bash
python manage.py shell -c "from apps.migration_cloud.alerts import alert; alert(severity='warning', title='test fire', body='ignore - operator pipeline test', dedupe_key='test-fire')"
```

Expected outcomes:
- Slack: a `:warning: test fire` card appears in the configured channel.
- Email: a single message to `OPERATOR_ALERT_EMAIL` with subject
  `[Migration Cloud][WARNING] test fire`.
- PagerDuty: nothing — `warning` doesn't page.

To test critical (this WILL page someone — coordinate first):

```bash
python manage.py shell -c "from apps.migration_cloud.alerts import alert; alert(severity='critical', title='page-test', body='operator pipeline page test', dedupe_key='page-test-001')"
```

Resolve the incident in PagerDuty immediately after to verify the
acknowledge/resolve flow works.

## Command Center integration

A minimal status surface is exposed via
`apps.migration_cloud.alert_status.get_alert_status_summary()`. Agent 6
(or v3.41) wires it into the Command Center template. The returned dict:

```python
{
    "last_critical_alert_at": datetime | None,
    "active_dedup_keys": int,        # how many distinct keys in current hour
    "channels_enabled": ["log", "email", "slack", "pagerduty"],
    "dry_run": bool,                 # operator-visible "are we live?" flag
    "rate_limit_per_hour": int,
}
```

## Honest deferred for v3.41+

- **OpsGenie / Teams** webhooks — same pattern as Slack; add a fourth
  channel emitter or generalize the Slack path into a "webhook channel"
  with vendor-specific payload builders.
- **Throttle saturation** alert source (see above).
- **Custom routing rules per severity per channel** — today every
  configured channel sees every alert above its threshold. Operators
  may want to scope (e.g. only `audit-*` dedupe-key prefixes go to
  PagerDuty; everything else stays Slack-only).
- **Digest mode** for non-page-worthy warnings — coalesce N
  same-source warnings into one Slack message every M minutes.
- **Alert silencing UI** in the Command Center (today the only kill
  switch is the env-level `OPERATOR_ALERT_DRY_RUN` toggle).
