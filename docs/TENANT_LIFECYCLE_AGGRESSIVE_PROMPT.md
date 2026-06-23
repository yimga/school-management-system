# Tenant Lifecycle — Aggressive No-Miss Fix Prompt (conception → deletion)

> Hand this whole file to a Claude Code session. Self-contained. It encodes a no-miss
> audit of the FULL tenant lifecycle (conception → provisioning → setup → users →
> operation → deletion) plus the discipline to fix every gap and re-audit until nothing
> is left. **Migrations, seeding, and testing/validation are PLATFORM-WIDE, not
> tenant-local.** Stop only when a fresh full-lifecycle audit finds nothing.

---

## NON-NEGOTIABLE OPERATING RULES

1. **VERIFY-FIRST.** Every finding below is a HYPOTHESIS produced by a read-only audit
   agent. Agents in this codebase have repeatedly produced confident-but-WRONG specifics
   (claimed a JS file wasn't loaded when it was; claimed a dedupe wasn't called when it
   was). **Open the cited file, confirm the exact cause, THEN fix.** Never edit off a
   second-hand finding.
2. **PLATFORM-WIDE migrations + seeding + testing.** A fix is not done until: its
   migration runs under BOTH `migrate_schemas --shared` AND `--tenant` cleanly; its seed
   data is idempotent and applied to ALL tenants (not just one); and there is a test that
   exercises it across the platform, not a single tenant. `makemigrations --check` must be
   clean; migrations idempotent (SeparateDatabaseAndState + ensure_*_tables pattern).
3. **Idempotent + reversible.** Provisioning/seeding/purge steps must be safe to re-run.
   No partial states without a resume path. Destructive steps (purge/delete) need a
   dry-run, an export, an audit record, and a residual-verification pass.
4. **Token-only CSS, no hardcoding, all CI gates green, SW bumped per UI wave**, path-
   scoped commits (a parallel session is often editing the tree — never `git add -A`).
5. **Browsable per judgment call.** Any UX/decision artifact gets a self-contained
   `var/design-previews/<topic>-browsable.html` for owner sign-off.
6. **Loop until dry.** After each wave, re-run the 5-lens lifecycle audit
   (provisioning · setup · users · deletion · platform migrate/seed/test). Stop only when
   a fresh pass finds nothing new. Log every intentional deferral.

---

## STAGE 1 — CONCEPTION + PROVISIONING  (apps/schools)

Entry points: `super_views_provisioning.py::api_create_school`, `management/commands/create_school.py`,
`super_views_create_school_wizard.py`; pipeline `tasks.py::_do_provision_tracked` (Phase A portal +
Phase B seeding). Model `models.py::School/SchoolDomain/SchoolMembership/SchoolProvisioningEvent`.

CRITICAL (verify each, then fix):
- **Missing seed data on provision** — grading scale, default SiteSettings singleton, RuntimeDefaults,
  compliance profile are NOT seeded → new school 500s on grade entry / brand reads. Add
  `seed_grading_scale_from_profile` / `seed_siteconfig_defaults` / `seed_runtime_defaults_for_school`
  to Phase B; idempotent; covered by a test.
- **Silent profile fallback** (`tasks.py` ~profile-resolution) — no approved education profile → hardcoded
  UK defaults, school goes live broken. Decision: ABORT activation unless policy sets `allow_missing_profile`.
- **Schema-migration failure → infinite retry** — same broken migration re-runs forever. Cap retries (3),
  emit OPERATOR_ALERT, persist failure.
- **Column-repair failure swallowed → school 500s while is_active=True.** Repair failure must ABORT Phase B
  and emit `COLUMN_REPAIR_REQUIRED_MANUAL`, not continue seeding.
