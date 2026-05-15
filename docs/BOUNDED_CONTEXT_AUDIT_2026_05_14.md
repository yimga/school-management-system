# Bounded-Context Audit — 2026-05-14

Re-verification pass on the bounded-context ownership chart. Triggered by the broader
2026-05-14 state-of-platform sweep. Result: **healthy. No relocation work required.**

## Method

1. Read `docs/bounded_context_ownership.md` (current SOT).
2. Ran `scripts/lint_bounded_context_imports.py --strict` — **exit 0**. Tenant-facing
   apps (`portal`, `student360`, `academics`, `people`, `finance`, `evals`, `reports`,
   `communication`, `dashboard`, `payroll`, `requests`, `api`, `observability`,
   `analytics`) do not import from forbidden control-plane modules
   (`apps.customers.models`, `apps.marketplace.models`, `apps.policies.models`).
3. Sampled all `^class Student*` definitions across `apps/` outside `apps/people/`.
4. Sampled per-app `models.py` density.
5. Sampled potentially-overlapping apps: `apps/customers/`, `apps/student360/`,
   `apps/accounts/`, `apps/people/`.

## Findings

### 1. Linter is wired and passing

`scripts/lint_bounded_context_imports.py` enforces the chart with regex blocks on
forbidden cross-context imports. It runs in `scripts/pre_deploy_gate.sh` and in CI
(`backlog_unlock_nightly.yml`). Strict mode exit 0 on 2026-05-14.

### 2. Model placement is correct

The 50-app tree could *look* like sprawl, but every `^class Student*` outside
`apps/people/` is a domain-specific record, not a duplicate profile:

| Class | App | Role |
|---|---|---|
| `StudentDegreeEnrollment` | academics | Academic enrollment row |
| `StudentSignals`, `StudentAtRiskSignal` | analytics | Analytics-owned signal records |
| `StudentIDFormat` | compliance | Compliance-owned ID-format policy |
| `StudentCompetencyAssessment` | evals | Evaluation-owned assessment row |
| `StudentSyncConsumer` | api | Websocket consumer (not a model) |
| `Student*View`, `Student*Serializer`, `Student*Pagination` | api | API surface (not a model) |

The canonical `StudentProfile` lives in `apps/people/models.py` (per the
ownership chart). Every cross-app import is `from apps.people.models import StudentProfile`
— in the expected direction.

### 3. Model density per file

| File | Class count | Verdict |
|---|---|---|
| `apps/finance/models.py` | 55 | Healthy — finance has Invoice, Payment, Fee, Tax, Subscription, RegionPaymentProfile, processors, scholarship, aid, etc. Normal for a finance bounded context. |
| `apps/platform_runtime/models.py` | 33 | Healthy — runtime+metadata catalog. |
| `apps/academics/models.py` | 29 | Healthy. |
| `apps/people/models.py` | 22 | Healthy. |
| `apps/siteconfig/models_platform_catalog.py` | 20 | Already split out of main `models.py` — good hygiene. |
| `apps/schoolops/models.py` | 17 | Healthy. |
| `apps/marketplace/models.py` | 15 | Healthy. |
| `apps/communication/models.py` | 15 | Healthy. |

No file is pathologically large.

### 4. App naming nit (cosmetic, not load-bearing)

`apps/customers/` holds the `django-tenants` `Client` model (the tenant record). Name
is misleading — the file's docstring confirms it: *"Phase I: Tenant (Client) and Domain
models for django-tenants schema-per-tenant."* A future rename to `apps/clients/` or
`apps/tenant_clients/` would be cleaner, but it's a substantial migration:

- Update `INSTALLED_APPS` entry.
- Rename app config + app label across migrations.
- Update every import path (the bounded-context linter's
  `FORBIDDEN_PATTERNS` regex hardcodes `apps.customers.models` — would need updating).
- Update `bounded_context_ownership.md` chart.

**Recommendation:** leave as-is unless there's a separate naming-cleanup wave.
The cost/benefit isn't there given the current shape.

### 5. `apps/student360/` is correctly thin

One model (`ImmutableTranscript`) — an explicit read-only archive snapshot of a
student transcript, frozen per year. It is a separate context because of its
immutability + retention semantics (FERPA-driven). Correctly placed.

### 6. `apps/accounts/` vs `apps/people/`

Clean separation in the chart:
- `accounts` = Identity & Access (User, Permission, AccessRole, MFA, Delegation, …).
- `people` = People & Relationships (StudentProfile, TeacherProfile, GuardianProfile, identity resolution).

A `User` belongs to identity; a `StudentProfile` belongs to people; the FK runs from
profile → user. No collision.

## Verdict

The bounded-context layer is healthy. No model relocation needed. The earlier
state-of-platform note flagged "people/customers/accounts/student360" as a suspect
cluster — confirmed not actually suspect. Concern dismissed.

Continue running the linter in CI; bump the chart when a new bounded context lands.

## Action items (none blocking)

- Optional, future: rename `apps/customers/` → `apps/clients/` for clarity.
- Optional, future: add `AppReview` + `AppSubscription` models to `apps/marketplace/`
  if the partner program ever offers paid app subscriptions (currently the lifecycle
  is `MarketplaceApp.status` enum + installation count, which is sufficient).
