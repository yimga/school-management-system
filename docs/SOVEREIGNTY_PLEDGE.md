# RunMyCampus data sovereignty pledge

**Audience:** school operators, IT directors, district compliance officers,
parents asking "where does my child's data live?"

---

## Our commitment

RunMyCampus is built so that **you** — the school, the district, the operator —
retain ultimate control over where your data resides, how it moves, and how to
leave if you choose to. This document describes the concrete mechanisms behind
that commitment. We do not overclaim: where a capability is ops-provisioned or
roadmap, we say so.

---

## 1. Residency border-lock (app-layer enforcement)

When enabled (`DATA_RESIDENCY_ENFORCE=1`), the platform **refuses** — fail-closed
with HTTP 403 — to read or write a tenant's personally identifiable information
from any store outside that tenant's declared regulatory region. Three independent
enforcement points guarantee coverage:

| Layer | What it blocks |
|-------|----------------|
| **Database router** | An ORM read/write whose resolved alias belongs to a foreign region. |
| **Request middleware** | A request that arrives pre-pinned to a foreign-region alias. |
| **Export path** | A data export whose destination region differs from the school's. |

Every block is audited with a CRITICAL-level log line and a best-effort
`AuditLog` row (`ACCESS_DENIED`, sensitivity `CRITICAL`).

> **Honest scope:** the border-lock is an **application-layer** control. It does
> not by itself create physical per-region database replicas — those remain an
> ops/deploy provisioning item. Until replicas are provisioned, the border-lock
> is the binding guarantee because it fails the operation closed rather than
> allowing a silent cross-border transfer.

Full technical reference: [`docs/DATA_RESIDENCY_BORDER_LOCK.md`](DATA_RESIDENCY_BORDER_LOCK.md).

---

## 2. Self-host and data export (zero lock-in)

The entire RunMyCampus stack is open-source and zero-lock-in: PostgreSQL, Valkey
(BSD Redis fork), Celery, Django. You can run the platform on your own
infrastructure at any time.

- **Docker Compose scaffold:** `deploy/selfhost/` contains a complete topology
  (web + worker + beat + Postgres 16 + Valkey) — copy `.env.example`, set your
  secrets, and `docker compose up`.
- **Data migration:** `pg_dump` the hosted database, `pg_restore` into your own
  Postgres instance, point DNS, verify health.
- **Immutable tenant snapshots:** daily HMAC-SHA256-signed JSON snapshots of each
  tenant's config core + staff + finance ledger, restorable onto a clean instance
  with signature verification (fail-closed).

Full self-host guide: [`docs/SELF_HOST_MIGRATION.md`](SELF_HOST_MIGRATION.md).
Restore runbook: [`docs/DR_SELF_HOST_RESTORE_RUNBOOK.md`](DR_SELF_HOST_RESTORE_RUNBOOK.md).

---

## 3. Per-region replicas (honest scope)

Physical per-region database replicas (e.g. `replica_eu_central`,
`replica_us_east`) are an **ops-provisioned** capability. The application code
includes alias routing and the border-lock enforcement for them, but the replicas
themselves are provisioned per deployment — they are not automatic.

What this means in practice:

- **Single-region deployments** (the current default for most operators): all data
  resides in the hosting provider's region (e.g. Render's Oregon or Frankfurt).
  The border-lock is armed but every tenant resolves to the same region, so no
  cross-border transfer occurs.
- **Multi-region deployments** (ops-provisioned): when the operator provisions
  region-specific database aliases and sets `ENABLE_MULTI_REGION=true`, the
  middleware routes each tenant to its declared region's alias. The border-lock
  then enforces that routing is correct.

We do not claim multi-region capability is automatic or zero-effort. It requires
deliberate infrastructure provisioning and DNS/routing configuration.

---

## 4. What we promise

1. **No silent cross-border data transfer.** When enforcement is on, every
   cross-region attempt is denied and audited — never silently allowed.
2. **Full data portability.** You can export your data (`pg_dump`, tenant
   snapshots, CSV/JSON audit exports) and self-host at any time.
3. **No vendor lock-in.** The stack uses only open-source components. There is no
   proprietary database, no proprietary runtime, no data format that requires our
   tools to read.
4. **Transparent limitations.** Per-region replicas are ops-provisioned, not
   automatic. The border-lock is application-layer, not network-layer. We say
   what we have and what we don't.

---

## 5. Related documents

| Document | Purpose |
|----------|---------|
| [`DATA_RESIDENCY_BORDER_LOCK.md`](DATA_RESIDENCY_BORDER_LOCK.md) | Technical reference for the fail-closed enforcement layer. |
| [`SELF_HOST_MIGRATION.md`](SELF_HOST_MIGRATION.md) | Step-by-step guide to move from Render to your own server. |
| [`DR_SELF_HOST_RESTORE_RUNBOOK.md`](DR_SELF_HOST_RESTORE_RUNBOOK.md) | Restore a tenant from an immutable snapshot onto a clean instance. |
| [`DATA_RESIDENCY_AND_COMPLIANCE.md`](DATA_RESIDENCY_AND_COMPLIANCE.md) | Baseline data-handling posture. |
| [`compliance/DATA_RESIDENCY_LEGAL_GUIDE.md`](compliance/DATA_RESIDENCY_LEGAL_GUIDE.md) | Per-corridor legal and hosting roadmap. |
