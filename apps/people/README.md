# apps/people

> Students, teachers, guardians, and applicants — plus the guarded machinery for
> moving a person between schools, merging duplicates, and carrying an identity
> across tenants.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 29 models · 71 migrations · 26 test modules · ~18k LOC

## What this app owns

`people` is the roster. It owns the four person records the rest of the platform
joins against — `StudentProfile`, `TeacherProfile`, `StudentGuardian`,
`Applicant` — and the admissions funnel that turns a lead into an enrolment.
Everything else here exists because *people move*, and a school-management system
that models a person as "a row in one tenant" breaks the moment a student
transfers, two records turn out to be the same child, or a school merges.

So the app carries a second, larger concern: **person-identity operations that
cross a tenant boundary**. Three rails, all built on the same grammar — an
explicit FSM, an operator preview, a recorded approval, and honest compensation
on failure:

- **Transfer** (`models_transfer` + `transfer_service`) — one student, source
  school to target school, driven through a guarded status machine.
- **Merge** (`models_merge` + `merge_service`) — two person rows at the *same*
  school consolidated into one.
- **School batch** (`models_school_batch`) — a whole-school merge or a cohort
  split, which fans out one `TransferCase` per student and adds no new transfer
  mechanics of its own.

Above all three sits the **student passport**: a lifetime identity keyed by GUID
that survives school churn, linked to per-tenant enrolments via
`StudentPassportMembership` and carrying verified documents in a transcript
vault. The passport is the reason a transfer can be a *link*, not a copy.

Transfer FSM (`TransferCase.Status`):

```
draft -> consent_pending -> approved -> exporting -> envelope_sealed
      -> applying -> applied -> reconciled
                 |
                 +-> compensating -> failed        (any stage -> cancelled)
```

## Key models

The app declares 29 models; these are the 13 that carry the app's shape. The
rest are supporting records (badges, scan events, resource returns, employer and
apprentice links, retention alerts, information tags).

| Model | Table | Purpose |
| --- | --- | --- |
| `StudentProfile` | `people_studentprofile` | The student record. Soft-deletes by default; `student_code` / `admission_number` are unique **per school**, not globally. |
| `TeacherProfile` | `people_teacherprofile` | The staff record joined by scheduling, evals, and payroll. |
| `StudentGuardian` | `people_studentguardian` | Links a Parent user to one or more students — the parent-portal edge. |
| `Applicant` | `people_applicant` | Admissions-funnel lead. Reaching the ENROLLED stage triggers `StudentProfile` creation in the same tenant. |
| `StudentPassport` | `people_studentpassport` | Lifetime, GUID-keyed identity that survives school churn; optionally owned by a User. |
| `StudentPassportMembership` | `people_studentpassportmembership` | Binds a passport to one enrolment inside one tenant, with an explicit consent status. |
| `TranscriptVaultItem` | `people_transcriptvaultitem` | Stored transcript/report artifact reference plus a verification hash — a reference, not a generated credential. |
| `TransferCase` | `people_transfercase` | One student's source→target transfer and its guarded FSM. The transfer record of truth. |
| `TransferConsent` | `people_transferconsent` | One guardian's consent decision for one case. A case cannot leave `consent_pending` except through one of these. |
| `RecordMergeOperation` | `people_recordmergeoperation` | Duplicate consolidation: previewed plan, explicit approval, quarantined collisions. |
| `SchoolTransferBatch` | `people_schooltransferbatch` | N transfers driven as one merge/split operation; dual-approval gated. |
| `StaffComplianceRecord` | `people_staffcompliancerecord` | Jurisdiction-scoped clearance / safeguarding record per teacher; expiry gates attendance. |
| `TenantAuditLog` | `audit_log` | Per-tenant audit trail — one physical table per tenant schema. INSERT-only by DB grant, not by convention. |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Celery task | `check_badge_expiry_alerts_task` | Sweeps badges nearing expiry |
| Celery task | `sync_alumni_registry_task` | Alumni registry sync (`tasks_alumni`) |
| Command | `attach_audit_triggers` | Installs the PostgreSQL triggers that populate `audit_log` |
| Command | `revoke_audit_log_permissions` | Revokes UPDATE/DELETE on `audit_log` — the INSERT-only guarantee |
| Command | `backfill_passport_links` | Heals `StudentProfile.passport` for rows that only had a membership row |
| Command | `check_badge_expiry_alerts` | Manual run of the badge-expiry sweep |
| Command | `repair_teacherprofile_updated_at` | Adds the `updated_at` column when tenant-schema drift left it missing |
| Module | `transfer_service` | Wave B engine: export → seal → apply → passport link → reconcile |
| Module | `merge_service` | Registry-walking FK re-pointer with quarantine |
| Module | `passport_services` | Tenant-safe passport + vault access |
| Module | `offline_workflow_handlers` | Server appliers for offline student/teacher/applicant creation |
| Module | `ai_dedup` | Duplicate-candidate scoring with a deterministic fallback |
| Module | `schema_repair` | Idempotent column repairs for django-tenants schema drift |

