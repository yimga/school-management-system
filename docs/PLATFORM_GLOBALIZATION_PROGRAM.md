# Platform Globalization Program

**Opened 2026-07-21.** Derived from the seven-dimension tenant-wide audit of 2026-07-20
(offline-first reality, 250-country i18n, platform extensibility, academic-domain completeness,
multi-tenancy/scale/residency, low-bandwidth/emerging-market UX, compliance/security).

This document is the executable specification for that audit. Each item states the **defect**,
the **fix**, and an **acceptance criterion that must be a must-fire test** — a test that fails
if the fix is reverted. Items are ordered by dependency, not by size.

## The premise

RunMyCampus intends to be the AWS / Linux / Salesforce / Shopify of school management: the
substrate other people build on, in 250+ countries, local-first and offline-capable. The audit
found the platform is closer to that than its own documentation suggests in some places, and
further in others. The gap is not usually "unbuilt" — it is **built and unwired**.

## The systemic finding (read before doing anything else)

Seven auditors with seven different mandates independently found the same failure mode:
**a declared capability with no runtime path**, reported as working.

- capability flags with no consumers
- models with no producers
- adapters that return `success=True` without sending
- middleware declared and never loaded
- CI gates that are structurally incapable of failing

The last one is the multiplier. A gate that cannot fail manufactures confidence, and several
of this platform's green gates guard nothing. **Every item below must ship with a test that
fails when the fix is removed.** A negative "must-not-flag" test can never detect a dead guard.

## Non-negotiables for every item in this program

1. **Global by default, Cameroon as one instance.** No item may encode a single country's
   education system, calendar, grading scale, currency, or statutory return as structure.
   Country-specific behaviour is *data* (a row, a preset, a locale), never a column name,
   a hardcoded choice list, or a branch.
2. **Probe the effect, not the source line.** A setting that executes proves nothing about
   whether the write lands. Prove the behaviour changed.
3. **Producer and consumer, or it does not ship.** A model with no writer, a flag with no
   reader, and an adapter with no transport are all the same defect.
4. **Fail closed.** Where a guard cannot determine safety, it denies.
5. **Ship inert where money or user-visible behaviour changes** until explicitly enabled.
6. **No hardcoding** — the 7-layer configurability contract in `CLAUDE.md` applies throughout.

---

# TIER 0 — Active exposure

Ships first. Each is small; each is currently causing harm or legal risk.

## 0.1 — Student PII reaches an external LLM

**Defect.** `services/ai_gateway.py::_data_tier_allows_premium` decides whether a payload may
go to the external `LITELLM_PROXY_URL`. It delegates to `_payload_contains_pii`, which returns
`False` when `services.inference.strip_pii_for_inference` cannot be imported — so an import
failure *permits* the external call. The detector also only recognises what
`strip_pii_for_inference` rewrites; a child's name, date of birth, grades, SEN status, or a
safeguarding narrative is classified not-PII and posted verbatim.

Redaction exists in the codebase and is used only as a *detector* — the string that gets sent
is the original, not the redacted one.

**Fix.**
- `_payload_contains_pii` must return `True` (assume PII) when the redactor is unavailable.
- `_data_tier_allows_premium` must deny when the sensitivity class is unknown, not only when
  it is explicitly `high`.
- The outbound payload for any external tier must be the **redacted** text, not the original.
- Structured metadata (student names, DOB, guardian contacts) must be scrubbed on the same path.

**Acceptance (must-fire).**
- A test that monkeypatches the redactor import to fail and asserts premium is **denied**.
- A test that sends a payload containing a name+DOB and asserts the bytes handed to the
  external transport contain neither.
- Reverting either fix must turn the test red.

**Global note.** PII patterns are locale-dependent (name order, national ID formats, phone
shapes). The redactor must be extensible per-country, not regex-frozen on one format.

## 0.2 — SMS is a no-op in every emerging market

**Defect.** Neither `twilio` nor `africastalking` appears in `requirements.txt` or
`requirements_optional.txt`. The routing table points at both. Every feature-phone parent in
CM/NG/KE/GH receives nothing, silently.

**Fix.** Pin both SDKs. More importantly, **a missing transport must be loud**: an adapter whose
SDK is absent must refuse to register (or register as unavailable), never register and silently
drop. Selection must skip unavailable adapters and raise `ChannelUnavailableError` when no
usable adapter exists for a channel.

**Acceptance (must-fire).** A test that simulates the SDK being absent and asserts the adapter
does not report a successful send. Reverting must turn it red.

## 0.3 — USSD and IVR report success while sending nothing

