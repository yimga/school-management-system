# apps/compliance

> The platform's audit trail, GDPR/FERPA data-rights machinery, external-auditor
> access, and the data-residency border lock.

**Tenancy:** SHARED (public schema; some models carry an explicit `school` FK, but the core audit tables do not — see "Before you change this")
**Scale:** 27 models · 23 migrations · 45 test modules · ~24.7k LOC

## What this app owns

Compliance is where the platform proves what it did. It owns four slices that
are only loosely related in code but tightly related in a regulator's eyes: the
append-only audit trail (`AuditLog`, `AccessLog`, plus the hash-chained
`NonRepudiationLogEntry`), the data-subject rights pipeline (GDPR Art.17 erasure
and Art.20 portability, FERPA §99.32 disclosure logging, consent capture), the
external-inspector surface (time-bounded magic-link grants that expose only
PII-masked projections), and the access-control perimeter (IP/country rules,
threat detection, and the cross-border residency gate).

The organising principle across all four is **fail-closed, and never let the
record-keeping break the control**. `cross_border_export._audit_residency_violation`
is the clearest statement of it: when a cross-region access is blocked, the
durable record is a structured ERROR log line, because the data layer cannot
assume a writable DB in the correct region exists at the moment it blocks — that
is the whole point of blocking. An `AuditLog` row is *also* attempted, wrapped in
a bare `except`, so a failed audit write never masks the block.

The second principle is that this app documents its own limits. Read the "HONEST
SCOPE NOTE" in `cross_border_export.py`: residency is enforced at the
*application data layer*. It refuses to serve a request that would read or write
a tenant's PII from a store outside that tenant's regulatory `data_region`. It
does not by itself provide physical multi-region storage — per-region Postgres
replicas remain an ops item.

## Key models

The 15 that matter most, of 27 declared. This table is not exhaustive.

| Model | Table | Purpose |
| --- | --- | --- |
| `AuditLog` | `compliance_auditlog` | The master trail: create/update/delete, sensitive-data views, exports, auth events, permission changes. Append-only. Carries `during_impersonation` + `impersonated_school_id` so an operator acting inside a tenant is forensically separable from a tenant's own users. |
| `AccessLog` | `compliance_accesslog` | Access to sensitive views/APIs. |
| `NonRepudiationLogEntry` | `compliance_nonrepudiationlogentry` | Per-school SHA-256 hash chain, each entry HMAC-signed, so a later edit or re-ordering is detectable by `verify_chain`. |
| `AuditLegalHold` | `compliance_auditlegalhold` | Blocks matching records from entering retention archives or purges. Blank `model_label` applies to every supported model. |
| `AuditArchiveRecord` | `compliance_auditarchiverecord` | Verification metadata (sha256 + HMAC signature) for one archive-before-purge bundle. |
| `AuditorAccessGrant` | `compliance_auditoraccessgrant` | Time-bounded, revocable grant for an EXTERNAL inspector (Ofsted / state). The unexpired, unrevoked grant *is* the authorisation — the inspector never logs in. |
| `AuditorAccessLog` | `compliance_auditoraccesslog` | Append-only record of what an inspector actually viewed under a grant. |
| `EraseRequest` | `compliance_eraserequest` | GDPR Art.17 right-to-be-forgotten request. |
| `ExportJob` | `compliance_exportjob` | GDPR Art.20 portability export. |
| `FerpaDisclosure` | `compliance_ferpadisclosure` | FERPA §99.32 disclosure log for US K-12. |
| `ConsentRequest` | `compliance_consentrequest` | School-created consent event (field trip, photo usage, privacy policy). |
| `ConsentRecord` | `compliance_consentrecord` | Parent signature: SHA-256 hash of the document at sign time. |
| `RetentionRule` | `compliance_retentionrule` | Retention window per data class / entity type. |
| `IPAccessRule` / `CountryAccessRule` | `compliance_ipaccessrule` / `compliance_countryaccessrule` | Allow/deny perimeter; country rules use ISO 3166-1 alpha-2. |
| `UserActivitySession` | `compliance_useractivitysession` | Login/logout, inactivity timeout, concurrent-login tracking. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `mark_sla_breaches` | The app's only registered task. |
| Module | `cross_border_export` | `enforce_region_match` / `enforce_cross_border_export` (hard gate) + `cross_border_export_blocked` (soft UI predicate). |
| Module | `tenant_scope` | `scope_audit_logs` / `scope_access_logs` / `scope_sessions` — mandatory (see below). |
| Module | `pii_masking` | Non-destructive masked projections for auditor views. |
| Module | `dsar_registry` | Declarative DSAR coverage contract. |
| Module | `non_repudiation` | `record_action` / `verify_chain`. |
| Module | `audit_retention` | Archive-before-purge. |
| Command | `rotate_audit_hmac_key`, `verify_non_repudiation_chain`, `verify_data_integrity` | Chain + key custody. |
| Command | `archive_old_audits`, `purge_compliance_data`, `tenant_purge`, `tenant_offboarding_run_scheduled_purges` | Retention / offboarding. |
| Command | `process_erase_requests`, `privacy_request` | DSAR fulfilment. |
| Command | `detect_threats`, `verify_access_control`, `check_compliance`, `seed_compliance_baseline`, `export_compliance_evidence_pack` | Perimeter + evidence. |
| URLs | `dashboard`, `audit_trail`, `data_rights_queue`, `erase_approve` / `erase_reject` / `erase_complete`, `auditor_grants_console`, `auditor_inspect`, `data_quality_center`, `integrity_check`, `anomalies` | Split across `urls.py` and `urls_reporting.py`. |

