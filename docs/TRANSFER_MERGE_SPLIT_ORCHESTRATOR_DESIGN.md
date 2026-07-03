# Transfer / Merge / Split Orchestrator — Design (9.8-regime, merge/split domain)

**Status:** DESIGN ONLY — no code shipped with this document. The domain's B-measure
score (5.8, lowest-dimension rule) is UNCHANGED by this document; documentation moves
no score. This is the build plan for the multi-session waves that will.

**Date:** 2026-07-02. Evidence gathered by four parallel read-only audits of the tree
at `28461aa9b`; every file:line below was verified on that tree.

---

## 1. Scope

Three capabilities, currently scored as one domain:

1. **Record merge** — consolidate two duplicate person rows (StudentProfile /
   TeacherProfile / StudentGuardian) inside one school.
2. **Inter-school transfer** — move a student (later: teacher) from school A to
   school B on the same platform, with history.
3. **School merge / split** — combine two tenants or split one. Explicitly LAST:
   it composes 1+2 and must not be attempted before they are proven.

## 2. Evidence map — what exists today

### Transfer rails (five disconnected pieces, none end-to-end)

| Piece | Where | State |
|---|---|---|
| `StudentTransferView` (`POST /api/v1/student/transfer`) | `apps/api/views_v1.py:634` | LIVE but misleading name: mints a `PassportSchoolInvite` (90-day read-invite token). Moves nothing. |
| Transfer envelope | `apps/interop/transfer_envelope.py:72` | Generic checksummed serializer over caller-supplied dicts (`sha256` over canonical JSON, hashed tenant ids, kinds `student`/`teacher`/`academic_history`). Does NOT read any model; no in-tree caller outside tests. |
| `apply_teacher_transfer_envelope` | `apps/interop/transfer_apply.py:42` | Teacher-only; creates `governance.Employment` + `SchoolAssignment` at target. **NOT idempotent** (unconditional `create()`), wired to no endpoint/command. No student counterpart exists. |
| OneRoster inbound writes | `apps/api/oneroster_writes.py:214,394` | Additive `SchoolMembership` upsert (never removes the old school); `StudentProfile.school` set only-when-null and cross-tenant re-point **refused** (`tenant_mismatch` 409 at `:432`). Moves no history. |
| Offboarding export → migration-cloud import | `apps/schools/tenant_offboarding.py:837` → `apps/migration_cloud/` | Whole-tenant ZIP: per-student GDPR JSON + canonical CSV via `tier3.export_tenant_to_canonical` (`tier3.py:264` — **students + finance only**; `guardians` is in the default domain set but has no branch, silently omitted). Format-compatible with migration-cloud intake (`RunMyCampusCanonicalAccelerator`, ≥3 header hits) but nothing wires export to import. |

The migration-cloud apply pipeline itself is the strongest asset: 24 domain landers
(students/guardians/staff/enrollment/attendance/grades/finance/transcripts/…),
natural-key idempotent upserts with conflict detection
(`landers/_helpers.py:294 upsert_with_conflict_detection` → `MigrationConflict` +
operator PRESERVE), per-school `MigrationIdMapping` (`models.py:457`, unique
`(legacy_namespace, legacy_id, canonical_model, school)`), quarantine, dry-run,
FK dependency waves, reconciliation with parity threshold + PII blob purge
(`reconciliation.py:56`), Celery tasks with synchronous fallback
(`celery_tasks.py:92 enqueue_advance`), and a generic rows→CSV→bundle→apply bridge
(`services/connector_bundle_bridge.py`). **No internal-tenant source adapter exists**
(`source_adapters.py:98` registers external SIS only) — that adapter is the missing
keystone.

### Identity anchor (passport) — exists, with a real defect

- `StudentPassport` (`apps/people/models.py:1139`): platform-unique `guid`
  (uuid4), optional `owner` user. `PassportDocument` (verified artifacts),
  `PassportSchoolInvite` (read-invites).
- **Defect (fix in Wave A):** two DISCONNECTED link rails.
  `passport_services.get_or_create_passport_for_student` (`passport_services.py:20`)
  writes a `StudentPassportMembership` (`student_passport_models.py:14`) but never
  sets `StudentProfile.passport`; the API timeline view
  (`views_v1.py:566 StudentPassportView`) reads ONLY the `StudentProfile.passport`
  FK (`models.py:506`). A portal-created passport is invisible to the API timeline.
  No backfill exists — passports are lazy-created only.
- `SchoolMembership` (`apps/schools/models.py:1104`) is the sole access authority
  (`unique_together (user, school)`; `is_primary` is a default-school pointer with
  no authority). Two active memberships without a session pin → interactive school
  picker (`tenant_login_redirect.py:48,143`). `UserTenantBinding` is an SSO audit
  sidecar, never routing authority (`oidc_rp.py:435`).

