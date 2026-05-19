# Migration Cloud — Command Center

**Wave:** v3.40.0 Agent 6 (2026-05-19)
**URL:** `/super/migration/command-center/` (staff-only)
**Refresh:** auto every 60 seconds via `<meta http-equiv="refresh">`
**Cache:** `Cache-Control: no-store` — never served stale

## What this dashboard is

A single read-only screen aggregating the live state of every Migration
Cloud pillar in one place. It is the **operator entry point** during
incident response and the canonical "is the platform healthy *right
now*" question-answerer for partner-success and on-call.

The Command Center does **not** mutate anything. Every action lives on
a sub-dashboard reachable from a card's "Drill in →" link.

## The eight cards

| # | Card                  | What it answers                                              | Drill-in destination                       |
|---|-----------------------|--------------------------------------------------------------|--------------------------------------------|
| 1 | Audit chain           | Is the tamper-evident audit log healthy? When verified last? | `/super/migration/audit/`                  |
| 2 | Webhook fleet         | What's the 24h success rate? Who's failing? Any stale subs?  | `/super/migration/operator/webhooks/`      |
| 3 | Token fleet           | Active token count + rotation pressure                        | `/super/migration/operator/tokens/`        |
| 4 | Companion fleet       | Per-tenant keypairs, 30d uploads, MAA coverage               | `/super/migration/health/`                 |
| 5 | API + rate limit      | SSE transport mode + throttled-bucket snapshot               | n/a (info only)                            |
| 6 | Signed release        | SW cache key + last release tag + audit-root signing backend | n/a (info only)                            |
| 7 | Observability         | Metrics backend + `/metrics/` registration                   | n/a (info only)                            |
| 8 | Counsel / compliance  | MAA active version + draft set + DSAR last-run               | `/super/migration/maa-v2-promotion/`       |

## Status pill semantics

Every card carries one of four pills. They are advisory — never block
anything.

| Pill   | Color  | Meaning                                                                          |
|--------|--------|----------------------------------------------------------------------------------|
| ok     | green  | Nominal — no action needed.                                                       |
| info   | grey   | Informational — section is healthy or no data to surface yet.                     |
| warn   | amber  | Attention soon — sub-threshold problem (e.g. 80-95% delivery rate, 14d rotation). |
| alert  | red    | Act now — chain broken, signature mismatch, overdue rotation, missing MAA.        |

### Per-card pill thresholds

* **Audit chain** — alert on `broken` or `sig-mismatch`; info on `never-verified`; ok on `ok`.
* **Webhook fleet** — alert <80% success in 24h; warn 80-95%; ok ≥95%; info when total_24h=0.
* **Token fleet** — alert when any rotation is overdue (`grace_until < now` + no successor); warn when any is rotating in 14d; ok otherwise.
* **Companion fleet** — alert when uploads happened but no MAA signed; warn when keypair exists but no signed MAA; ok otherwise.
* **API + rate limit** — always info (snapshot informational).
* **Signed release** — warn if SW cache key cannot be parsed; ok otherwise.
* **Observability** — warn if prometheus backend selected but `/metrics/` URL not registered; info on noop; ok on prometheus + registered.
* **Counsel / compliance** — warn while v2.0 is in `MAA_TEXT_DRAFT_VERSIONS` and active version is still v1.0 (counsel-signoff backlog); ok once flipped.

## Performance

**Target:** <500ms total query time on a moderate-size dev DB.

We hit that target by:

* Aggregating delivery counts with **one** `.values().annotate(Count)`
  query (not N+1 across tenants).
* `.distinct()` + `.count()` on signed-tenant / keypair-tenant queries
  rather than materializing rows.
* `.only("integrity_hash", ...)` on every audit-event read.
* No re-walk of the full audit chain — chain status is read from the
  most-recent `audit.*` meta-event (which the weekly beat writes).

If you observe the page taking >500ms in dev or >2s in prod, you've
probably introduced an N+1 inside a section helper — fix it before
shipping.

## Refresh cadence

The page refreshes every 60 seconds via meta-refresh. This matches the
v3.38 health dashboard. **Do not** add JS-driven polling — the page is
intentionally JS-light so it works in any operator browser including
IT-locked-down districts.

If you keep this tab open during an incident, you'll see new audit
events tick up, success rates shift, and stale subscriptions appear
within one refresh cycle.

## Defensive-read patterns used

Five other agents are landing changes to Migration Cloud in the same
v3.40.0 wave. The Command Center is built to survive their renames:

* `CompanionUploadReceipt.plaintext_byte_size` is read via
  `getattr(r, "plaintext_byte_size", 0) or getattr(r, "byte_size", 0)`
  so if Agent 4 promotes the field name, the dashboard keeps working.
* `MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND` AND legacy
  `MIGRATION_CLOUD_AUDIT_ROOT_SIGNING_BACKEND` are both read with
  fall-through.
* `WebhookDeliveryStatus.DELIVERED` is read as `.value` defensively in
  case the TextChoices accessor changes shape.
* Each section helper wraps **all** queries in try/except and returns
  `{"error": <exc-type>}` rather than raising.

## How to escalate from this page

| Card                   | If pill is alert, do this                                                            |
|------------------------|--------------------------------------------------------------------------------------|
| Audit chain (broken)   | Run `python manage.py verify_audit_chain --all-tenants --email-on-broken=oncall@...` |
| Audit chain (sig)      | Treat as backup-restore tamper signal. Page security lead before re-running.         |
| Webhook fleet (<80%)   | Check top-failure-tenant endpoints; they're likely down. Pause deliveries if needed. |
| Token fleet (overdue)  | Manually rotate the listed tokens via `/operator/tokens/<id>/rotate/`.               |
| Companion (no MAA)     | Block further uploads for that tenant until MAA is signed.                           |
| Counsel (warn)         | Ping legal for v2.0 PDF signoff; not an outage but blocking the promotion.           |

## Things this dashboard intentionally does **not** show

* Raw tenant slugs (only IDs / hashed prefixes via sub-dashboards).
* Token plaintext (impossible — only sha256 persisted).
* Signature bytes / HMAC secrets / private keys (never).
* MAA body text (drill into the MAA promotion dashboard for that).
* Per-event payload contents (drill into audit dashboard).

The Command Center is **read-only by design**. If you find yourself
wanting to add a button here, add it to the appropriate sub-dashboard
instead.
