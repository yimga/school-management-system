# apps/interop

> Standards interoperability: translate the platform's canonical person/roster
> model to and from the education-sector wire formats — OneRoster, LTI, Ed-Fi,
> CEDS — plus the cross-SIS student-transfer envelope and the Clever / ClassLink
> rostering clients.

**Type:** support library — **not** an installed Django app. It has no models, no
schema, and no `AppConfig`, and it does not appear in `INSTALLED_APPS`. It is a
pure adapter/transform package imported by core apps (chiefly `people`,
`migration_cloud`, `academics`, and `accounts`).

## What this app owns

`interop` is the boundary between RunMyCampus's own data model and the outside
world's standards. The rule the package exists to enforce is one-directional:
**business logic stays in the core apps; the code here only translates.** An
adapter takes a canonical record (a `people.StudentProfile`, an enrolment, a
roster) and emits the standard payload, or parses an inbound standard payload
back into canonical shape — and does nothing else. Nothing here writes an
authoritative record on its own; that keeps a vendor format change from rippling
into core business rules, and keeps the core apps free of vendor-specific
serialisation.

The second concern is **portable student identity across systems**: the transfer
envelope (`transfer_envelope` → `transfer_apply`) is the sealed, verifiable packet
that moves one student between two RunMyCampus tenants or between RunMyCampus and
a foreign SIS, mirroring the guarded discipline of `apps.people` transfers.

## Key modules

| Module | Purpose |
| --- | --- |
| `oneroster/` | OneRoster CSV/REST roster adapters (users, orgs, enrolments). |
| `lti/` | LTI 1.3 launch / tool-link translation. |
| `edfi/` | Ed-Fi API resource mapping. |
| `ceds/` | CEDS element alignment for state-reporting vocabularies. |
| `clever_classlink_client.py` | Clever / ClassLink rostering client. |
| `roster_sync.py` | Drives a roster pull/push against a configured provider. |
| `student_transfer_export.py` | Canonical → transfer-packet export. |
| `transfer_envelope.py` | Builds the sealed, hash-verified transfer envelope. |
| `transfer_apply.py` | Applies a received envelope into the target tenant. |
| `erp_coexistence.py` | Reconciliation helpers for running alongside an incumbent ERP. |
| `district_readiness.py` | District-level onboarding/readiness checks. |

## Before you change this

- **Adapters translate; they do not own truth.** If you find yourself computing a
  grade, minting an id, or deciding enrolment status here, that logic belongs in
  the relevant core app — call it, don't re-implement it.
- **The transfer envelope is signed and hash-verified.** `transfer_apply` must
  verify the envelope's integrity *before* materialising any row, exactly like the
  `people` / `migration_cloud` transfer rails. Do not add a "trust the sender"
  fast path.
- **Standard payload maps are versioned by the standard, not by us.** When a
  vendor bumps a format, add a new mapping rather than mutating the existing one —
  older exports must keep round-tripping.
- **No model imports at module top level for the transfer path** — keep the core
  apps' schemas decoupled; resolve records through the caller or `get_model`.
