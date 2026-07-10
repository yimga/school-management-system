# Athletics / Sports-Management Module — Design & Build Record

**Wave:** 9.8-regime A-wave (2026-07-09). **Prior audit:** athletics 2.5/10 (capability entirely absent; two empty marketplace listings advertised it — a contradiction). This module builds the athletics spine end-to-end and reconciles the marketplace.

## Scope (v1)

Athletics IS the competitive-sports spine generic clubs are not: teams that play scheduled fixtures with rosters, coaches, seasons, results, athlete eligibility (academic + attendance + medical), guardian participation consent, venue booking with double-booking prevention, kit/participation fees, and away-fixture transport.

**Non-goals (v1):** per-play statistics, cross-school league standings/brackets, live scoreboards, public inter-school fixture federation (opponents are free-text; internal house matches use a same-school self-FK), athlete performance ML, wearables ingest, spectator ticketing (that stays in `apps/school_events`). Extracurricular clubs are a distinct, separately-dispositioned capability — athletics does not subsume them.

## App layout — `apps/athletics/`

`apps.py` (AthleticsConfig, `ready()` imports signals) · `constants.py` (all magic numbers) · `models/` package (catalog, team, roster, consent, eligibility, fixtures, booking) · `services/` (eligibility, consent, scheduling, booking, fees, transport, gdpr) · `views/` (coach, family, admin_console) · `urls.py` · `admin.py` · `forms.py` · `templates/athletics/` · `migrations/` · `tests/` · `management/commands/seed_athletics_catalog.py`.

## Data model (13 models, all `school` FK, all RLS-enrolled)

Sport, Season, TeamKitFee (catalog) · Team, CoachAssignment (team) · TeamMembership, MedicalClearance (roster) · ParticipationConsent (consent — clones `people.TransferConsent` token discipline) · EligibilityRecord · Fixture, FixtureResult, FixtureTravel · FixtureVenueBooking (double-booking prevention — clones `schoolops.ResourceBooking` `ExclusionConstraint`).

Migrations: `0001_initial` (all models; the venue-booking `ExclusionConstraint` ships via `SeparateDatabaseAndState` — state `AddConstraint` + Postgres-guarded `RunPython` + `BtreeGistExtension`, so the SQLite test lane skips the gist constraint), `0002_enable_rls_postgresql`, `0003_rls_policy_default_deny` (both clone `school_events`). App registered in `INSTALLED_APPS` (RLS mode) and `TENANT_APPS` (schema mode).

Roster integrity: partial-unique `uniq_active_membership_per_team` (one active membership per student) and `uniq_active_jersey_per_team` (no shared active jersey). Coach: partial-unique `uniq_active_coach_per_team`.

## RBAC

New `COACH` extended role (`role_registry.ROLE_COACH`, `permissions.ROLE_RANK["COACH"]=55`, `ROLE_CATEGORIES["Athletics"]`). Codes `athletics.view` / `athletics.manage` / `athletics.eligibility.override` / `athletics.medical.manage`, seeded by `accounts/0050_athletics_rbac_codes` (creates the COACH AccessRole; additive `.add()`, idempotent). `MODULE_ACCESS_DEFAULTS["athletics"]` registers read (coach + academic tier + family) and write (coach + academic leadership). `apps/athletics` added to `scan_granular_rbac_adoption._OPERATIONAL_APP_DIRS` (zero-tolerance coarse-gate ratchet). Every view gates on `@require_permission`; coach write actions additionally check `effective_access.athletics_team_manage_access(user, school, team_id)` (code + active CoachAssignment).

## Services

`eligibility.resolve_eligibility` (academic/attendance/medical/consent predicates → EligibilityRecord; optional PDP consult under enforce mode) · `consent.request_participation_consent` / `record_consent_decision` (token discipline; membership PENDING→ACTIVE on consent) · `scheduling.schedule_fixture` / `record_result` · `booking.book_fixture_venue` (clones `schoolops.booking_services`; SQLite pre-check + DB exclusion backstop) · `fees.raise_kit_fee_invoice` (Decimal end-to-end via `apps.finance`) · `transport.link_away_fixture_transport` (`schoolops.Route`).

## Migration round-trip

Three landers (`athletics_teams`, `athletics_memberships`, `athletics_fixtures`) cloning `transport_assignment_lander` discipline (real-fields-only via `filter_to_model_fields`, DFV fallback, per-row quarantine — never silent-drop). Accelerator `CANONICAL_FILENAME_TO_DOMAIN` + `DOMAIN_CANONICAL_HEADERS` extended; both `companion-*/canonical_headers.json` mirrors updated in lockstep (drift gate stays 0). Medical clearance + participation consent do NOT ride the generic migration path (PII) — they ride the GDPR DSAR export only.

## GDPR

`services/gdpr.py::athletics_export_sections` / `athletics_scrub_student` woven into `compliance.gdpr_services.export_student_data_portability` + `gdpr_scrub_student` — memberships/medical/consent export in DSAR; medical notes + consent guardian PII redacted-in-place on erasure (rows preserved for referential integrity).

## Portal / UX

Coach console (my-teams, eligibility board, fixtures, record result, consent tracker); family student/parent team + fixture pages; admin season/fixture console; anonymous token-based participation-consent public page. Sidebar registered in `portal_sidebar_items.py` (staff block + grant-responsive coach block + student/parent blocks).

## Marketplace reconciliation

`specialty-athletics-eligibility` listing → real backed listing (widgets deep-link into the module). `specialty-extracurricular-clubs` → honestly labeled `status: roadmap` (not falsely pointed at athletics).

## Test plan

Unit + failure-injection: cross-tenant leakage negatives (`@tag("tenants_rls")`), ineligible-athlete-blocked, consent-missing-blocked, double-booked-venue-rejected (service + DB exclusion), kit-fee-is-Decimal, GDPR round-trip, lander real-fields-only, RBAC (coach-scoped, non-granted 403, anonymous redirect).

## Gate compliance

tenant queryset/marker-quality (every query scoped/marked), granular-rbac (0, athletics in op-dirs), role-strings (ROLE_COACH constant, no literals), magic-numbers (constants.py), print/bare-except (0), reference-integrity family (0), companion-headers-drift (0), makemigrations --check clean, SW CACHE_VERSION bump.