### Merge rails

- `RecordManagementService.merge_records` (`apps/people/people_management.py:363`)
  is a comment-only no-op returning `{"merged_into", "removed"}`. Zero callers,
  zero tests, no registry contract around it.
- `apps/people/ai_dedup.py` is LIVE and read-only: `deterministic_score` (name/DOB/
  contact heuristic) + `propose_match` (AI gateway), wired into the migration-cloud
  student lander (`landers/student_lander.py:130`) which surfaces candidates into
  `bundle.mapping_summary["dedup_candidates"]` for operator review. **No action
  path exists** — candidates can be seen, never resolved.
- Inbound-FK blast radius (live models, lower bound): **StudentProfile ~64 FKs
  across 11 apps** (academics 10, analytics 9, evals 8, finance 8, schoolops 7,
  communication 4, portal 4, people 11, compliance/reports/student360 1 each);
  TeacherProfile ~19 across 4 apps; StudentGuardian 2 (finance).

### School merge/split rails

None. The adjacent destructive-tenant rail whose **safety grammar we copy** is the
purge path (`apps/schools/tenant_offboarding.py` + 
`apps/compliance/tenant_offboarding_inventory.py`): generic app-registry model-graph
walker (`build_inventory:341`), dry-run `PurgePreview`, `confirm_slug` token, legal
hold, dual distinct-operator approval, resumable `PurgeOperation` with
`needs_resume`, signed deletion certificate, RLS-bypass atomic block.

### Governance rails the orchestrator plugs into

- Process engine: `apps/orchestration` — `ProcessDefinition`/`ProcessDefinitionVersion`
  (frozen per-run), `OrchestrationRun` (pending/running/completed/failed/
  compensating/cancelled, `school` FK, `sla_deadline`), append-only
  `OrchestrationStepEvent`, retry + `compensate()` hook, runner dispatch by
  definition code (`runners.py:308`), simulation mode (`runners.py:322`), Celery
  advancer with mgmt-command fallback (`tasks.py:19`).
- Consent: `GuardianConsentToken` (`apps/migration_cloud/models_guardian_consent.py:87`)
  is the canonical cross-org consent artifact — raw token returned once, only
  `token_sha256` stored, `hmac.compare_digest`, immutable consent-text hash,
  server-captured IP/UA, 90-day revocation, atomic FSM transitions, best-effort audit.
- Audit: `compliance.AuditLog` best-effort pattern
  (`apps/portal/views_device_governance.py:30 _audit_device_action`).
- Lineage: `record_derived_lineage` (`apps/metadata/models_derived_lineage.py:85`) —
  transfer/merge outputs stamp provenance (`computation="student.transfer"` /
  `"people.merge"`, row granularity).
- Operator console pattern: staff_member_required + `?format=json` branch +
  `templates/super/<area>/` + 500-row cap (`views_device_governance.py`,
  `views_sync_health.py`; routes in `apps/portal/urls.py:263`).