HIGH: SchoolDomain has no `(school, domain)` unique DB constraint; payment-policy binding errors swallowed;
`phase_b_failed_steps` not persisted (operator can't see which step blocks). 
TEST GAP: provisioning e2e stops at `is_active=True`; add failure-path tests (migration fail aborts Phase A,
seed fail → Phase B incomplete, profile fallback, column-repair fail aborts).

## STAGE 2 — SCHOOL SETUP + ACTIVATION  (apps/setup_studio)

`services.py` STEP_DEFINITIONS + `_step_state_for_school` + health/launch-blocker calc; wizard engine +
`wizards/*.json`; `templates/.../setup_command_surface.html`; backend dashboard activation checklist.

CRITICAL: **No `academic_year` wizard** — `has_year` is a launch-readiness blocker (`services.py:~772/849`)
but NO wizard guides creating the academic year/terms → schools physically cannot reach launch_ready. Add
`academic_year_setup.json` (+ terms) with a real writer. 
HIGH: no fee-structure / classes / subjects / staff-role wizards (finance + teacher flows break); 12 wizards
reference writers that don't exist (answers silently not persisted) → audit all 36 wizard JSON writers,
implement or mark `state_only`, add `test_wizard_writer_exists_for_all_persistence_targets`.
MED: `health_summary` says "Launch ready" at ≥85% even when `launch_blockers` non-empty → reorder to check
blockers FIRST; WizardNotFound → 500 not 404; SiteSettings singleton not auto-created (seed pk=1 in migration).
TEST GAP: no e2e "fresh school → complete all steps → launch_ready=True, no blockers".

## STAGE 3 — USERS  (apps/accounts, apps/people, apps/portal)

CRITICAL/HIGH (verify each):
- **Bulk import not tenant-scoped** (`people/people_management.py:~197`) — `get_or_create(email=...)` sets no
  `school_id`, creates no SchoolMembership → imported users can reach any school; no password/email sent.
- **Default role = PARENT** (`accounts/models.py:~178`) — any role-less created user inherits PARENT, which
  grants finance access. Change default to least-privilege; require explicit role in all creation paths.
- **Two parallel role systems** (`User.role` CharField vs `User.roles` M2M) with undefined precedence →
  define `effective_role()`, document precedence, test it.
- **Guardian invite has no school scope** → cross-tenant claim possible; add school validation + test.
- **No user soft-delete / deactivation audit** — disabling a user leaves SchoolMembership active, classroom
  assignments + pending invites orphaned. Add `is_active`/`removed_at`/`removed_by` to SchoolMembership,
  cascade on deactivation, audit it.
- **`has_feature_permission` fails closed on DB error silently**; new roles (DPO) missing from `ROLE_RANK`.
MIGRATION/SEED: roles+permissions seeded across 7 fragmented migrations; not all `User.Role` values seeded
(IT_ADMIN/BURSAR/HOD/DEAN missing) → single ROLES_MANIFEST seeded idempotently across all schools + test.
AUTH: audit every `login()` call passes explicit `backend=`; first-login MFA enrollment routing; password
reset sets `password_changed_at`.
TEST GAP: full invite→claim→login→RBAC across roles + schools; deactivate→access-denied; legacy-hash upgrade.

## STAGE 4 — DELETION / OFFBOARDING  (apps/lifecycle, apps/compliance, apps/schools)

`compliance/tenant_offboarding_inventory.py`, `lifecycle/services_offboarding.py`, `lifecycle/purge_operations.py`.

CRITICAL (verify each):
- **No post-purge residual verification** — purge never re-counts after delete; a 99% purge looks identical to
  100%. Add `residual_inventory` to `PurgeReceipt`, re-run `build_inventory` after delete, flag
  `purge_incomplete=True` if any residual > 0.
- **No permission/consent + audit on user deletion** — User deleted via raw cascade, no actor/reason/audit.
  Add an immutable, HMAC-signed `TenantPurgeAuditEvent` (mirror Migration Cloud's append-only log).
- **`School.objects` still returns soft-deleted schools** (`models.py:~232`, "intentionally left alone") →
  ~50 callers leak grace-period tenants into reports. Make `live_objects` the default after auditing callers.
HIGH: no automatic data export before hard purge (GDPR Art.17 / FERPA); DSAR `anonymize_user` exists but is
never called; orphaned scalar `school_id` rows left in public schema (best-effort sweep); legal-hold/consent
not re-checked at purge execution time.
TEST GAP: create-then-purge e2e leaving ZERO residue + schema gone + clean public schema; a platform-wide
`verify_purge_completeness --all-schools` command.

## STAGE 5 — PLATFORM-WIDE MIGRATIONS / SEEDING / VALIDATION  (config, scripts/release, apps/platform_runtime)

`scripts/release/render_predeploy.sh`, `tenant_schema_guard.py`, `detect_tenant_table_drift` /
`heal_tenant_schema_drift`, `verify_all_migrations_applied`, `seed_platform_complete`.

CRITICAL (verify each):
- **`verify_all_migrations_applied --include-tenant` is WARNING-ONLY by default** → a fake-applied migration
  ships and 500s in prod. Flip `--strict` ON by default; opt-OUT via env, not opt-in.
- **No per-tenant reference-data seeding in predeploy** — new schema gets DDL only, no EducationSystemProfile/
  RegionConfig/etc. Add `seed_tenant_reference_data --all-tenants` after `migrate_schemas --tenant`.
- **SiteSettings singleton can be missing** post-migrate → 500 on brand reads. Auto-seed pk=1 in heal + migration.
- **No consolidated platform health command** — drift + migrate-verify + runtime + seed checks are scattered.
  Add `health_check_platform --strict` running ALL gates → single green/red, + a periodic Celery beat.
- **No full-arc e2e** (provision→setup→users→seed→delete across the platform). Add
  `test_tenant_complete_lifecycle_e2e.py` (TransactionTestCase).
MED: column drift only checked if table exists; apps with `RunPython` + new tables but no `schema_repair`
module; `migrate_schools_to_tenants` ordering; healing not proven idempotent on second run.

---

## EXECUTION LOOP

```
order waves by severity: CRITICAL first, across all 5 stages.
for each finding:
  1. RE-READ the cited file; confirm the cause is exactly as stated (verify-first).
  2. Smallest correct fix. If it needs schema change → idempotent migration (shared + tenant),
     makemigrations --check clean, seed idempotent + platform-wide.
  3. Add/extend the test that proves it — PLATFORM-WIDE where the behavior is platform-wide.
  4. Run tests (RMC_SQLITE_TEST_USE_MEMORY_NAME=1) + all CI gates; bump SW if UI.
  5. Path-scoped commit + push.
  6. Re-audit the affected stage; add new findings to the list.
repeat until a fresh 5-lens audit finds nothing.
```

## DONE = a fresh full-lifecycle audit (5 lenses) returns zero new findings; provision→setup→users→delete
## passes one e2e test; `health_check_platform --strict` is green across all tenants; migrations idempotent
## shared+tenant; seeds idempotent platform-wide; every destructive path has dry-run + export + audit + residual check.
