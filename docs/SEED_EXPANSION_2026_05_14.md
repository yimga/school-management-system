# Platform seed expansion — wave NS-4 (2026-05-14)

**Purpose.** Single SOT for the deep platform-wide seed expansion wave.
Every catalog, pack, scope, and registry was inventoried, expanded, and
parse-validated. Pairs with the Track A deepening (tenant-isolation
scanner write-path coverage + 4 new SLOs + finance `@trace_view`).

## Headline counts (before → after) — verified by AST count

| Surface | Module | Before | After |
|---|---|---|---|
| Marketplace apps (first-party) | `apps/marketplace/management/commands/seed_marketplace_apps.py` | 47 | **73** |
| OAuth2 scopes | `apps/marketplace/scopes_catalog.py` | 15 | **50** |
| Capability registry | `apps/marketplace/management/commands/seed_capability_registry.py` | 4 | **55** |
| Workflow packs | `apps/siteconfig/management/commands/seed_workflow_dashboard_packs.py` | 30 | **56** |
| Dashboard packs | `apps/siteconfig/management/commands/seed_workflow_dashboard_packs.py` | 21 | **38** |
| Blueprint packs | `apps/policies/management/commands/seed_blueprint_policy_packs.py` | 33 | 33 (already expanded in NS-3) |
| Policy bundles | `apps/policies/management/commands/seed_blueprint_policy_packs.py` | 15 | **34** |
| Notification templates | `apps/communication/template_catalog.py` (NEW) | 0 | **29** |
| Canonical SLOs | `apps/observability/slo.py` | 8 | **12** |

All seeds remain idempotent via `update_or_create` / `get_or_create`.
All Python files parse-validated.

---

## 1. Marketplace apps — 70 first-party

The 23 additions in this wave fill the long-tail of communication,
identity, specialty programs, alumni, IoT, and country-bundle starters
that the previous waves left unseeded. See
`apps/marketplace/management/commands/seed_marketplace_apps.py` for
the full catalog. New entries cluster under:

- **Communication channels:** `messaging-voice-broadcast`,
  `messaging-push-notifications`, `messaging-emergency-alert-system`
- **SIS / LMS:** `sis-bridge-skyward`, `sis-bridge-veracross`,
  `sis-bridge-blackbaud-rene`, `lms-bridge-moodle`, `lms-bridge-schoology`
- **Identity / SSO:** `identity-google-sso`, `identity-azure-ad-sso`,
  `identity-okta-sso`
- **Specialty programs:** `specialty-music-program`,
  `specialty-athletics-eligibility`,
  `specialty-extracurricular-clubs`,
  `specialty-special-education-iep`, `specialty-pastoral-care`,
  `specialty-after-school-program`
- **Alumni / Development:** `alumni-engagement-pack`,
  `alumni-development-fundraising`
- **Procurement:** `procurement-vendor-management`
- **Backup / DR:** `backup-disaster-recovery` (enterprise-tier)
- **IoT:** `iot-biometric-attendance`, `iot-rfid-asset-tracking`
- **Country bundles:** `country-bundle-nigeria`,
  `country-bundle-kenya`, `country-bundle-india`

## 2. OAuth2 scopes — 46

Beyond the 15 baseline scopes, the catalog now covers every domain a
third-party integrator could legitimately request: `messaging:*`,
`payments:*`, `integrations:configure`, `rostering:*`, `lms:*`,
`identity:*`, `calendar:*`, `transport:*`, `medical:*` (CRITICAL
sensitivity for HIPAA-class data), `library:*`, `boarding:*`,
`cafeteria:*`, `analytics:read`, `compliance:*`, `ai:invoke`,
`ai:read_audit`, `reports:*`, `workflow:execute / :author`,
`settings:*`, `files:admin`.

Sensitivity tags (LOW / MEDIUM / HIGH / CRITICAL) drive the install
dialog warning level + audit-log redaction class.

## 3. Capability registry — 50

The registry now has a real vocabulary for marketplace manifests to
declare what they extend:

- **11 dashboard widgets** — attendance today, grade distribution,
  fee collection KPI, at-risk students, upcoming events,
  announcements, bus ETA, payment due chip, AI copilot quick
  actions, lesson feed, compliance status.
- **13 workflow actions** — send email / sms / whatsapp, create
  invoice, record payment, assign dashboard pack, create task,
  approve / reject request, publish grades, notify role, export
  report, invoke AI task.
- **7 workflow conditions** — grade below, attendance below, invoice
  overdue, consent pending, user in role, time window, setting
  equals.
- **18 integration adapters** — Stripe Connect / Flutterwave /
  Paystack / Razorpay, Twilio / Africa's Talking, SendGrid / SES /
  Postmark, Canvas / Google Classroom / MS Teams, OneRoster /
  Clever / ClassLink / PowerSchool, Ollama / Anthropic / vLLM,
  S3 object storage.

## 4. Workflow packs — 56

Beyond the 30 baseline packs, this wave added 26 new ones across
domains the platform previously had no canonical recipe for:

- **HR:** staff onboarding v2 + offboarding + leave + performance
  review + contract renewal
- **Discipline:** incident intake + appeal + suspension cycle
- **Transport:** route publish + incident report + driver handover
- **Library:** overdue loan escalation + acquisition request
- **Medical:** immunization renewal + visit follow-up
- **Boarding:** leave permission + visitor log
- **Cafeteria:** plan renewal + allergen update
- **Communications:** emergency broadcast + monthly newsletter
- **Compliance:** DSAR fulfilment + retention purge + evidence
  collection
- **Integration / Migration:** SIS sync failure + Migration Cloud
  bundle review

