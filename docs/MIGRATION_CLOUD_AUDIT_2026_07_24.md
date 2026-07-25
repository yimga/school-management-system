# Migration Cloud — Total Adversarial Audit (2026-07-24)

Seven parallel adversarial auditors (slices A–G) ran the doctrine in [`../../PROMPT_migration_cloud_audit_A_to_Z.md`](../../PROMPT_migration_cloud_audit_A_to_Z.md)
against real code at tip `18c497ce4`. Every finding below was cited to `file:line` by the
auditor and re-verified against the code before the fix landed. Legal artifacts are split out
to [`MIGRATION_CLOUD_LEGAL_EXTERNAL.md`](MIGRATION_CLOUD_LEGAL_EXTERNAL.md).

## Verdicts

| Slice | Area | Verdict |
|---|---|---|
| A | Intake & ingest | THIN — one silent-data-loss BLOCKER at district scale |
| B | Profile / classify / map | THIN — money-corruption BLOCKER + orphaned international transformers |
| C | Apply / guardrail / reconcile / rollback | NO-GO — non-atomic finance BLOCKER, cross-tenant IDOR, rollback missing 23/25 domains |
| D | Competitive parity | THIN — shadow + diff + connector-extensibility are theater |
| E | Security / tenant / audit / API | NO-GO — scoped-token control not wired; RLS inert for MC |
| F | Legal / compliance | PASS-WITH-BLOCKER — guardian-consent record does not gate the data flow |
| G | Objective alignment | THIN — advertised self-serve wizard cannot cut over |

## BLOCKERs (data loss / money / tenant leak / cannot cut over)

| # | Finding | File | Fix |
|---|---|---|---|
| 1 | Blob-cap silent data loss: 10 MB inline cap vs 5 GB intake cap → archive members / companion exports / remote pulls > 10 MB apply **zero rows** with no error | `artifact_blob_store.py:105` | Quarantine over-cap artifacts (visible) instead of `return False`; raise cap; file-backed spill path |
| 2 | `currency_to_decimal` corrupts thousands/EU money **1000×** (`KES 125,000 → 125.000`) on a wired path | `transformers/currency_to_decimal.py:22` | Infer decimal separator by last-separator + trailing group size; consume profiler hint; raise on true ambiguity |
| 3 | Non-atomic finance apply (`apply_atomic` default False) commits ledger **before** guardrail; finance rollback is a no-op → half-written ledger persists on mismatch | `orchestrator.py:202`, `models.py:232` | Coerce `apply_atomic=True` when finance is among resolved domains |
| 4 | **Cross-tenant destructive IDOR**: rollback view fetches `MigrationRun` by raw pk, unscoped, mounted on tenant portal → any authed user deletes another school's students/grades | `views.py:1239` | Scope run to caller's tenant + entitlement gate; 404 cross-school |
| 5 | Scoped API tokens neither authenticate nor enforce scope; JWT path carries full user privilege with no tenant binding | `api/viewsets.py`, `config/settings.py:3098` | Wire `MigrationCloudTokenAuthentication` + `ScopedAPIPermission` on all MC viewsets |
| 6 | Guardian consent is a record with **no apply-time gate** → minor-PII lands regardless of decline/revoke | `models_intake.py`, apply path | Enforce consent in `can_advance_to()` promotion transition |
| 7 | Diff-mode since-filter is dead (checks bare keys, rows arrive `_unmapped.*`) → every "since" delta run re-imports everything | `diff_mode.py`, `orchestrator.py:792` | Filter raw row before transform / match `_unmapped.<col>` + per-vendor timestamp col |
| 8 | Shadow-sync has no live source feed, zero-seeded baseline reads ~100% drift → auto-cutover can never fire | `shadow.py:235` | Seed baseline from live post-apply counts; connector-backed `source_pull`; opt-in scheduled tick |
| 9 | Real rollback of applied tenant rows exists for **only 2 of 25 domains** (students, grades) | `apps/automation/rollback_handlers.py` | Snapshot-driven per-domain revert (created PKs already captured) |
| 10 | Advertised customer wizard dead-ends at MAA-signed; no apply/approve/cutover route | `views_customer.py`, `urls_customer.py` | Wire customer path to the bundle pipeline, or relabel as assisted-migration |

## HIGH

