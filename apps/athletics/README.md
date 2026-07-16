# apps/athletics

> School sports: sport catalog, seasons, team rosters, fixtures, and the four
> eligibility gates an athlete must clear before playing.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 13 models · 3 migrations · 13 test modules · ~6.4k LOC

## What this app owns

Athletics is the whole competitive-sport slice: which sports a school offers,
the seasons it runs them in, the squads it fields, the matches those squads
play, and — the part that actually matters — whether a given student is allowed
on the pitch. It owns the fixture lifecycle, the venue booking that a fixture
holds, the kit fee a roster place invoices against, and the away-fixture link
to a transport route.

The defining design decision is that **eligibility is a recompute-and-cache
snapshot, not a stored flag**. `services/eligibility.py` resolves four
independent school-scoped predicates for a `TeamMembership` — academic average,
attendance rate over a rolling window, medical clearance, guardian consent —
and materializes them into an `EligibilityRecord`. Nothing sets "eligible" by
hand; it is always derived. When the PDP is in enforce mode a policy DENY
overrides the computed answer and forces INELIGIBLE, so a school can add its
own rule without touching this app. Thresholds live in `constants.py`
(`MIN_ELIGIBILITY_AVERAGE`, `MIN_ELIGIBILITY_ATTENDANCE_PCT`,
`ELIGIBILITY_ATTENDANCE_WINDOW_DAYS`) rather than inline, so an operator tunes
them in one place.

The second decision is that this app **borrows rather than forks**. Venue
booking clones the `schoolops.ResourceBooking` exclusion-constraint pattern
verbatim, kit-fee invoicing follows the finance service pattern exactly
(`ComplianceProfile` → AR invoice → single line → `recalculate_invoice`), and
GDPR erasure mirrors `apps.compliance.gdpr_services`. If you are changing one
of those, check the parent pattern first.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `Sport` | `athletics_sport` | Per-tenant sport the school offers; seeded, operator-extendable |
| `Season` | `athletics_season` | A competitive season for a sport within an academic year |
| `Team` | `athletics_team` | A squad that plays fixtures within a season |
| `TeamMembership` | `athletics_teammembership` | A student's place on a team roster — the subject of every eligibility check |
| `CoachAssignment` | `athletics_coachassignment` | Links a coach (User, optionally a TeacherProfile) to a team |
| `Fixture` | `athletics_fixture` | A scheduled match a team plays; carries the SCHEDULED/COMPLETED/CANCELLED status |
| `FixtureResult` | `athletics_fixtureresult` | The recorded score/outcome; its existence is what makes a fixture COMPLETED |
| `FixtureVenueBooking` | `athletics_fixturevenuebooking` | Venue reservation held by a fixture; Postgres `ExclusionConstraint` on overlap where `status="confirmed"` |
| `FixtureTravel` | `athletics_fixturetravel` | Links an away fixture to a transport route (`schoolops.Route`) |
| `EligibilityRecord` | `athletics_eligibilityrecord` | Recompute-and-cache snapshot of a membership's eligibility to play |
| `MedicalClearance` | `athletics_medicalclearance` | Fitness-to-play clearance — GDPR-sensitive PII (`notes` + uploaded `document`) |
| `ParticipationConsent` | `athletics_participationconsent` | One guardian's consent decision for one membership; carries guardian PII |
| `TeamKitFee` | `athletics_teamkitfee` | Kit/participation fee catalog a team's memberships invoice against |

All 13 declared models are listed. Every one carries a `school` FK.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL namespace | `athletics:` | Mounted at `athletics/` in `config/tenant_urls.py` **only** |
| Coach views | `coach_dashboard`, `coach_team_detail`, `coach_fixtures`, `coach_schedule_fixture`, `coach_cancel_fixture`, `coach_record_result`, `coach_add_member`, `coach_eligibility`, `coach_request_consent` | The coach's working surface |
| Admin views | `admin_seasons`, `admin_fixtures` | School-wide season + fixture calendar (capped by `ADMIN_FIXTURE_LIST_LIMIT`) |
| Family views | `family_my_team` | Guardian/student read surface (capped by `FAMILY_FIXTURE_LIST_LIMIT`) |
| Public views | `participation_consent_public`, `participation_consent_decide` | Token-addressed guardian consent — reachable without a login |
| Service | `services/eligibility.py` | The four-predicate resolver + `EligibilityRecord` writer |
| Service | `services/scheduling.py` | `schedule_fixture` / `record_result` / `cancel_fixture` |
| Service | `services/booking.py` | `book_fixture_venue` / `cancel_fixture_venue_booking` / `overlapping_confirmed_count` |
| Service | `services/consent.py`, `fees.py`, `transport.py`, `gdpr.py` | Consent mint/decide, kit-fee invoicing, away-travel link, DSAR export + erasure |
| Management command | `seed_athletics_catalog` | Seeds the per-tenant `Sport` catalog |

No Celery tasks. `apps.py::ready()` imports `signals` inside a `try/except
ImportError` — a deliberate guard from incremental build-out, so a missing
`signals.py` never breaks app loading.

## Before you change this

- **`reverse()` needs an explicit `urlconf=`.** Athletics is registered in
  `config/tenant_urls.py` and nowhere else — it is absent from `config/urls.py`.
  Anywhere the tenant urlconf is not already the active one (tests, a management
  command, an operator-host view), `reverse("athletics:coach_cancel_fixture")`
  raises `NoReverseMatch`. Pass `urlconf="config.tenant_urls"`, as
  `tests/test_fixture_cancel.py` and `tests/test_rbac.py` do. This is host-split
  routing, not a bug to "fix" by also mounting it on the default urlconf.
- **Never cancel a fixture by setting `status` directly.** Use
  `services/scheduling.py::cancel_fixture`. `FixtureVenueBooking.CANCELLED`
  previously had no producer at all, so a cancelled match pinned its venue
  forever — the exclusion constraint only fires on `status="confirmed"` rows, so
  releasing the booking is what frees the slot for a replacement fixture. The
  producer now exists and releases every confirmed booking the fixture holds
  (`cb6d2bffb`). A direct `status` write reintroduces the pin.
- **`cancel_fixture` is idempotent, and refuses COMPLETED.** An already-CANCELLED
  fixture returns unchanged; a COMPLETED fixture (a played match with a recorded
  result) raises `ValueError` for the caller to surface. Do not soften that into
  a silent no-op — cancelling a played match would orphan its `FixtureResult`.
- **The venue exclusion constraint is the backstop, not the check.** The service
  does a `time_range__overlap` pre-check on Postgres and an interval scan on the
  SQLite test lane, but the race-proof guarantee is the model's
  `ExclusionConstraint`. `IntegrityError` is mapped to `BookingConflictError` —
  keep that mapping or callers will see a 500 instead of a conflict message.
- **Two models carry PII and must ride DSAR.** `MedicalClearance` (health notes
  + document) and `ParticipationConsent` (guardian name/email). Erasure
  **preserves every row** and redacts columns in place — FKs stay intact so
  eligibility history and audit chains survive. `TeamMembership` rides the
  export but is never scrubbed. If you add a PII-bearing field, wire it into
  `services/gdpr.py` in the same pass.
- **The consent token is surfaced exactly once**, from `mint`, and is never
  logged. Neither are guardian emails or medical notes. The consent email is
  best-effort by contract — a delivery or import failure must never fail the
  mint.
- **Money is `Decimal`, never float** (`services/fees.py`), per the
  `scan_money_float` zero-tolerance gate.