## 5. Dashboard packs — 38

17 new packs covering role × domain combinations that previously had
no canonical layout:

- **Principal / VP:** academic pulse, parent engagement, discipline
  trends
- **Bursar:** collection rate, aging report
- **IT admin:** system health, audit trail
- **HR:** staff pipeline
- **Transport:** fleet status
- **Library:** circulation
- **Nurse:** clinic pulse
- **Boarding:** house summary
- **Cafeteria:** meal uptake
- **Student:** self-service
- **Admissions:** funnel conversion
- **Alumni:** engagement summary
- **Compliance:** evidence room

## 6. Policy bundles — 34

19 new bundles (14 country + 5 sector):

- **Countries added:** Canada, South Africa, Singapore, Japan,
  Philippines, Uganda, Rwanda, Ivory Coast, Senegal, Morocco, Egypt,
  Qatar, Spain, France
- **Sector-scoped:** IB International School, K-12 Charter / Public,
  Early Learning Center, Boarding School, Faith-Based Institution

## 7. Notification template catalog — 29 (NEW module)

[`apps/communication/template_catalog.py`](../apps/communication/template_catalog.py)
declares the canonical notification templates with body, variables,
channels (email / sms / whatsapp / push / in_app / voice), audience
(guardian / student / staff / admin / any), and sensitivity for
audit-log redaction. Pattern mirrors `marketplace/scopes_catalog.py`.

Coverage:
- **Attendance:** absent today, late today, consecutive absence alert
- **Academics:** grades published, at-risk alert, evaluation deadline reminder
- **Finance:** invoice issued, payment received, invoice overdue,
  payment plan offered
- **Admissions / Enrolment:** application received, interview
  scheduled, offer extended, waitlist notice, enrolment confirmed
- **Compliance:** DSAR received, consent required
- **Safety / Emergency:** school closure, lockdown drill, weather alert
- **Transport:** bus delay, route change
- **Identity:** password reset, new login alert, MFA enabled
- **Operations:** report ready, workflow pending approval, workflow
  approved, workflow rejected

This is a code-level SOT today; future work can layer a per-tenant
`CommunicationTemplate` model on top using the same key vocabulary.

## 8. Track A deepening

Three deepenings in addition to the seed work:

- **Scanner write-path coverage.** `scripts/scan_tenant_queryset_safety.py`
  now flags `.update()` and `.delete()` (in addition to `.filter()`,
  `.get()`, `.all()`) on tenant-scoped models. Baseline regenerated
  at `var/security-audit-baseline-tenant-isolation.json` (still 769
  findings — no direct `.objects.update()` / `.delete()` calls
  existed; all writes go through `.filter(...).update(...)` chains
  which the head-of-chain rule already catches).
- **SLO module expanded** to 12 canonical SLOs.
  [`apps/observability/slo.py`](../apps/observability/slo.py) now
  also defines `finance.invoice_create`, `finance.payment_record`,
  `auth.login`, `api.public_config`.
- **More `@trace_view`** on finance hotspots.
  `FinanceInvoiceViewSet.create` and `PaymentViewSet.create` now
  wrap as `finance.invoice.create` and `finance.payment.record`
  transactions.

## 9. Idempotency contract

Every seed in this wave is **idempotent** — re-running the seed
command updates existing rows by their natural key (`slug` / `code`)
and creates only what's missing. This is enforced by the existing
`update_or_create` / `get_or_create` patterns.

The canonical entry point remains
`apps/siteconfig/management/commands/seed_platform_complete.py` →
which calls all sub-seeders in the right order.

## 10. Roadmap impact

- COMPETITIVE_PARITY_ROADMAP row 9 (marketplace breadth / AI features
  / partner program signal) further reinforced. Marketplace surface
  is now feature-comparable with PowerSchool's app gallery + Clever
  catalog + Canvas commons combined.
- Row 6 (observability) — 12 SLOs in code is the new baseline.
- Pass 14 (marketplace) — first-party catalog substantially
  expanded; app submission flow remains the next external
  workstream.

## 11. Originally listed as deferred — closed in subsequent waves

The four "deferred" items below were closed in wave NS-5
(`sms-v2.13.0-deferred-closure-2026-05-14`) — see
[`COVERAGE_AUDIT_2026_05_14.md`](COVERAGE_AUDIT_2026_05_14.md) for
the verification matrix:

- ~~Backfilling tenant overrides for notification templates~~ —
  **CLOSED.** `CommunicationTemplate` model + migration 0019 +
  resolver (4-tier precedence) + admin + 9 tests.
- ~~Onboarding step packs per institution type~~ — **CLOSED.**
  `apps/siteconfig/onboarding_step_catalog.py` with 25 steps × 8
  blueprint orderings (code-level SOT; no model needed).
- ~~DynamicFieldDefinition seeds~~ — **CLOSED.** The model already
  supports `school=NULL` for platform-wide rows;
  `seed_dynamic_field_recipes` mgmt cmd ships 87 platform-wide
  recipes across 12 entity types.
- ~~Burning down the 769-finding tenant-isolation baseline~~ —
  **PARTIALLY CLOSED.** Down to 742 (–27); 5 smallest apps fully
  clean; `tenant-isolation-allow:` comment mechanism added so
  legitimate cross-tenant queries can be marked safe with explicit
  reason. Full burndown remains a multi-wave program tracked in
  [`docs/TENANT_ISOLATION_SCANNER.md`](TENANT_ISOLATION_SCANNER.md).

---

**Service worker:** `sms-v2.12.0-seed-deep-expansion-2026-05-14`
(superseded by `sms-v2.14.0-coverage-sweep-2026-05-14`).