**This app has no `urls.py`.** Its views (`views_backend`, `views_backend_bulk`,
`employer_views`, `people_management`) are routed by other apps — chiefly
`apps.accounts.urls` and `apps.portal.urls`. The one exception is the guardian
transfer-consent landing/decide pair, mounted directly in `config/urls.py` as
`people_transfer_consent_landing` / `people_transfer_consent_decide` because a
guardian follows that link without a tenant session.

## Before you change this

- **`StudentProfile.delete()` is a soft delete.** It stamps `deleted_at`, clears
  `is_active`, and returns without touching the row — deliberately, to preserve
  academic and legal history when a student leaves. `hard_delete=True` exists
  only for explicit purge workflows. Never assume a delete removed the row.
- **`student_code` / `admission_number` uniqueness is per-school, and that is
  load-bearing.** Schools issue their own identifiers, and an inter-school
  transfer *deliberately* lands the same number at the target while the source
  row retires as TRANSFERRED. Do not promote these to global unique constraints.
- **The merge engine walks the app registry; it does not use a curated FK list.**
  That is a decision, not laziness — a hand-maintained list drifts the day a new
  FK lands. Unique-constraint collisions are **quarantined** (left attached to
  the retired secondary and listed on the operation for review), never deleted
  and never silently skipped. GenericForeignKey references are knowingly out of
  scope: audit rows naming the secondary by string id stay truthful history.
- **Nothing is hard-deleted by a merge.** The secondary soft-retires with an
  `is_active=False` + `merged_into` tombstone.
- **Transfer export is blocked while the student's device holds undrained
  offline writes** at the source school. This is not a nicety: replay after a
  school change hits the frozen-`school_id` tenant-mismatch guards and those
  writes would be stranded. Do not weaken `offline_transfer_blockers`.
- **`TransferConsent` mints its raw token exactly once and never stores it** —
  sha256 only, constant-time compare, with the consent text version + hash
  recorded immutably. It clones the Migration Cloud `GuardianConsentToken`
  discipline on purpose; keep them in step.
- **`TransferCase` uses loose references (`consent_reference`,
  `target_bundle_id`), not FKs, to migration_cloud** — so that `people` is not
  coupled to migration_cloud's schema. Resist the urge to "fix" them into FKs.
- **`passport_services` must keep both passport rails in step.** The API
  timeline reads `StudentProfile.passport` while the service historically wrote
  only `StudentPassportMembership`; a passport written to one rail alone is
  invisible to the other. `_ensure_profile_passport_link` handles this, and it
  never re-points an already-linked profile — that is an operator action.
- **`audit_log` is INSERT-only by database grant.** `revoke_audit_log_permissions`
  is what makes that true; app-level convention is not the guarantee.
- **Signal handlers catch broker-transport errors deliberately.** Free-tier
  deploys often have no Celery broker, so a signal calling `.delay()` raises
  `kombu.OperationalError` — not a `DatabaseError`. That catch is what stops a
  missing broker from rolling back a student-create write.
- **`schema_repair` exists because tenant schemas drift.** A tenant cloned from a
  recorded migration state will not re-run a migration, so columns can be missing
  on live schemas that `migrate` reports as fully applied. Repairs must stay
  idempotent and introspection-driven.