**Defect.** `apps/communication/channel_adapter.py::register_log_only_defaults` registers
`_LogOnlyAdapter` for six channels including `ivr` and `ussd`, at cost ranks 30 and 25.
`_LogOnlyAdapter.send` returns `DeliveryResult(success=True, detail="log-only")`. The registry
selects by cost, so a dispatcher asked for the cheapest reachable channel can pick one of these
and report delivery.

USSD and IVR are the two channels that matter most in the markets this platform targets.

**Fix.** `_LogOnlyAdapter` must be honest: either it is a *test/offline* adapter that is never
registered in a deployed configuration, or it returns `success=False` with a detail explaining
no transport is configured. Deployed registration of a log-only adapter must require an explicit
opt-in setting, and must be visible in the delivery audit.

**Acceptance (must-fire).** A test asserting that under a production-like configuration, a send
on a channel with no real transport does **not** yield `success=True`.

## 0.4 — Offline work is silently discarded

**Defect.** `static/js/offline-queue-client.js::writeOutboxLS` persists the outbox to
localStorage and swallows `QuotaExceededError`. There is no cap, no eviction policy, and no
warning, while the UI reports "Saved on this device". The service-worker queue's
`enforceQueueLimit` deletes the oldest entries with no signal. Two of the three offline rails
can lose a teacher's day of work without telling anyone.

**Fix.**
- `writeOutboxLS` must detect a failed write and surface it: the enqueue call reports failure,
  the UI must not claim the write was saved.
- A cap with an explicit, documented eviction policy — and eviction must emit a user-visible
  warning, not a console line.
- Back-pressure: when the outbox is near capacity, the UI warns before the user does more work.

**Acceptance (must-fire).** A test that fills storage, attempts an enqueue, and asserts the
enqueue reports failure (not success). Reverting the swallow-fix must turn it red.

**Global note.** This matters most exactly where connectivity is worst — multi-day offline is
the design target, not an edge case.

## 0.5 — RLS regression introduced 2026-07-18

**Defect.** `billing_processorrevenueshareaccrual` (shipped in `8c9654ae9`) is not covered by
row-level-security enablement, taking `scan_rls_table_coverage` from 121 to 123.

**Fix.** Enable RLS for the new table via the app's enable-RLS migration path.

**Acceptance.** The RLS coverage scanner returns to its prior baseline or lower. Note the known
blind spot: these migrations hard-code a TABLES list, so the scanner's file-pairing check can
report clean while tables are uncovered — re-derive with `scan_rls_table_coverage.py`, do not
trust the pairing gate.

---

# TIER 1 — Structural honesty

Nothing below Tier 1 can be trusted until Tier 1 lands, because Tier 1 is what makes "declared"
mean "loaded" and "green" mean "verified".

## 1.1 — MIDDLEWARE is declared twice; the first list is dead code

**Defect.** `config/settings.py` builds `MIDDLEWARE` at line 351 and extends it at 441. At line
4098, inside the `USE_DJANGO_TENANTS` branch, it is **reassigned** — replacing the list wholesale.
`render.yaml` sets `USE_DJANGO_TENANTS=1`, so in production the base list never loads. Roughly
22 middleware — including CSP, the compliance guard, data-residency routing, and the defender —
are dead code in prod while appearing present in the file.

The SQLite test settings take the *base* branch, so middleware tests are false-green: they
exercise a list production never uses.

**Fix.** One `MIDDLEWARE` list. The tenancy branch may *insert* the tenant middleware at the
correct position, never reassign. Any middleware intentionally excluded under tenancy must be
excluded explicitly and named.

**Acceptance (must-fire).** A test that imports the **parsed settings under the tenancy
configuration** and asserts each security/compliance middleware is present by dotted path.
It must fail if the reassignment returns. Testing the base branch is not acceptance.

**Consequence.** This one fix restores CSP, ComplianceGuard, residency routing and the defender
simultaneously. Several Tier-6 items are unverifiable until it lands.

## 1.2 — Gates that cannot fail

**Defect.** Multiple CI gates are green while what they guard is broken.

- `verify_offline_capability_implementation.py` reports `finding_count: 0, latent: 0` but is a
  **text scan over a concatenated JS blob**: a matching string in a comment satisfies it. This
  is why a capability with zero runtime existence reports `producer: true, server: true,
  ui_surface: true`.
- `scan_locale_coverage.py` only trips on *regression*, so a locale at 0% translated stays
  permanently green.
- `scan_rls_table_coverage` checks file pairing, not table membership (see 0.5).
- A zero-tolerance gate forces CSP nonces into templates for a policy that is never sent (1.1).

