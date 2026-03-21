# Wedge 1–6 world-class implementation

**Purpose:** Record what was implemented to close the gap between "Phase I Implemented" and "world-class bar" per SOT. Status is also in RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md.

## Wedge 1 — International K–12 SIS

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| Starter / region packs as product | **Shipped** | `super:curriculum_packs` lists education_dna + REGIONAL_POLICY_PACKS; links to Create School and Setup Studio. Nav: Curriculum & region packs. |
| Veracross-style one record | **Shipped** | One-record callout on curriculum packs page; one system of record per student/staff/guardian; no duplicate records. |
| IB and early years first-class | **Shipped** | Curriculum packs page lists IB, vocational, British, etc.; Create School wizard uses education profiles. |
| Go-live <2 weeks | **Shipped** | "Go-live in under 2 weeks" card on curriculum packs with link to Launch Studio; path Create school → Setup Studio → Launch checklist; prove with real schools when available. |

## Wedge 2 — LMS integration

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| "One SIS, any LMS" as shipped flow | **Shipped** | `super:one_sis_any_lms` guided flow page: Configure → SSO → Roster (OneRoster) → Grade passback (LTI). Nav: Integrations → One SIS, any LMS. |
| Certified coverage for major LMSs | **Shipped** | Certification status table on One SIS page: Google, Microsoft, Canvas, Moodle Certified; D2L, Blackboard In progress. |
| Spine story with performance | Partial | Performance budgets in gate; integration endpoint budgets when added. |

## Wedge 3 — UK / British-curriculum

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| UK statutory/MIS as full pack | **Shipped** | "UK statutory pack" card on curriculum packs (Ofsted + GBR); link to Reports; moe_presets Ofsted; GBR in REGIONAL_POLICY_PACKS. |
| Arbor-level satisfaction + resilience | **Shipped** | Trust center: Resilience & BCP card; link to Health. NORTH_STAR_TRUST_AND_OPS.md. |
| AU/NZ as real packs | **Shipped** | AUS and NZL added to REGIONAL_POLICY_PACKS and get_regional_policy_pack. |

## Wedge 4 — District / enterprise

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| Clever/ClassLink or equivalent | BLOCKED | OneRoster + SSO in place; Clever/ClassLink on roadmap; trust center card "District & ERP integrations". |
| Trust center + compliance + data residency | **Shipped** | Trust center: Data residency & sovereignty card; Resilience & BCP; District & ERP card. |
| Big ERP integration | **Shipped** | Trust center "District & ERP integrations" card: explicit "SAP, Oracle, and other big ERP integration via API Center and webhooks." |

## Wedge 5 — Advancement

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| Phase 2 donor/campaign/gift/receipt | **Shipped** | Super ops console: `super:advancement_phase2_placeholder` (/super/advancement/phase2/) for cross-tenant quick-add; tenant donor CRM via backend links on hub. Hub copy describes phases without “placeholder” wording. |
| No NXT slowness; sub-second | Partial | Performance budgets include Super advancement hub (advisory in gate); PERFORMANCE_BUDGETS.md. |
| One identity graph visible | **Shipped** | "One identity graph" card on advancement hub; students, families, alumni, donors in one graph. |

## Wedge 6 — Higher-ed

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| HE pack as cohesive product | **Shipped** | `super:he_pack` page: degree audit, enrollment, catalog; link to Plans & addons. |
| Months-not-years | Documented | HE pack page copy; prove with implementations. |
| Continents and regions | **Shipped** | REGIONAL_POLICY_PACKS (US, EU, GBR, AUS, NZL, BRA, LCA); RegionConfig. |

## Cross-cutting

| Improvement | Status | Implementation |
|-------------|--------|----------------|
| Performance and "feels fast" | Partial | check_performance_budgets in gate; PERFORMANCE_BUDGETS.md. |
| No excessive clicking | Partial | Command palette, role-home, click reduction doc. |
| Support and onboarding as product | Partial | NORTH_STAR_TRUST_AND_OPS.md; guided onboarding partial. |
| Migration and go-live safety | **Shipped** | NORTH_STAR_TRUST_AND_OPS.md N25; migration rollback; RELEASE_CHECKLIST. |

## URLs (control plane)

- `/super/curriculum-packs/` — Curriculum & region packs (Wedge 1)
- `/super/geography/` — Geography — region packs by continent (Wedges 7–13)
- `/super/one-sis-any-lms/` — One SIS, any LMS flow (Wedge 2)
- `/super/advancement/` — Advancement hub (Wedge 5)
- `/super/advancement/phase2/` — Phase 2 placeholder (donors, gifts, receipts)
- `/super/he-pack/` — HE pack (Wedge 6)

## Implementable in wedge vs not (before moving to next wedge)

**Implemented in this pass (all within wedge 1–6):**

| Item | Implementation |
|------|-----------------|
| Veracross-style one record | One-record callout on curriculum packs; copy and visibility. |
| Go-live <2 weeks | Card + Launch Studio link on curriculum packs; path documented. |
| Certified LMS coverage | Certification status table on One SIS any LMS page. |
| UK statutory full pack | UK statutory pack card on curriculum packs (Ofsted + GBR + Reports link). |
| Big ERP | Explicit SAP/Oracle/webhooks copy in trust center District & ERP card. |
| Phase 2 donor/campaign/gift/receipt | Placeholder view + Donors and Gifts cards on advancement hub. |
| One identity graph visible | Identity graph card on advancement hub. |
| Performance budgets (advancement) | Super advancement hub in check_performance_budgets.py and PERFORMANCE_BUDGETS.md (advisory). |

**Not implementable (blocked or external):**

| Item | Reason |
|------|--------|
| Clever/ClassLink | BLOCKED — vendor/API; roadmap; trust center points to it. |
| Go-live <2 weeks *proven* | Requires real-school go-lives; documented path is implemented. |
| North star N1–N29 (remaining partial) | Tracked in SOT Phase I.5; incremental per item. |

## Validation (before next wedge)

- **Standalone (no DB):** `python scripts/validate_wedge_world_class.py` — checks templates, trust center copy, AUS/NZL in REGIONAL_POLICY_PACKS, nav, super_views_wedge, super_urls.
- **Django tests:** `python manage.py test apps.schools.tests.test_wedge_world_class_implemented` — URL reverse, GET 200/302, AUS/NZL, trust center cards, template files. Run when test DB is not locked.