- **A-2** `.xls` multi-sheet workbooks drop tabs 2+ (explode only covers `.xlsx/.xlsm`).
- **A-3** one encrypted/corrupt archive member aborts the whole bundle instead of quarantining the member.
- **B-2** two source columns → one canonical field silently overwrite (last-wins, no conflict row).
- **B-3** four country-aware transformers (grading/attendance/name-locale/spanish-double) registered but wired to nothing.
- **B-4** `grading_scale_to_canonical` has no ceiling → accepts 25/20, 150%, GPA-as-score.
- **C-3** attendance upserts on `(student, date)` but model unique key is `(student, classroom, date)` → per-period collapse.
- **D-3** OneRoster v1.2 snapshot-only: `academicSessions` dropped to custom_fields, no `tobedeleted` delta.
- **D-5** connector registry has dead profiles (`oneroster_csv` PILOT_READY → `connector_not_registered`); no plugin extensibility.
- **E-3** connector-audit "hash-chain mirror" is a dead path (`connector.*` not a registered event type → every mirror write swallowed).
- **G-4** token/webhook minting is operator-only → no partner self-provisioning (AWS gap).
- **G-5** lifecycle events thin: only 3 types, only from API path; UI-driven migrations emit none; no `bundle.reconciled`/`rolled_back`/`shadow.tripped`.

## MEDIUM / LOW (selected)

- **A-4** MC's 7 `request.FILES` sites bypass `apps.security.upload_validation` (size cap only).
- **A-5/7/8** single-non-first-sheet loss; SQL-dump `\N` escape mangling; PDF tabulariser drops identity block.
- **A-6** `EMAIL` intake is an inert stub; `DATABASE` mislabeled "Live database connection" (SQLite-file only).
- **B-5/6/7** country `date_format` never reaches the date transformer; `encoding_fix` doesn't fix mojibake; `enum_rewrite` inert passthrough.
- **C-4** quarantine stores error but not the source row.
- **C-5** reconciliation fill-rate/idempotency computed from source file, not landed rows.
- **C-6** RECONCILED reachable on self-reported parity when visible-count verify silently fails → purges blobs.
- **D-8** `recommended_diff_since` cross-tenant bleed when `school_id is None`.
- **E-2** RLS default-deny inert for MC (SHARED_APPS + `USE_DJANGO_TENANTS=1`); isolation is app-layer only — docs overstate.
- **E-4** `_sanitize_payload` only fires via `record()`, not `save()/create()`; leaked key makes export raise.
- **E-5** Vault HSM backend fails **open** (dry-run defaults on, hardcoded public seed).
- **E-8/9** anonymous companion-pubkey endpoint = tenant-slug oracle + anonymous keypair mint; `csrf_exempt` on session-authable companion POSTs.
- **F-Q3** DSAR + MAA-promotion audit events masquerade as other types (unregistered → fallback).
- **G-6** no SLO clocks on the migration path; **G-7** not marketplace-extensible.

## Remediation status (2026-07-24 — this wave)

**Fixed + verified this wave (bug fixes — code landed, `ast`-clean, agent claims re-verified against real code):**

- **BLOCKER 4** cross-tenant destructive IDOR — `views.py` rollback view now `_tenant_scoped_bundle` + `run.school_id == bundle.school_id`.
- **BLOCKER 2** currency 1000× — `currency_to_decimal.py` last-separator + trailing-group inference + profiler hint (14/14 intl vectors pass).
- **BLOCKER 1** blob-cap silent loss — cap 10 MB→64 MB + quarantine-visible over-cap (`artifact_blob_store.py`).
- **BLOCKER 3** non-atomic finance — force atomic + single-thread when finance present (`orchestrator.py`).
- **BLOCKER 7 / D-8** diff-mode dead filter — `_unmapped.*` key match + tz-safe compare + tenant-scoped `recommended_diff_since` (`diff_mode.py`).
- **C-3** attendance collapse — upsert keys on real `(student, classroom, date)` + section resolution (`attendance_lander.py`).
- **BLOCKER 5** scoped-token control unwired — `MigrationCloudTokenAuthentication` + `ScopedAPIPermission` on all 4 viewsets (`api/*`).
- **BLOCKER 6** guardian consent not enforced — real fail-closed gate on the promotion transition (`models_intake.py`).
- **B-5** country date_format/locale seeded to the date transformer (evidence still wins) (`orchestrator.py`).
- **G-1** customer-wizard honesty — misleading "Awaiting *your* approval" → accurate assisted-path labels (`views_customer.py`).
- **B-2/B-3/B-4/B-6/B-7** column-collision guard + 4 orphan country transformers wired + grading ceiling + mojibake + enum honesty (`mapper.py`, `transformers/*`).
- **A-2/A-3/A-5/A-7/A-8** `.xls` multi-sheet explode (+ `xlrd` pinned) + per-member archive resilience + single-non-first-sheet + SQL `\N` decode + PDF identity-block preserved (`xlsx_explode.py`, `intake/*`, `pdf_extract.py`).
- **E-3/E-4/F-Q3** connector-audit hash-chain mirror registered (kills dead path) + sanitize in `save()` + export redacts-not-raises + DSAR/MAA event types registered (`models_audit.py`, `connector_audit.py`, cmds; migration `0040`).
- **E-5/E-8/E-9/D-1** HSM Vault fail-*closed* + anonymous keypair-mint closed + MAA-sign CSRF gated + shadow honest live-count baseline (`hsm_vault.py`, `companion_receiver.py`, `shadow.py`).
- **Rollback (BLOCKER competitive)** real per-domain handlers for finance/attendance/behavior/guardians/staff (+ honest enrollment non-revert) — **2 domains → 8** — all `pk__in=created_ids` school-scoped; connector rollback wired (`automation/rollback_handlers.py`, `connector_rollback.py`).
- **C-5/C-6** reconcile fill-rate relabeled honest + RECONCILED blocked on verify-failure so source blobs aren't purged on self-reported numbers (`reconciliation.py`).