**Fix.** For each: replace presence-detection with behaviour-detection, and prove it with a
negative control — a test that **reintroduces the defect and asserts the gate turns red**. Any
gate without a must-fire test is not a gate.

The offline gate specifically should be driven by the Playwright offline harness already present
and unused in the repo (`playwright.offline-indexeddb.config.js`), not by string matching.

**Acceptance.** Each rewritten gate ships with a must-fire test. A gate that cannot be made to
fail must be deleted rather than left green.

---

# TIER 2 — The country-neutral academic spine

This is the deepest blocker to the 250-country ambition and the largest body of work. The
academic schema currently encodes one country's model as database structure.

Sequenced so each step is independently shippable.

## 2.1 — Country → grading-scale resolution (cheapest, do first)

**Defect.** Multiple national grading scales are fully built but unreachable because nothing
resolves a school's country to a scale. Related: `resolve_school_score_scale(None)` returns 100,
so an out-of-range mark (25 on a 20-point scale) is accepted.

**Fix.** A data-table resolution from country → default scale, overridable per school. The
`None` case must fail closed, not default to 100.

**Acceptance (must-fire).** A test per unlocked scale proving a school in that country gets it,
plus a test that an out-of-range mark is rejected under a 20-point scale.

## 2.2 — `Enrollment` as a first-class entity

**Defect.** There is no enrollment record. Promotion is a destructive `UPDATE` on the student
row: last year's class is overwritten and lost, **repeating a year cannot be expressed**, and
the promotion job ignores `PromotionRule`, promoting failing students identically.

This blocks: academic history, transcripts, re-enrollment, retention, statutory returns, and
any longitudinal analytics.

**Fix.** `Enrollment(student, academic_year, class/section, status, entry_date, exit_date,
outcome)` with the student's current class derived from the active enrollment. Promotion writes
a new enrollment and closes the prior one; it never overwrites. `PromotionRule` must be honoured,
including retention and conditional promotion.

**Acceptance (must-fire).** A test that promotes a cohort, asserts prior-year enrollments still
resolve, and asserts a student meeting a retention rule stays in grade. A test that a student
can hold two enrollments in the same grade in different years.

## 2.3 — Curriculum allocation (`periods_per_week`)

**Defect.** No `periods_per_week` field exists anywhere in the tree. Every subject implicitly
gets exactly one lesson per week. Maths five times weekly, double laboratory blocks, and
two-week rotating cycles are unrepresentable.

**Fix.** A `CurriculumAllocation(class/section, subject, periods_per_week, block_length,
cycle_length)` so the timetable solver has a real demand model. Cycle length must support
n-week rotations, not just 1.

**Acceptance (must-fire).** A test that a subject allocated 5 periods produces 5 scheduled
lessons, and that a 2-week cycle produces a different week-B schedule.

## 2.4 — Tenant-scope `Room` and `TimeSlot`

**Defect.** Neither carries a school FK, so two tenants cannot both define an 08:00 period.

**Fix.** School FK + uniqueness scoped per school. Backfill existing rows.

**Acceptance (must-fire).** A test that two schools independently define the same period label
and the same room name without collision.

## 2.5 — Per-period attendance

**Defect.** Attendance is daily-only. The UK, France, India, Nigeria and the United States
legally require a register for **every lesson**. Also observed: attendance NULLs and a school
FK that was nullable.