- Async: `apps/platform_runtime/periodic.py` registry (`register_job:123`,
  /health/-tick fallback, dead-man's-switch, `cache.add` exactly-once) — prod has
  NO Celery worker, so the advancer MUST be a registered periodic job, with the
  Celery task as the standing-down path.
- Offline hazard: queued `OfflineAction` rows freeze `school_id` at enqueue
  (`offline_queue.py:212`); every applier re-validates entity school vs frozen id
  and rejects `Tenant mismatch`. Devices/tokens are hard-bound
  `(school, user, device_id)` (`models_offline_device.py:36`).

## 3. Design decisions

**D1 — Transfer is export→import, never live FK re-pointing.**
The student gets a NEW `StudentProfile` at the target school; the source profile is
retained and marked `TRANSFERRED` (status label already exists,
`views_backend.py:614`). Rationale: the platform's own OneRoster write path refuses
cross-tenant re-points by design; ~64 inbound FKs assume school-stable rows; source
school retains its legal academic record; tenant isolation is never violated.
Cross-school continuity rides the passport GUID (the API timeline already unions
`StudentProfile.objects.filter(passport=...)` across schools). REJECTED: UPDATE of
`school_id` across the row graph (violates isolation invariants, breaks offline
frozen-school replay, unwindable only by another mass UPDATE).

**D2 — The apply side rides migration-cloud unmodified.**
A transfer produces canonical-domain rows (`DOMAIN_CANONICAL_HEADERS` — students,
guardians, enrollment, attendance, grades, finance, transcripts first) and feeds
them through `connector_bundle_bridge` into a normal bundle at the target school:
same landers, same idempotency, same conflict detection, same `MigrationIdMapping`
(namespace = `rmc_transfer_<source-school-hash>`), same quarantine, dry-run preview,
and reconciliation. We build ONE new `TransferSourceAdapter` (internal-tenant
source) instead of a parallel apply path. REJECTED: bespoke per-model copy code
(would fork 24 landers' worth of upsert/conflict logic).

**D3 — The wire format is the interop envelope, upgraded to carry canonical rows.**
`build_student_envelope` gets a real model-reading builder: per-student extraction
into `{domain: [canonical rows]}` payload inside the existing checksummed envelope
(kinds `student` + `academic_history` are already reserved). The envelope is what
gets consent-gated, checksummed, audited, and (later) exported off-platform — the
same artifact serves same-platform transfer and future cross-platform switching.
`apply_teacher_transfer_envelope` is retrofitted idempotent (`get_or_create` on
(user, school, role) + envelope-id dedupe) in the same wave.

**D4 — The state machine is a first-class model, advanced by the orchestration app.**
New `TransferCase` model (see §4) owns the FSM; a new orchestration runner
(`definition code "student_transfer"`) advances it so we inherit the append-only
step-event log, retry, compensation, SLA deadline, and SLO rollups for free. The
advancer is registered in the periodic registry (Celery absent in prod). REJECTED:
driving the FSM from views only (no crash-resume, no event log).

**D5 — Consent before export, purge-grammar before destructive steps.**
Student transfer requires a `TransferConsent` artifact (clone of the
`GuardianConsentToken` discipline) captured BEFORE the envelope is built. Merge and
school-merge adopt the purge safety grammar: dry-run preview with row counts,
explicit confirmation token, dual distinct-operator approval for school-level
operations, resumable operation record, and a signed completion certificate.

**D6 — Merge re-parents via a walker, quarantines collisions, never hard-deletes.**
`merge_records` becomes real: walk the app registry for inbound FKs to the person
model (same technique as `tenant_offboarding_inventory.build_inventory`, re-point
instead of delete), handle unique-constraint collisions by QUARANTINE (operator
review, mirroring `MigrationConflict`) rather than auto-delete, then soft-retire
the secondary (`is_active=False` + `merged_into` FK tombstone + audit + lineage).
The existing `ai_dedup` candidates become the console's inbox. REJECTED: curated
static FK list (drifts the day a new FK lands — the walker is self-maintaining;
the purge inventory proves the technique in production).

**D7 — School merge = orchestrated bulk transfer + wind-down; split = cohort transfer.**
No new mechanics: school merge is N `TransferCase`s (batch parent record) from
source into target followed by the EXISTING offboarding wind-down of the source;
split is a cohort-scoped selection transferred into a freshly provisioned tenant.
Gated behind Waves A–C being proven in production.

## 4. Domain model (new)

```
people.RecordMergeOperation            # Wave C
  id UUID; school FK; kind (student|teacher|guardian)
  primary_ct/pk, secondary_ct/pk (Char — survives secondary retirement)
  status: draft → previewed → approved → applying → applied → failed
  preview JSON (per-model re-point counts, collision list)
  collisions JSON (quarantined unique-constraint hits)
  approved_by FK; needs_resume bool; completed_at; certificate_sha256

interop.TransferCase                   # Wave A (model), Wave B (runner)
  id UUID (= bundle idempotency key at target)
  student_passport FK (people.StudentPassport — the cross-school anchor)
  source_school FK; target_school FK; source_profile_pk Char
  status: draft → consent_pending → approved → exporting → envelope_sealed
          → applying → applied → reconciled | failed | compensating | cancelled
  envelope_checksum Char(64); domains JSON (which canonical domains included)
  consent FK → interop.TransferConsent (null until captured)
  orchestration_run FK (null=True) — the advancer binding
  created_by FK; timestamps per transition (JSON or explicit fields)

interop.TransferConsent                # Wave B
  — GuardianConsentToken discipline: token_sha256 only, consent_text_sha256,
    decision FSM pending/consented/declined/expired, server IP/UA,
    revocation window, best-effort audit on every transition.
```

Tenant note: `TransferCase` carries BOTH school FKs and is operator-plane data —
queries need honest `# tenant-isolation-allow:` markers on the `.filter(` lines
(scanner anchors there), reason family `transfer-case-cross-tenant-by-design-…`.

## 5. Transfer pipeline (end-to-end, Waves A+B)

1. **Open** — operator (or source-school admin) opens a `TransferCase`; passport is
   `get_or_create`'d for the student (Wave A fixes the dual-rail so this also sets
   `StudentProfile.passport`).
2. **Consent** — `TransferConsent` minted to the guardian; case blocks in
   `consent_pending` until consented (declined → cancelled).
3. **Export** — envelope builder reads the source profile's graph into canonical
   rows per domain (extends `tier3.export_tenant_to_canonical` to per-student
   scope + the missing domains, fixing the silent `guardians` omission), seals the
   checksummed student envelope, stamps lineage (`computation="student.transfer.export"`,
   row granularity, source row PKs).
4. **Apply** — `TransferSourceAdapter` feeds envelope rows through
   `connector_bundle_bridge` into a target-school bundle (idempotency key =
   TransferCase id, namespace `rmc_transfer_*`); dry-run first → operator preview
   (reuse `#mc-apply-preview` panel pattern); then real apply through the landers.
5. **Link** — new target `StudentProfile.passport` = same passport;
   `StudentPassportMembership` row at target; source profile → `TRANSFERRED`
   status + `is_active=False`; source `SchoolMembership` (if student user) left
   intact per OneRoster additive precedent, `is_primary` moved to target.
6. **Reconcile** — migration-cloud reconciliation runs parity; case → `reconciled`.
   Compensation path = bundle `MigrationRun.trigger_rollback()` + case →
   `compensating`/`failed`; source profile untouched until apply is proven.
7. **Guards** — refuse `exporting` while the student has pending/conflict
   `OfflineAction` rows at source (frozen-school replay hazard, `offline_queue.py`);
   surface the block in the console. Device registrations stay school-bound
   (new school = new registration by design).

Console: `/portal/super/transfers/` per the devices/sync-health pattern. Audit:
best-effort `AuditLog` at every transition. Incidents: a stuck case (SLA overdue)
raises through `incident_services.upsert_platform_incident`
(key `transfer_stuck_<case>`), wiring the orchestrator into the wave-2/4 rails.

## 6. Failure injection + test plan (per 9.8 ceiling rules)

- **Unit:** FSM transition matrix (illegal transitions raise); envelope
  checksum tamper → apply refuses; consent decline/expiry/revocation paths;
  idempotent re-apply (same case id twice → no duplicate rows, proven via lander
  natural keys); teacher-apply idempotency regression.
- **Failure injection:** kill the advancer mid-`applying` (crash-resume via
  orchestration retry + `needs_resume` semantics); force a lander quarantine and
  prove the case parks (not silently completes); offline-pending guard blocks
  export; unique-collision in merge quarantines instead of deleting; simulated
  parity failure keeps case out of `reconciled`.
- **Isolation:** every new query passes `scan_tenant_queryset_safety` with honest
  markers; cross-tenant writes only inside the adapter/apply boundary.
- **Runtime proof:** end-to-end test transferring a seeded student (evals +
  attendance + invoice) between two fixture schools (distinct `subdomain=`!),
  asserting target rows, id-mappings, passport timeline spanning both schools,
  and source retention.

## 7. Wave decomposition

| Wave | Scope | Exit criteria |
|---|---|---|
| **A — foundations** | Passport dual-rail fix + backfill command; `TransferCase` model + migration; real student envelope builder (per-student canonical extraction incl. guardians fix); `TransferSourceAdapter` + bridge into target bundle; teacher-apply idempotency; dry-run only end-to-end. | Seeded student round-trips source→target in dry-run with correct preview counts; 0 gate regressions. |
| **B — orchestrated go-live** | Runner + periodic advancer; `TransferConsent`; real apply + link + reconcile; offline guard; console; audit/lineage/incident wiring. | Full transfer completes + compensates under injected failure; console operational. |
| **C — record merge** | FK walker re-parent engine; `RecordMergeOperation` + preview/approve; collision quarantine; soft-retire tombstone; ai_dedup inbox console; real `merge_records` (or its retirement in favor of the service). | Two seeded duplicates merge with all ~64-FK classes re-parented or quarantined; secondary tombstoned; no hard delete. |
| **D — school merge/split** | Batch parent over Waves A–C + wind-down integration; design refresh first. | Not before A–C proven in prod. |

## 8. Defects found during this design pass (fix in Wave A, they are code, not docs)

1. Passport dual-rail disconnect (`passport_services.py:20` vs `views_v1.py:566`).
2. `export_tenant_to_canonical` silently omits declared `guardians` domain
   (`tier3.py:271` vs missing branch).
3. `apply_teacher_transfer_envelope` non-idempotent (`transfer_apply.py:42`).

## 9. Open questions for the owner (non-blocking for Wave A)

- Does the SOURCE school need to approve an outbound transfer, or only the guardian
  consents + target accepts? (Default designed: guardian consent + target-side
  operator approval; source admin notified.)
- Which domains transfer by default? (Designed default: students, guardians,
  enrollment, attendance, grades, transcripts; finance EXCLUDED by default —
  balances stay with source; explicit opt-in flag on the case.)
- Retention: how long does the source keep the TRANSFERRED profile active-invisible
  before normal archival applies? (Designed default: existing archival policy,
  no special-case.)
