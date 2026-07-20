# apps/school_events

> Campus events: venues, the event record, ticket tiers, registrations, and
> sponsor commitments.

**Tenancy:** TENANT (each school gets its own Postgres schema under django-tenants; the RLS migrations add a second, row-level seal on top)
**Scale:** 6 models · 3 migrations · 0 test modules · ~1.1k LOC

## What this app owns

School Events owns the lifecycle of a campus event end to end: where it happens
(`EventVenue`), what it is (`SchoolEvent`, DRAFT → PUBLISHED → COMPLETED /
CANCELED), who is coming (`EventTicketTier` → `EventRegistration`), and who is
paying for it (`EventSponsor` → `EventSponsorCommitment`). It also feeds two
read-side surfaces consumed elsewhere: `upcoming_public_events_for_school` for
public/portal listings and `event_operations_snapshot` for the events hub tile.

The shape worth understanding is the **two-tier tenancy split**. Only three
models carry a `school` FK — `EventVenue`, `EventSponsor`, and `SchoolEvent` —
and those are exactly the three tables the RLS migrations (`0002`, `0003`)
enable and default-deny on. The child tables (`EventTicketTier`,
`EventRegistration`, `EventSponsorCommitment`) have **no** `school` column at
all; they are isolated transitively, through their FK to a parent that has one.
So a query that reaches a child without going through `SchoolEvent` has no
tenant seal under it.

Ticketing and sponsorship are both feature-flagged per event
(`ticketing_enabled`, `sponsorship_enabled`, both default `False`), so an event
is a plain calendar entry until someone opts in.

## Key models

| Model | Table | Purpose |
| --- | --- | --- |
| `SchoolEvent` | `school_events_schoolevent` | The event: status FSM, `start_at`/`end_at`, `is_public`, per-event `ticketing_enabled` / `sponsorship_enabled` flags, `fundraising_goal`. Auto-slugs from `title` on save; unique per `(school, slug)` |
| `EventVenue` | `school_events_eventvenue` | A reusable campus location with a `capacity`, unique per `(school, code)` |
| `EventTicketTier` | `school_events_eventtickettier` | A priced tier on an event: `price` + `currency_code`, `capacity`, `sold_quantity`, and a `remaining_capacity` property |
| `EventRegistration` | `school_events_eventregistration` | One attendee booking: RESERVED / CONFIRMED / CANCELED / CHECKED_IN, `amount_due` vs `amount_paid`, `check_in_at` |
| `EventSponsor` | `school_events_eventsponsor` | A sponsoring organisation with a tier (community → platinum) and a lifecycle status, unique per `(school, name)` |
| `EventSponsorCommitment` | `school_events_eventsponsorcommitment` | A sponsor's pledge against one event; unique per `(event, sponsor)`, aggregated into `sponsorship_total` |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| URL | `school_events:event_hub` | `/…/` — all events for the tenant + operations snapshot |
| URL | `school_events:event_detail` | `/…/<slug>/` — event with tiers and sponsor commitments |
| URL | `school_events:register_for_event` | `/…/<slug>/register/` — POST only |
| Module | `services` | `upcoming_public_events_for_school`, `event_operations_snapshot` |
| Admin | `tenant_admin_site` | All six models registered, with a ticket-tier inline on the event |

Mounted on the tenant host only (`config/tenant_urls.py`). No Celery tasks, no
management commands.

## Before you change this

- **Every view must have a tenant.** All three views bail with
  `HttpResponseForbidden("Tenant context required.")` when `request.school` is
  None, and every lookup passes `school=school` into `get_object_or_404`. The
  slug is unique *per school*, not globally — drop the `school=` kwarg and you
  have a cross-tenant read.
- **The child tables are not RLS-sealed.** `0003_rls_policy_default_deny` covers
  `school_events_eventvenue`, `school_events_eventsponsor`, and
  `school_events_schoolevent` — and only those, because the policy clause keys on
  `school_id`, which the child tables do not have. If you add a `school` FK to a
  child, add it to `SCHOOL_EVENTS_TABLES` in a new migration too, and if you
  query a child directly, scope it through its parent yourself.
- **`register_for_event` enforces capacity via `register_for_tier`.** The service
  locks the tier with `select_for_update`, refuses oversell against
  `remaining_capacity`, and increments `sold_quantity` with an `F()` update.
  Paid tiers land RESERVED; free tiers land CONFIRMED.
- **Registration does not take card/mobile money in-app.** The service sets
  `amount_due` from `price × quantity` and starts paid tiers at RESERVED with
  `amount_paid = 0`. Free tiers go straight to CONFIRMED. Cash/manual settle and
  unpaid-hold release live in `confirm_registration_payment` /
  `release_reservation` (tenant admin actions). Abandoned holds age out via
  `expire_stale_reservations` / `manage.py expire_stale_event_reservations`.
  Successful finance webhooks may settle a hold when payload metadata carries
  `event_registration_id`. Live PSP ticket capture remains EXTERNAL.
- **`fundraising_goal` is a stored target, not a tracked total.**
  `event_operations_snapshot` sums `sponsor_commitments__pledged_amount` into
  `sponsorship_total`; nothing compares the two or verifies a pledge was paid.
  `EventSponsorCommitment.status` (PLEDGED → ACTIVE → FULFILLED) is set by hand.
- **The slug auto-fills only when blank.** `SchoolEvent.save()` slugifies the
  title on first save, then leaves it alone — renaming an event deliberately does
  not break its existing links.
- **There is no Club model in this app or anywhere else.** Clubs are a roadmap
  catalog entry only. Do not wire a surface against one.
- `tests.py` is a single module at the app root (not a `tests/` package), which is
  why automated per-app test-module counts read this app as zero. It does cover
  the hub, registration, and cross-tenant isolation.