**Fix.** Attendance keyed on the scheduled lesson, with daily attendance derived from it (or
configured as the school's mode). A school configures daily *or* per-period; both must be
first-class, neither hardcoded.

**Acceptance (must-fire).** A test that a per-period school records two different states in one
day, and that a daily-mode school is unaffected.

## 2.6 — Generic assessment structure

**Defect.** Assessment is eight fixed columns (`seq1`, `seq2`, `mock`, …). This cannot express a
US gradebook, IB, A-levels, or CBSE. Zero matches in the tree for `resit`, `moderation`, or
`remark`.

**Fix.** `AssessmentComponent(scheme, name, weight, max_score, sequence)` + `Mark(component,
student, score, status)`, with the existing fixed columns expressed as one seeded scheme so
current tenants are unaffected. Add resit / moderation / remark as component statuses.

**Acceptance (must-fire).** A test that builds a non-Cameroonian scheme (e.g. a weighted US
gradebook and an IB 1–7 scheme) end to end through to a report card, and a regression test
that the existing scheme still produces identical output.

## 2.7 — Report cards beyond one country

**Defect.** Report-card templates exist in Cameroonian variants only.

**Fix.** Report cards render from the assessment scheme + grading scale + locale, with country
presets as data. A bulk generator exists; keep it.

**Acceptance (must-fire).** A report card generated for at least three structurally different
systems from the same code path.

---

# TIER 3 — Make offline real

The SODP rail is genuinely well built — real idempotency, conflict flagging, and it **fails
loudly** rather than faking success. The gap is not the queue. It is that the app cannot be
*opened* offline.

## 3.1 — Cache application HTML

**Defect.** `service-worker.js::networkFirstNavigation` deliberately never caches authenticated
HTML, and `STATIC_ASSETS` contains no application route. A teacher who opens a laptop offline
the next morning gets `/offline/` for everything. Both offline rails therefore only work inside
the "already on the page, then lose signal" window — which is not what offline-first means.

A `routes_allowlist` manifest was built to fix exactly this and has **no consumer**.

**Fix.** Wire `routes_allowlist` into the service worker: allowlisted authenticated routes are
cached per-user with an explicit freshness policy and are purged on logout / tenant switch.
Caching authenticated HTML is a real security decision — scope it per session, never share
across users on a shared device.

**Acceptance (must-fire).** A Playwright test that loads a route online, goes offline, performs
a **cold load** of that route, and asserts the application renders. This is the single most
important test in this program.

## 3.2 — Offline receipt artifact

**Defect.** A parent paying cash offline gets a toast, not proof. In low-connectivity markets
the receipt is the only evidence the transaction happened. Report cards, PDFs, receipt printing
and invoice viewing also do not work offline.

**Fix.** A locally-generated, verifiable receipt artifact at capture time, reconciled on sync.

**Acceptance (must-fire).** A test that an offline payment capture produces a retrievable
receipt with a stable identifier that survives sync without duplicating.

## 3.3 — Reachability instead of `navigator.onLine`

**Defect.** `navigator.onLine` is the sole offline trigger. It reports `true` on captive portals
and degraded 2G, so the native POST hangs and nothing queues. A `reachabilityUrl` is emitted and
never consulted.

**Fix.** Consult the reachability probe with a short timeout; treat probe failure as offline.

**Acceptance (must-fire).** A test simulating "online but unreachable" that asserts the write is
queued rather than hung.

## 3.4 — Reconcile the three rails

**Defect.** `CLAUDE.md` documents two offline rails. There are **three**: SODP/OfflineAction,
WAL, and an undocumented service-worker `sync-queue` (`isApiWriteRequest` → its own IndexedDB
with independent caps, backoff and 4xx-drop). Three rails, three different durability and
data-loss policies.

Separately, the WAL rail **cannot run in shipped production**: `wal_stream_client_enabled()`
requires `WEB_SERVER_MODE=asgi` and `RMC_WAL_STREAM_ENABLED`; `render_start_web.sh` defaults to
`wsgi` and `render.yaml` sets neither. Teacher/parent messaging outbox has no SODP fallback and
is therefore dead offline.

**Fix.** Decide: either enable the WAL rail in production configuration, or retire it and give
messaging a SODP fallback. Document the third rail or fold it into one of the other two. One
conflict policy, one durability policy, one documented map.

**Acceptance (must-fire).** A test asserting the messaging outbox survives an offline compose
under the shipped production configuration.

## 3.5 — Conflict semantics

**Defect.** SODP flags and blocks conflicts (correct). WAL performs capture-time
last-writer-wins and **silently discards the loser** into a Redis stream with no UI.
`_apply_grade` uses `bulk_create(ignore_conflicts=True)`. Freshness reads fail **open**.

**Fix.** One conflict policy across rails: never silently discard a user's write. Freshness
reads fail closed.

---

# TIER 4 — The developer platform

The hard parts are built: scope model, install governance, kill-switch, a real event bus
(14 events, HMAC-signed, DLQ + replay), and interop (LTI 1.3, OneRoster, SCIM, SAML, Ed-Fi).
What is missing is the seam.

## 4.1 — A third-party credential must authenticate

**Defect.** There is no DRF authentication class that reads an API key or OAuth token, so a
third-party app hits the core API as `AnonymousUser` and receives 401. The entire ecosystem is
blocked on one missing class.

**Fix.** A DRF auth class resolving API keys and OAuth tokens to a principal carrying its
tenant + granted scopes, enforced against the existing scope model.

**Acceptance (must-fire).** A test that a scoped token reads exactly what its scopes allow and
is denied everything else, including cross-tenant reads.

## 4.2 — Self-serve app registration

**Defect.** `DeveloperApplication` exists; its only producer is a test. No developer can register
an app.

**Fix.** Registration flow producing credentials, with review/approval state.

## 4.3 — App runtime and quotas

**Defect.** The "sandbox" is a 33-line queryset filter. There are no per-(app, tenant) quotas,
so one badly-behaved integration degrades a tenant.

**Fix.** Per-(app, tenant) rate and resource quotas enforced on the API path, with the
kill-switch already built as the escalation.

## 4.4 — Public API surface

**Fix.** A published OpenAPI covering the core domain (students, enrollments, attendance,
assessment, finance), versioned, with the interop connectors as first-class citizens.

---

# TIER 5 — Scale and residency

## 5.1 — Transaction-local tenant binding

**Defect.** Tenant binding uses session-level `search_path`, which is architecturally
incompatible with PgBouncer transaction pooling. This caps connection scaling.

**Fix.** Bind the tenant per transaction. This is the single unlock for connection pooling.

**Acceptance (must-fire).** A test proving tenant isolation holds when connections are reused
across tenants within a pool.

## 5.2 — Provisioning and migration throughput

**Defect.** 311 tables per schema × 10k tenants is 3.11M tables; serial migrations project to
multi-hour deploys. Realistic ceiling is ~1–3k tenants, not 10k.

**Fix.** Template-schema clone provisioning + parallel migration execution. Measure before and
after; publish the real ceiling.

## 5.3 — Per-tenant Celery queues

**Fix.** So one tenant's batch cannot starve another's.

## 5.4 — Residency honesty

**Defect.** "EU data is in EU" is not currently true: the residency middleware is in the dead
list (see 1.1), replica aliases can never resolve (`eu_central` vs `replica_eu_central`), only
48 of 250 countries are mapped, and everything is on one database instance.

**Fix.** Either implement residency properly (unify alias resolution, complete the country map,
provision real regional instances) **or stop claiming it** in marketing and contracts. There is
no acceptable middle state — this is a representation made to customers.

---

# TIER 6 — Compliance you can sell on

Depends on 1.1 (the compliance guard is currently unloaded).

## 6.1 — Consent graph and age gating
`consent_services` has no producer. Age-of-consent varies by country (13 US COPPA, 16 default
GDPR with member-state variation down to 13). Must be data, not a constant.

## 6.2 — DSAR export artifact
A DSAR registry exists; `ExportJob` has no producer. A subject-access request must produce a
real, complete, machine-readable artifact within the statutory window.

## 6.3 — Retention execution
`RetentionRule` has no producer. Rules that never execute are worse than no rules — they are a
documented policy you are demonstrably not following.

## 6.4 — Field-level encryption on student PII
The mechanism exists (`EncryptedBinaryField`) and is applied to legacy hashes, not to student
records.

## 6.5 — Audit coverage on children's records
Tamper-evident audit exists for Migration Cloud. Extend to student records, and cover **reads**,
not only writes.

---

# What is already world-class — do not rebuild

Recorded so no wave wastes effort re-doing solved work:

- **Object-level authorization** — a teacher provably cannot read another class's children.
- **Per-tenant timezone and DST handling.**
- **The SODP offline rail** — real idempotency, conflict flagging, loud failure on unhandled cases.
- **The 15-scale grading engine.**
- **The event bus** — 14 real events, HMAC-signed, DLQ + replay.
- **Install governance and the kill-switch.**
- **Interop** — LTI 1.3, OneRoster, SCIM, SAML, Ed-Fi.
- **WhatsApp delivery.**
- **Immutable transcripts.**
- **DRF pagination discipline.**
- **PPP regional pricing** — `CountryMultiplier`, World-Bank bands, seeded and wired.
- **The cross-tenancy FK deploy blocker** — remediated 2026-07-20, gate now zero-tolerance.

# Corrections to prior findings

- Timetable `--dry-run` **does not** persist. It was fixed (`transaction.atomic()` +
  `set_rollback(True)`) and regression-tested. An earlier recorded finding said otherwise; it
  was stale and is retracted.
- Of 16 cross-tenancy FK findings, only 4 were real; 12 already carried `db_constraint=False`,
  which is the remediation rather than a workaround.

# Program status

| Tier | Scope | Status |
|---|---|---|
| 0 | Active exposure (5 items) | in progress |
| 1 | Structural honesty (2 items) | not started |
| 2 | Country-neutral academic spine (7 items) | not started |
| 3 | Offline made real (5 items) | not started |
| 4 | Developer platform (4 items) | not started |
| 5 | Scale and residency (4 items) | not started |
| 6 | Compliance (5 items) | not started |
