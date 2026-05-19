# Migration Cloud — DSAR automation

_v3.40.0 Agent 13 — DSAR runbook recorder + command center wiring._

This document describes how Migration Cloud surfaces "when did we
last fulfill a DSAR?" into the operator command center, and the
30-day SLA tracking the runbook supports.

## What is a DSAR?

A Data Subject Access Request is a regulator-shaped request from an
individual whose data the platform holds, asking for: access to
their records (GDPR Art. 15), rectification (Art. 16), erasure
(Art. 17), or portability (Art. 20). Under NY Ed Law §2-d and
FERPA, schools must respond within 30 days. Migration Cloud is the
data-mover layer, so it surfaces "the last time we recorded a
fulfillment" as a command-center signal rather than fulfilling
DSARs itself.

## Architecture

Three pieces collaborate:

1. **CLI: `dsar_runbook_record`**
   `python manage.py dsar_runbook_record --request-id <opaque> \
       --completed-at <iso-utc> --notes "..."`
   Writes a structured row to `var/dsar-runs/<utc-iso>.json` and
   updates `var/dsar-last-run.txt` (single-line file).

2. **Web UI: `DSARRunbookView`**
   `/super/migration/dsar/runbook/` — staff-only. Renders the last
   30 recorded runs + provides a POST form that calls the same
   `record_dsar_run` function the CLI uses.

3. **Command-center surface**
   Agent 6's `views_command_center._section_counsel` reads
   `var/dsar-last-run.txt`. When the file is missing or stale, the
   counsel card pill flips to `warn`.

## File layout

```
var/
├── dsar-last-run.txt        # one line: latest UTC-ISO timestamp
└── dsar-runs/
    ├── 20260519T130000Z.json
    ├── 20260519T140230Z.json
    └── ...
```

Each per-run JSON file carries:

```json
{
  "recorded_at_utc_iso": "2026-05-19T13:00:00Z",
  "completed_at_utc_iso": "2026-05-19T12:55:00Z",
  "request_id_sha256": "<full 64-hex>",
  "request_id_prefix": "<12-hex>",
  "has_notes": true,
  "notes": "operator context — never audit-logged"
}
```

The `notes` field is persisted ONLY in the local var/ file; the
audit-event payload carries `has_notes` boolean and nothing more
(notes content may contain FERPA-protected identifiers — the audit
log is exported by reviewers and so MUST stay PII-free).

## 30-day SLA tracking

Operators record one DSAR run per fulfillment. The command-center
counsel card pill goes:

* `ok` — last run within 30 days.
* `warn` — last run older than 30 days OR no run on file.
* `alert` — never (recording a DSAR is not a critical system gate;
  the regulator-facing follow-up is the legal team's beat).

The 30-day threshold is the GDPR Art. 12(3) ceiling; the runbook
itself can be polled more frequently for schools that prefer a
faster cadence.

## Audit event

Each call to `record_dsar_run` emits one `MigrationCloudAuditEvent`
row. Until the dedicated `migration.dsar.runbook_recorded` choice
is registered in the `MigrationCloudAuditEventType` enum, the row
lands under `audit.retention_purge_applied` with a marker key in
the payload (`"dsar_marker": "migration.dsar.runbook_recorded"`)
so an exporter can re-classify.

Payload shape (NEVER carries notes content):

```json
{
  "dsar_marker": "migration.dsar.runbook_recorded",
  "request_id_sha256_prefix": "abc123def456",
  "completed_at": "2026-05-19T12:55:00Z",
  "has_notes": true,
  "registered_choice_fallback": "dsar_event_type_unregistered"
}
```

## Honest-deferred items

* **S3 redirection of request bodies.** Large DSAR responses (full
  data exports) are out-of-band today — operators ship them via
  shared-drive links pasted into `--notes`. A v3.41+ wave can wire
  pre-signed S3 GETs with audit-logged access counts.
* **Dedicated `migration.dsar.runbook_recorded` event_type.** A
  TextChoices addition in `models_audit.py` is a one-line change but
  carries no migration (Django doesn't migrate choices); deferred to
  the next MC fan-out to keep this wave file-disjoint from the
  models_audit owner.
* **Per-tenant DSAR scoping.** Today the runbook is platform-level;
  per-tenant fan-out would attach `tenant_slug` to the audit row.
* **Counsel attestation flow.** The DSARRunbookView could capture an
  optional counsel-signoff signature; today the operator manually
  attaches PDF via shared drive.
