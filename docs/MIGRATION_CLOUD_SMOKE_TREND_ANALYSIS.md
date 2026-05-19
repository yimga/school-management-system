# Migration Cloud — smoke trend analysis

_v3.40.0 Agent 13 — `/super/migration/smoke/history/`._

The Migration Cloud nightly smoke task (Agent 8) emits a structured
summary on each run. Agent 13 wires a Celery `task_postrun` signal
handler that archives each summary to
`var/smoke-results/<utc-iso>.json`. The
`SmokeRunHistoryView` reads the last 30 archived runs and presents
a privacy-conscious trend view.

## How to read the trend page

The page has three sections:

1. **Header.** Total archive count + currently-displayed count.
2. **Sparkline.** A row of CSS bars, one per archived run, sized by
   `passed` section count. Left is oldest, right is newest. Hover a
   bar to see the filename + passed/failed counts in a native
   browser tooltip.
3. **Recent runs table.** Newest-first; columns are archived-at
   timestamp, filename, status string, exit code, passed / failed /
   skipped counts.

The `?status=` filter narrows by status string (`ran`, `disabled`,
`raised`, etc. — see Agent 8's `tasks_smoke.py` for the canonical
set).

## What "passed" means in context

The nightly smoke task runs ten sections:

* setup, maa, companion_keypair, intake, ingest, webhook, sse,
  promotion, audit_chain, cleanup

A clean nightly run will see 5 PASS + 5 SKIP (the optional
sections — intake/webhook/sse/promotion/cleanup — are dry-run
gated by Agent 8's `--apply` policy, so they SKIP rather than fail).
Any FAIL is the load-bearing signal; a sudden drop in PASS count
mid-trend is the second-most-load-bearing signal (something a
required section relies on broke between runs).

## Privacy / logging hygiene

The archived JSON files carry ONLY summary keys — section names,
counts, exit codes. NEVER tenant slugs (the smoke task targets a
single synthetic `smoke-test-tenant` configured via
`MIGRATION_CLOUD_SMOKE_SYNTHETIC_TENANT`), NEVER user emails,
NEVER signature bytes, NEVER ciphertext bytes.

The view renders only the archived envelope keys; if a future
version of Agent 8's summary shape gains a PII-shaped field, the
view's render layer must reject it before display.

## File layout

```
var/
└── smoke-results/
    ├── 20260519T043000Z.json   # nightly Celery beat
    ├── 20260519T143200Z.json   # operator triggered via /super/migration/smoke/trigger/
    └── ...
```

Each file:

```json
{
  "archived_at_utc_iso": "2026-05-19T04:30:01Z",
  "summary": {
    "status": "ran",
    "exit_code": 2,
    "passed": 5,
    "failed": 0,
    "skipped": 5
  }
}
```

The `summary` block mirrors Agent 8's `run_smoke_against_synthetic_tenant`
return value verbatim (with defensive coercion for non-dict
returns — e.g. an exception path returns `{"status": "raised", ...}`).

## Honest-deferred items

* **Proper chart library.** The sparkline is HTML/CSS bars; a v3.41+
  wave could ship a privacy-respecting chart (no remote-served font,
  no CDN, no JS analytics). Chart.js bundled locally would be the
  pragmatic choice; the constraint is "must work offline + must NOT
  carry telemetry."
* **Per-section trend.** Today only the aggregate `passed` count is
  graphed. A per-section trend (passing % of "companion_keypair"
  over time) would surface drift in a specific subsystem; deferred
  because it requires Agent 8's summary shape to include per-section
  status.
* **Retention pruning.** `var/smoke-results/` grows unbounded; a
  Celery beat that prunes files older than 90 days (matching the
  audit-event retention floor) is a one-task addition for the next
  wave.
* **Alerting on trend regression.** The existing
  `MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL` fires per-run on FAIL; a
  trend-regression alert (passed count dropped >50% week-over-week)
  is a separate analyzer task.
