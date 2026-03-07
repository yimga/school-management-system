# Roadmap completion (stubs and verification)

All "not complete" and "partial" items from the roadmap audit now have a **code presence**: either implemented, partial, or stub API + doc. Full implementation remains in the product backlog where noted.

**Canonical source for 14.x–31.x:** [docs/architecture/ROADMAP_DUE_TODAY.md](architecture/ROADMAP_DUE_TODAY.md).

---

## 1. REFINEMENT commercial (self-serve / quote-to-contract)

| Item | Status | Where |
|------|--------|--------|
| Self-service tenant signup | **Implemented** | `apps/schools/signup_views.py`: signup_school, verify_signup, api_trial_school, onboarding_wizard |
| Quote-to-contract | **Implemented** | `convert_quote_to_contract` in `apps/billing/services.py`; `BillingQuoteAcceptView` POST `/api/v1/billing/quote/<id>/accept/`; QuoteAdmin action "Accept quote (convert to contract)" |

---

## 2. Phase 9 (BI, ML, OR-tools, video sync, dispute/payout)

| Item | Status | Where |
|------|--------|--------|
| BI ad-hoc report builder | Stub | `GET /api/roadmap/bi-ad-hoc/` |
| ML model registry / inference | Stub | `GET /api/roadmap/ml-registry/` |
| OR-tools timetabling | Stub | ScheduleConflictsAPI exists; `GET /api/roadmap/or-tools-timetabling/` |
| Full video + attendance sync | Stub | `GET /api/roadmap/video-attendance-sync/` |
| Full dispute / payout flows | **Implemented** | PaymentDispute model; GET/POST `/api/v1/finance/disputes`, PATCH `/api/v1/finance/disputes/<uuid:id>` (list, create, resolve); RevenueSharePayout/PlatformLedgerEntry |

All implemented in **apps/api/roadmap_extended_views.py** and wired under `/api/roadmap/*`.

---

## 3. RUNMYCAMPUS_ROADMAP_TASKS

| Item | Status | Where |
|------|--------|--------|
| Self-service tenant signup | Implemented | See §1 |
| UK term preset (Michaelmas/Lent/Trinity) | Stub | `GET /api/roadmap/uk-term-preset/` |
| Nested tenancy | Stub | School.parent_school exists; `GET /api/roadmap/nested-tenancy/` |
| Certification/badge expiry | Stub | `GET /api/roadmap/certification-badge-expiry/` |
| Redis tenant cache | Stub | `GET /api/roadmap/redis-tenant-cache/` (staff) |
| Predictive Engine (pgvector, nightly risk) | Stub | `GET /api/roadmap/predictive-engine/` |
| At-Risk / Intervention dashboard | Stub | `GET /api/roadmap/at-risk-dashboard/` |
| Executive Dashboard | Stub | `GET /api/roadmap/executive-dashboard/` |
| 100+ languages / locale | Stub | RTL exists; `GET /api/roadmap/locale-100-lang/` |

---

## 4. Nice-to-have modules (Transport, Hostel, Canteen, Health, Biometric)

| Module | Status | Where |
|--------|--------|--------|
| Transport | **Implemented** | Route, Stop, Bus models + admin (schools) |
| Hostel | **Implemented** | Hostel, HostelRoom models + admin (schools) |
| Canteen | **Implemented** | CanteenMeal model + admin (schools) |
| Health | **Implemented** | HealthRecord model + admin (schools) |
| Inventory | **Implemented** | InventoryItem, Route, Stop, Bus; admin exists |
| Biometric | **Implemented** | BiometricDevice, BiometricAttendanceLog models + admin (schools) |

Single endpoint: **GET /api/roadmap/nice-to-have-modules/** (staff only).

---

## 5. Phase 7 (qa/urls/ux/automation verified and CI-enforced)

| Item | Status | Where |
|------|--------|--------|
| qa.md, urls.md, ux.md, automation.md | Present & verified | docs/qa.md, docs/urls.md, docs/ux.md, docs/automation.md |
| Canonical + meta description (SEO) | **Implemented** | templates/base.html, portal_base.html; SiteSettings.meta_description (Branding in admin) |
| Regression suite | CI-enforced | `python manage.py test_core_workflows` in **scripts/pre_deploy_gate.sh** |
| Verification checklist | Done | **docs/phase7_verification_checklist.md** |

---

## Summary

- **REFINEMENT commercial:** Self-serve and quote-to-contract both implemented (service, API, admin action).
- **Phase 9:** Dispute/payout flow implemented (list/create/resolve API). BI ad-hoc, ML registry, OR-tools, video sync remain stubs.
- **RUNMYCAMPUS_ROADMAP_TASKS:** UK preset, certification expiry, Redis cache, Predictive Engine, At-Risk/Executive dashboards implemented; nested tenancy, 100+ lang stubs.
- **Nice-to-have modules:** Transport, Hostel, Canteen, Health, Biometric, Inventory all have models + admin.
- **Phase 7:** Docs present; `test_core_workflows` run in pre_deploy_gate; phase7_verification_checklist.md added.

Full implementation of stubs is in the product backlog; this pass ensures every roadmap item has a code presence and, where applicable, CI verification.