Test remedies applied for behavior that was corrected: `test_shadow.py` (asserted the OLD misleading baseline), `test_hsm_vault.py` (dry-run now needs `DEBUG=True`).

**Verification (2026-07-24, under `config.settings_test`):** `manage.py check` → *no issues* (imports the whole app registry — every edit + the new API auth wiring + the event-type enum resolve, no circular imports); `makemigrations migration_cloud --check` → *No changes detected* (migration `0040` has zero drift); `test_hsm_vault` (SimpleTestCase, no DB) → the dry-run remedy passes, and the only 2 failures (`VaultLogHygieneTests`) reproduce identically against HEAD, i.e. **pre-existing** and unrelated to this work; pure-function checks (currency 14/14 intl vectors, diff-filter both row shapes). The full `manage.py test` suite is NOT runnable in this sandbox (the `:memory:` runner rebuilds ~845 migrations and hangs — a standing environment limitation, not a code gap); CI runs it on a real Postgres/keepdb.

### Build-phase status (2026-07-24, phase 2)

Product builds SHIPPED this phase (verified: `manage.py check` clean, `makemigrations --check` no drift, template-reference/compile/url-name/import-reference/print/bare-except/pii gates all green, SLO registry valid):

- **G-5 partner lifecycle event bus** — `services/lifecycle_events.py` emits `bundle.advanced/applied/failed/reconciled` at the SERVICE layer (pipeline/orchestrator/reconciliation) so UI-driven migrations fire the same webhooks the REST path does; the REST viewset's inline emit was removed (no double-emit). Catalog: `docs/MIGRATION_CLOUD_EVENT_CATALOG.md`.
- **G-4 self-serve token + webhook provisioning** — `views_tenant_provisioning.py` + 4 templates + tenant routes: a tenant admin mints a scoped API token FORCE-bound to their own school (scope allowlist excludes `tokens:manage`) and registers webhooks, all IDOR-safe.
- **D-5 connector marketplace-extensibility** — `connectors/plugin_loader.py` (settings + entry-point discovery, broken-plugin-isolated) wired into `registry.py`; the dead `oneroster_csv` profile now resolves to a real `OneRosterCsvConnector`.
- **G-3 CutoverRunbook** — `models_cutover.py` + migration `0041` + `views_cutover.py` + operator template + route: create rehearsal→real→sign-off with an immutable reconciliation-scorecard SHA-256 anchor (sign-off legal wording stays LEGAL-EXTERNAL).
- **A-4 upload-validation routing** — MC `request.FILES` sites routed through `apps.security.upload_validation` (coverage 34→24).
- **G-6 migration-fleet SLO panel** — `views_health.py::_migration_fleet_panel` + 3 cards leading the operator health dashboard, answering "is the fleet meeting its SLA" straight from persisted data (no Sentry emit required): **apply latency** p50/p95 over 30d from `mc_apply_bundle` outbox `claimed_at→finished_at`; **reconcile parity** attainment over 30d from `reconciliation_summary.overall_parity_pct` vs the SLO target; **outbox drain** freshness (pending `mc_apply`/`mc_advance` rows + oldest age vs the platform stale-pending threshold). Thresholds are read from the SLO registry (`apps/observability/slo.py`) so dashboard and objective can't drift; every query wrapped so a missing table/field degrades one card, never 500s the page.
- **C-4 rollback coverage 8→30 domains + quarantine source-row** — (1) `apps/automation/rollback_handlers.py` gained a school-scoped `created_ids` deleter for the 16 remaining first-class domains (academics/sections/health/library/transport/hostel/cafeteria/transcripts + the 3 schoolops assignments + 3 athletics + 3 DFV domains) via a factory that INTROSPECTS each model and *refuses* an unscoped delete rather than risk a cross-school one (scope priority `school → student__school → student_profile__school → team__school → hostel__school → issuing_school`; verified every registered domain has a provable scope, so none silently refuses); `structure`, `alumni` + `academic_sessions` got honest non-revert handlers (shared scaffold / in-place mutation). (2) `LanderResult.error_rows` + `_helpers.record_row_error` + `orchestrator._quarantine_errors` now thread the offending SOURCE ROW into `MigrationQuarantineRecord.payload['source_row']` (bounded snapshot), so an operator sees WHAT failed, not just an error string — additive, keyed by the exact error string, zero regression for un-upgraded landers; `behavior_lander` adopted as the reference (other landers adopt incrementally by swapping their `errors.append` pair for one `record_row_error` call).
- **D-3 OneRoster v1.2 delta engine** — three parts: **(academicSessions → real terms)** a dedicated `academic_sessions` lander lands OneRoster `academicSessions.csv` as first-class `AcademicYear` + `Term` rows (two-pass: years then terms under their resolved parent), mapped in the accelerator and placed in orchestrator **wave 0** (before grades, which bind to a term); previously those rows fell through to `custom_fields` so a OneRoster import produced zero real terms. **(delta path)** OneRoster's camelCase `dateLastModified` is added to `diff_mode._TIMESTAMP_COLUMNS`; it's left UNmapped so it arrives as `_unmapped.dateLastModified`, which the `diff_mode="since"` engine reads to skip unchanged rows — a real incremental re-ingest. **(tobedeleted)** structural course/class rows carry `status` through to the lander as `record_status` for the hold path (below); students/enrollment/session `status` is NOT yet mapped, so those are not soft-deleted — the accelerator note states this honestly (the `status` vendor-enum is defined but not yet consumed at transform time), rather than claiming a soft-delete the code does not do. `academic_sessions` gets an honest scaffold rollback handler (shared calendar parent).
- **G-1a full self-serve zero-touch apply pipeline** — a school now drives its own migration from MAA-signed to live cutover with ZERO operator hand-offs, WITHOUT any new tenant-write code (every heavy step delegates to the already-guarded machinery). New `services/intake_pipeline.py` + an intake↔bundle FK (migration `0042`): **(upload)** `MigrationIntakeUploadView` + template validate a CSV/ZIP export (composed A-4 primitives — `sniff_file_mime` + `scan_for_malware` + size, since the magic-byte gate can't sniff a signature-less CSV), ingest it into a `MigrationBundle`, and kick advance→MAPPED + a **dry-run preview** (zero writes) on the durable HeavyWorkOutbox; **(reconcile)** `sync_intake_from_bundle` derives the intake FSM from the bundle's real status on every status load, walking one legal transition at a time and NEVER auto-crossing into promotion; **(approve)** the school's consent-gated approval (BLOCKER-6 guardian gate) enqueues the REAL apply via `enqueue_apply(dry_run=False, reconcile_after=True)` — financial guardrail, atomic mode, quarantine, RLS, rollback, then reconcile — on the outbox; **(complete)** the reconciler rolls the intake to `complete` when the bundle reaches RECONCILED. Concierge intakes (no bundle) are untouched. Proven by a **real DB end-to-end test** (upload → guarded pipeline → approve → real apply → complete) plus 12 wiring tests; 47/47 intake tests pass. The stage labels are now honest per path (self-serve vs concierge) and a validation-preview card shows the school what will import before it approves.
- **D-3 structural `tobedeleted`** — a OneRoster course/class marked `status=tobedeleted` is now carried to the lander via `record_status` and HELD FOR REVIEW (with its source row, C-4) instead of importing as active — and an existing tenant Subject/Classroom is left intact (those models have no is_active/status column and grades/enrollments FK into them, so a hard delete could orphan dependents). Students/enrollment/session `status` is not yet mapped, so those are NOT soft-deleted — the accelerator note says so honestly rather than claiming behavior the code doesn't implement. 5 DB tests + a new `source_deletion` quarantine class, including a **must-fire coupling test** that feeds the landers' real emitted hold strings through `_classify_quarantine_issue` and asserts `source_deletion`, so the producer↔classifier string match can never silently break.

> Note: 5 build agents were terminated mid-work by a session limit; the tree was verified consistent afterward (3 missing templates created, the cutover route added) — nothing shipped half-broken.

**All 9 sequenced product builds are now shipped end-to-end.** Remaining Migration Cloud work is EXTERNAL only (not code): the malware-scan engine (`UPLOAD_MALWARE_SCANNER` — the hook is wired + honest, no bundled scanner), the counsel items in `MIGRATION_CLOUD_LEGAL_EXTERNAL.md`, and a real ClamAV/scanning-service backend for the self-serve upload path.

### Re-audit hardening (2026-07-24, post-ship)

A second adversarial pass (two independent code-reading audits + the full CI-boundary mirror) confirmed G-1a and D-3/C-4 are genuinely wired end-to-end (real DB writes, apply un-mocked, 30-domain rollback with every scope proven or safely refusing) and closed five follow-ups it surfaced:

- **Operator kill-switch on the most dangerous surface** — `MIGRATION_CLOUD_SELF_SERVE_APPLY_ENABLED` (defaults **ON**, so live behavior is unchanged) instantly closes the customer upload + promotion entry points without a redeploy. Enforced at BOTH the service layer (`attach_and_start` raises, `begin_promotion` returns `disabled`) and the views (upload GET/POST + approve POST redirect to status; the status page hides both affordances). Every write still flows through dry-run-first + consent-gate + guarded apply regardless.
- **CSV sniff tightened** — `_looks_like_csv` no longer admits binary that merely contains a delimiter (`latin-1` decodes anything): a NUL byte or a >5% C0-control-byte ratio now marks content binary. Real CSV heads (incl. accented UTF-8) still pass.
- **Accelerator note made honest** — the OneRoster note previously claimed a students/enrollment `tobedeleted→withdrawn` soft-delete that was never wired; reworded to state exactly what is and isn't implemented.
- **Producer↔classifier coupling locked by a must-fire test** (see D-3 above).
- **Two undefined CSS classes defined/retired** — the CI `undefined-css-classes` gate caught `.rmc-card--mc-fleet-slo` (G-6 health) undefined and `.rmc-banner--danger` (G-1a upload) forked; the SLO card modifier is now defined token-safe in `rmc-class-grammar.css`, and the banner uses the existing `.rmc-banner--error`.

---

Original sequencing (superseded by the status above):

1. **Full self-serve customer-apply pipeline (G-1 option a)** — wire the customer intake wizard (`MigrationIntakeRequest`) to the working bundle pipeline with customer `apply`/`approve`/`cutover` routes, so a district reaches a live cutover with zero operator hand-offs (this wave delivered the honest relabel; the full pipeline is the build).
2. **Partner lifecycle event bus (G-5)** — emit `bundle.applied`/`reconciled`/`rolled_back`/`shadow.tripped` at the service layer so UI-driven migrations fire events; publish a partner event catalog. (Event *types* now exist via `0040`.)
3. **Self-serve token + webhook provisioning (G-4)** — tenant-admin scoped-token/webhook mint (the auth control is now enforced; the self-serve UI is the build).
4. **Migration SLO dashboard (G-6)** — apply-duration/ingest-latency/reconcile-parity/queue-depth metrics + a fleet panel.
5. **OneRoster v1.2 delta engine (D-3)** — `academicSessions` → real terms domain + `status=tobedeleted` inbound + a real delta path.
6. **Connector marketplace-extensibility (D-5/D-7)** — entry-point/DB plugin loader + registry-honesty (drop dead `oneroster_csv` PILOT_READY or register a real adapter).
7. **Full 23-domain rollback + quarantine source-row (C-4)** — extend rollback handlers to the remaining domains; thread the source row into `MigrationQuarantineRecord`.
8. **`CutoverRunbook` record (G-3)** — rehearsal→real→sign-off with a reconciliation-scorecard hash (sign-off wording is LEGAL-EXTERNAL).
9. **A-4 upload-validation routing** — route MC's `request.FILES` sites through `apps.security.upload_validation` (the platform AV hook itself is the E1 backlog).

## Genuinely solid (do not regress)

Determinism of the profiler; AI genuinely last + gated; apply never calls the gateway; `country_profiles`
(44 countries) + `locales` (~18 langs) are real data; `FinancialMismatchError` never swallowed on the raise
path + Decimal end-to-end; `repair_readiness` refusals are real must-fire guards; tenant `schema_context`
boundary holds on the apply write path; append-only audit chain + per-tenant hash chain + constant-time
compares; secrets at rest (token sha256-only, webhook secret + companion privkey `EncryptedBinaryField`);
outbound webhook canonical signing + SSRF guard at registration and delivery; MAA sign gates are real
must-FIRE constant-time checks (a draft body structurally cannot be captured); FACTS/Skyward write paths are
honest stubs with no flag workaround; no hidden server-side vendor scraper.