## Before you change this

- **`AuditLog` has no `school` column.** This is a SHARED app and the core audit
  tables are scoped *by user membership*, not by a FK or a Postgres schema. A
  queryset that forgets `tenant_scope.scope_audit_logs(qs, school)` returns every
  tenant's audit rows. `get_compliance_scope_school(request)` raises
  `PermissionDenied` when there is no `request.school` and the user lacks
  control-plane access — do not soften that into a `None` return.
- **Audit rows are append-only and enforced at the ORM.** `AuditLog` pairs
  `AppendOnlyModelMixin` with `objects = AppendOnlyManager()`, so both
  `instance.delete()` and `queryset.delete()` raise `AppendOnlyDeleteError` (a
  `PermissionDenied` subclass). The only legitimate removal path is
  `audit_retention` (archive, verify, then purge) — and it refuses any record
  matched by an active `AuditLegalHold`. If you find yourself reaching for
  `.delete()` on an audit table, the answer is a legal-hold-aware archive.
- **`DATA_RESIDENCY_ENFORCE` defaults to `False` on purpose.** It is an ops gate,
  not an oversight. With no region replicas provisioned, flipping it fails closed
  for every tenant whose `data_region` is not the declared
  `DATA_RESIDENCY_DEFAULT_STORE_REGION` (default `"global"`) — in-region/global
  tenants keep working, foreign-residency tenants do not. `config/settings.py`
  states the order: provision replicas in `DATABASES`, run
  `verify_data_residency --fix-derive --strict` until clean, get
  `RUN_VERIFY_RESIDENCY_READINESS` green, *then* flip.
- **Two residency layers raise two different exceptions.** This app's
  `enforce_region_match` raises `ResidencyViolation`, a `PermissionDenied`
  subclass, so it surfaces as 403. `apps.schools.middleware_residency` raises
  `CrossRegionWriteError`, which bubbles to a 500. Both honour the same flag; do
  not assume one exception type when catching.
- **`DATA_RESIDENCY_STRICT_UNKNOWN` is tri-state and its unset default follows
  `DATA_RESIDENCY_ENFORCE`** (closeout 2026-07-03). Enforcing residency while
  silently passing an unresolvable region was fail-open for the exact case the
  control exists for. A single-region deployment opts out *explicitly* with `0`.
- **Archive bundles are signed, not encrypted.** `audit_retention` writes gzipped
  JSONL and records a sha256 + HMAC signature; `AUDIT_ARCHIVE_SIGNING_KEY` is
  required and its absence raises `ImproperlyConfigured` rather than silently
  producing an unverifiable bundle. Signing proves integrity, not confidentiality
  — treat the archive root as PII-bearing storage.
- **Masking and scrubbing are not interchangeable.** `pii_masking` returns a
  masked *projection* and never alters stored data; `gdpr_services.gdpr_scrub_student`
  destructively anonymises. Auditor views must only ever use the former.
- **A new PII-bearing model in `people` / `accounts` will fail the DSAR gate**
  until it is classified in `dsar_registry` as `SUBJECT`, `RELATED_ERASED`, or
  `EXEMPT` (with a documented legal basis). That is the point:
  `tests/test_dsar_coverage_registry.py` fails loudly rather than letting a table
  of someone's PII silently escape both export and erasure.
