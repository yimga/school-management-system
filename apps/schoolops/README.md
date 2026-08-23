# apps/schoolops

> Everything a school runs that is not a lesson: transport, hostels, canteen and
> the campus wallet, inventory, library, clinic, front desk, facilities,
> substitutes — plus the platform's transactional email spine.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 30 models · 34 migrations · 33 test modules · ~18.7k LOC

## What this app owns

Schoolops is the operations grab-bag, and that is deliberate: these are the
surfaces a school touches daily that share no domain with each other but share
every constraint — they run on a phone at a gate or on a bus, often without
signal, and they must never double-count.

Two things here are worth knowing before anything else.

**This app was carved out of `apps.schools`, and the tables did not move.**
Most models declare `app_label = "schoolops"` but pin `db_table = "schools_*"`
(`schools_bus`, `schools_campus`, `schools_inventoryitem`, …). Migration `0001`
is a `SeparateDatabaseAndState` that relocated Django's *state* only, and `0002`
materializes the tables into tenant schemas that never had them. Models added
after the split use `schoolops_*` names. The two prefixes in the table column
below are therefore a historical record, not an inconsistency to clean up.

**Second, this app also owns the platform's outbound transactional email** —
which is not an operations concern at all, but is where the delivery spine
landed. `email_delivery` is the canonical surface in front of
`django.core.mail`: it retries, records an append-only `EmailDeliveryEvent`,
never raises at the caller, consults the `SuppressedRecipient` list *before*
every send, and parks permanently-failed retry-eligible sends in an encrypted
`EmailDeadLetter` for redrive. The suppression list exists because the platform
used to record hard bounces and then mail the same dead address again on every
subsequent trigger — which is how a school's sender reputation dies (Gmail and
Yahoo bulk-sender rules require a spam-complaint rate under 0.3%).

## Key models

The 15 that carry the app, of 30 declared.

| Model | Table | Purpose |
| --- | --- | --- |
| `InventoryItem` | `schools_inventoryitem` | Stock line. `quantity` is a cached total the movement ledger owns |
| `InventoryMovement` | `schoolops_inventorymovement` | The ledger: one append row per stock change, with `quantity_after` |
| `PosSaleLine` | `schools_possaleline` | A till / POS sale line |
| `MealPlanBalance` | `schools_mealplanbalance` | A student's running cafeteria / campus-wallet balance |
| `CanteenMeal` | `schools_canteenmeal` | Canteen menu item |
| `HealthRecord` | `schools_healthrecord` | Clinic record; allergy rows feed the POS allergen barrier |
| `Route` / `Stop` / `Bus` | `schools_route` / `schools_stop` / `schools_bus` | Transport network |
| `TransportAssignment` | `schools_transportassignment` | A student's join to a route, with stops + effective window |
| `BusBoardingEvent` | `schoolops_busboardingevent` | Append-only passive RFID/NFC/QR tap as a student boards or alights |
| `Hostel` / `HostelRoom` / `HostelAssignment` | `schools_hostel` / `schools_hostelroom` / `schools_hostelassignment` | Boarding, down to bed label + effective window |
| `LibraryItem` / `LibraryLoan` | `schools_libraryitem` / `schools_libraryloan` | Catalog + circulation |
| `VisitorCheckIn` | `schools_visitorcheckin` | Front-desk visitor log — the one ops surface with an offline write path |
| `SubstituteCover` | `schools_substitutecover` | Cover assignment |
| `SubstituteHandoverPacketRecord` | `schoolops_substitute_handover_packet` | Redacted, time-boxed handover packet, minted online or replayed from the offline queue |
| `EmailDeliveryEvent` | `schoolops_email_delivery_event` | Append-only forensic log of every transactional / bulk send |

Also here: `SuppressedRecipient` and `EmailDeadLetter` (the email spine),
`MaintenanceRequest`, `BookableResource` / `ResourceBooking`, `Campus`,
`BiometricDevice` / `BiometricAttendanceLog`, and the lost-belongings pair
`LostBelongingsTagRecord` / `LostBelongingsCustodyEventRecord`.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `inventory_services` | `record_inventory_movement` + checkout / transfer / return / consume / loss. The only sanctioned stock write path |
| Module | `pos_checkout` | Cashless campus wallet: resolve credential → allergen barrier → atomic wallet debit → `PosSaleLine`. Decimal-safe, idempotent |
| Module | `email_delivery` | `send_transactional` / `send_bulk` / `smtp_probe` / `get_resolved_smtp_config` |
| Module | `boarding_monitor` | Idempotent tap capture; the reader hardware is abstracted |
| Module | `route_optimizer` | Offline greedy nearest-neighbour over haversine distance. No map API, no extra deps |
| Module | `booking_services` | Postgres exclusion constraint for capacity=1 resources |
| Module | `substitute_market` | Cache/Redis locks against double-booking + Channels fan-out on `school-{id}-substitute-market` |
| Module | `substitute_handover` | Redacted, expiring packet for a substitute |
| Module | `lost_belongings_qr` | Anonymous finder → custody log → parent notification |
| Module | `field_trip` | Consent via `compliance.ConsentRequest` + an offline medical checklist |
| Module | `offline_workflow_handlers` | Offline write handlers — visitor check-in only, by design |
| Module | `notification_intent`, `notification_batch` | Server-owned intents; batching so sweeps don't stampede the broker |
| Module | `schema_repair` | Idempotent ADD COLUMN / CREATE INDEX heal for django-tenants schema drift |
| Celery | `dispatch_transactional_email`, `dispatch_bulk_email` | Email send paths |
| Celery | `notify_low_inventory_stock`, `sweep_low_inventory_stock` | Reorder alerting |
| Celery | `notify_low_meal_plan_balance`, `sweep_low_meal_plan_balances` | Wallet low-balance alerting (7-day cooldown) |
| Celery | `deliver_notification_intent_task` | Intent delivery |
| Command | `redrive_email_dead_letters`, `verify_email_dns`, `test_email_health` | Email operations |
| Command | `optimize_bus_route` | Runs the route optimiser |

This app has **no `urls.py`**. Its views (`views_tenant_ops`, `views_email_admin`,
`views_lost_belongings`, `views_substitute_handover`, …) are routed from
`apps/accounts/urls.py`; the email provider webhook is wired directly in
`config/urls.py`.

## Before you change this

- **Stock changes go through `record_inventory_movement`. Always.** A bare
  `.update()` or `save()` on `InventoryItem.quantity` desyncs
  `sum(movements)` from the cached total *and* skips the post_save low-stock
  reorder alert. The POS till in `views_tenant_ops.py` shipped exactly that bug —
  a raw decrement with a `quantity__gte` filter — and now routes through the
  ledger with `MovementType.CONSUME` (stock permanently leaves via the sale),
  relying on the ledger's below-zero guard for the same oversell protection the
  old filter gave. The inline comment there explains why; leave it.
  Note that `pos_checkout.py` (the cashless wallet) legitimately writes no
  movement — it debits `MealPlanBalance` and never touches `InventoryItem`.
- **Only an append-only event log is a safe offline write, and that scoping is
  deliberate.** `offline_workflow_handlers` covers visitor check-in and nothing
  else. Library loans and transport assignments mutate a *shared, limited*
  resource (a copy of a book; a seat) — queueing them offline would let two
  disconnected devices issue the same book and both "win" on drain, i.e. it
  would manufacture the conflict offline support exists to avoid. The clinic
  page is GET-only. Read still works offline via cache. Do not widen this
  without a conflict-resolution story.
- **The email PII contract is strict.** `EmailDeliveryEvent` stores
  `to_hash = sha256(to)[:12]`, a 64-char `subject_prefix` snapshot, and never
  the body, the recipient address, or the from-address. `EmailDeadLetter` is the
  one place a renderable copy must exist (a redrive cannot reconstruct the mail
  otherwise) — so its whole payload is Fernet-encrypted at rest on the same key
  chain as the stored SMTP password, and it is opt-in via
  `settings.SCHOOLOPS_EMAIL_DLQ_ENABLED`. Hard bounces, suppressions, and
  header-injection failures are **not** DLQ-eligible; only transient ones are.
- **Check the suppression list before sending.** `SuppressedRecipient` is the
  SOT on the send hot path. A new send path that skips it re-opens the
  reputation bug.
- **The low-balance signal fires once per False → True transition.** The
  pre-save handler caches `is_low` on the instance and post_save compares —
  `refresh_from_db` would race the in-flight UPDATE. Dispatch failure logs at
  WARNING and never raises: a notification glitch must not poison the save
  transaction. Never log addresses, phone numbers, names, or balance numerics
  there — PK plus student/plan id only.
- **`db_table = "schools_*"` is load-bearing.** Renaming a table to match the
  app label would orphan live tenant data. `schema_repair.py` exists precisely
  because tenant schemas provisioned before a migration land short of a column
  and hard-500; it is idempotent and must stay collision-free with `0022`/`0023`
  on replay.
- **The allergen barrier defaults to ON.** `_allergen_enforced` returns True
  when the tenant setting is absent — safety-first, block until explicitly
  disabled. Matching folds plurals and compounds (`_term_matches_token`)
  because a canteen writes "Peanuts" and "Chocolate Milkshake", not the bare
  allergen word; the 4-character floor on interior substrings is what keeps
  "raw" from blocking "strawberry". `pos_checkout` is Decimal throughout and
  idempotent per `idempotency_key` — enforced by the
  `uniq_possaleline_school_idem` partial unique index, because the pre-insert
  read cannot see an uncommitted concurrent replay. Keep all three.
- **`boarding_monitor` taps are idempotent by key** so an offline bus can replay
  a queue without double-counting. `route_optimizer` is an honest greedy first
  cut, not a VRP solver — stops without coordinates keep their sequence rather
  than being dropped.
- **The field-trip medical checklist is deliberately not PII-masked.** Unlike
  the auditor view, the supervising teacher needs the child's real name,
  allergens, and emergency contact to keep them safe. It is a confidential
  operational document; treat it as one.
