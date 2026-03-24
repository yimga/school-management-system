# RunMyCampus — 45-wedge execution scorecard (Phase 2 tracker)

**Authority:** Extends [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.2.1 — **does not replace** §0.2.1.2 (codebase validation) or §0.2.1.3 (innovation gaps). This file is the **per-wedge GTM / pack / workflow / depth matrix** from the Cursor wedge plan Phase 2.

**Core law (same as SOT):** One platform core — identity graph, runtime, metadata, localization, workflows, packages, marketplace, Studio OS — **no forked products per wedge.**

**Status legend**

| Value | Meaning |
|-------|---------|
| **DONE** | Breadth shipped + no material open gap in §0.2.1.3 for this row (rare). |
| **PARTIAL** | **Implemented in codebase** per §0.2.1.2; deepening (packs, UX, statutory proof, super-premium §0.2.1.5) **ongoing**. This is the normal state for most wedges. |
| **NOT DONE** | Missing from product/code for this wedge’s **named scope** (should be empty for IDs 1–45; use for explicit sub-capabilities in gap columns). |
| **BLOCKED** | External dependency (e.g. Clever/ClassLink **native** APIs — partnership). |

**Column abbreviations:** Surfaces = product/UI coverage · Packs = region/curriculum/starter gaps · WF = workflows · Dash = dashboards · Rpt = reports/docs · L10n = localization · Integ = integrations · Id = identity-graph extensions · GTM = go-to-market · vs = competitor / parity lens · Next = immediate engineering/GTM action.

**Verification:** `python scripts/verify_45_wedge_scorecard.py` (expects **45** numbered wedge rows below).

**Related automation:** `scripts/validate_wedges_phase.py --phase all` (wedges **1–45** in five phases: 1–10, 11–20, 21–30, 31–40, 41–45; extends `validate_wedge_super_premium_phases.py` with line-by-line catalog checks); `scripts/validate_wedges_14_22.py` (full DB registry audit when default DB is available); `scripts/validate_wedge_super_premium_phases.py`; `bash scripts/run_wedge_super_premium_gates.sh` — see SOT §0.2.1.5–§0.2.1.6.

---

## Tier A — Platform beachheads (wedges 1–6)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 1 | International K–12 SIS | A | PARTIAL | Wizard, SIS, portal, reports, region DNA, IB/early years; **beachhead checklist** on `super:curriculum_packs`; marketplace `international-k12-core-starter` | Measured go-live packs; migration-as-pack | Onboarding blueprint depth | Operator NBA dashboards | Report bundle polish | Per-locale report shells | One SIS ↔ any LMS story | Guardian/student single record UX | Fastest international setup | PowerSchool, iSAMS, Toddle | Deepen starter + IB/GCSE/US packs; benchmark N≥5 ([GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md](GOLIVE_UNDER_TWO_WEEKS_BENCHMARK.md)) |
| 2 | LMS integration | A | PARTIAL | SSO, LTI, OneRoster, district hub; **beachhead checklist** on `super:one_sis_any_lms` | Per-LMS certified packs | Grade passback workflows | Connector health dashboards | SLA docs | — | Canvas/Classroom/Teams depth | Roster truth in identity graph | RunMyCampus + [LMS] pages | Canvas, Google, MS | SLAs + observability ([LMS_ROSTER_GRADEPASSBACK_SLA.md](LMS_ROSTER_GRADEPASSBACK_SLA.md)); integration workbench |
| 3 | UK / British-curriculum | A | PARTIAL | GBR pack, DNA, statutory presets | Full MIS statutory depth | UK workflow bundle | Trust/school-group dashboards | Report pack completeness | UK terminology hardening | — | — | UK + British intl | Arbor, SIMS, iSAMS | Resilience/BCP visible; trust templates |
| 4 | District / enterprise | A | PARTIAL | Control plane, OneRoster, compliance, trust center, `super:district_enterprise` (+ rollups + **beachhead checklist**), government aggregates API `schema_version` 1.1 | District SKUs | District onboarding WF | Multi-school dashboards | Trust/compliance exports | Region residency UX | ERP coexistence pattern | District roles | Enterprise RFP story | Infinite Campus, PowerSchool | ERP-finance productization; native Clever **BLOCKED** (SOT) |
| 5 | Advancement | A | PARTIAL | Alumni, campaigns, gifts, aid; **beachhead checklist** on `super:advancement_hub` | Advancement dashboard pack | Donor journey WF | Advancement KPI dash | Receipts/ack reports | — | Payment/CRM bridges | Constituent graph | Donor retention | Blackbaud, Raiser’s Edge | Phase 2 gift/campaign depth (SOT §0.2.1.3) |
| 6 | Higher-ed | A | PARTIAL | Degree audit, enrollment, plan addons; **beachhead checklist** + catalog/learning links on `super:he_pack` | HE cohesive starter | HE registrar WF | HE operational dash | Transcript/credit reports | Semester global packs | SIS/LMS HE | Student-program graph | Months-not-years HE | Ellucian, Unit4 | Staged messaging; pack-driven only ([HE_MONTHS_NOT_YEARS_GOLIVE.md](HE_MONTHS_NOT_YEARS_GOLIVE.md)) |

---

## Tier B — Geography overlays (wedges 7–13)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 7 | Africa (region packs) | B | PARTIAL | `REGIONAL_POLICY_PACKS` LCA/WAEC/AFR_FR; super:geography | Per-country statutory | Ministry WF | Regional health | WAEC/LCA report depth | FR/EN depth | Mobile money / local (where productized) | — | Africa-first GTM | Local SIS | Per-market packs ([WEDGES_7_13_GEOGRAPHY_PLAN.md](WEDGES_7_13_GEOGRAPHY_PLAN.md)) |
| 8 | Asia | B | PARTIAL | ASIA aliases; geography hub | National variants | Attendance/compliance | Regional dash | Local transcripts | CJK/RTL where required | — | — | Pan-Asia | Regional MIS | Expand packs per entry market |
| 9 | Europe (beyond UK) | B | PARTIAL | EU packs; GDPR posture | National frameworks | GDPR workflows | Privacy dash | EU report shells | Multi-language | — | — | EU expansion | Local MIS | EU statutory depth per country |
| 10 | North America | B | PARTIAL | US/CAN packs | State/province variants | District compliance WF | State reporting dash | SIS exports | EN/ES | SIS/LMS interop | — | US/CA GTM | IC, PS | State reporting depth |
| 11 | South America | B | PARTIAL | BRA/LATAM_ES | National packs | Local compliance | Regional dash | Local reports | ES/PT | — | — | LATAM | Local vendors | LATAM pack depth |
| 12 | Oceania | B | PARTIAL | AUS/NZL | Statutory attendance/fees | Compliance WF | School group dash | Gov reporting | EN | — | — | AU/NZ | Synergetic | AU/NZ real packs (SOT Phase I narrative) |
| 13 | MENA | B | PARTIAL | MENA pack | Gulf variants | Ministry stubs → real | Regional dash | Ministry PDFs | AR/EN | — | — | MENA entry | Regional SIS | Replace stubs with jurisdiction proofs |

---

## Tier C — Education systems (wedges 14–22)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 14 | Public / state | C | PARTIAL | `PUBLIC` sector; wizard | State reporting packs | Compliance WF | District-style dash | State exports | — | SIS interop | — | State RFP | State SIS | Align packs to state reporting |
| 15 | Private / independent | C | PARTIAL | `PRIVATE`; RBAC | Independent school packs | Admissions WF | Advancement-linked | Parent reports | — | — | Household model | Private schools | WC, Veracross | Tuition + advancement bundle |
| 16 | Charter | C | PARTIAL | `CHARTER` | Authorizer packs | Lottery/enrollment WF | Compliance dash | Authorizer reports | — | — | — | Charter networks | Charters | Authorizer workflow depth |
| 17 | International | C | PARTIAL | `INTERNATIONAL` | IB/world-school packs | Cross-border WF | Multi-campus | Intl transcripts | Multi-language | — | Multi-school affiliation | Intl schools | Tier 1 intl | Same as wedge 1 depth |
| 18 | Faith-based | C | PARTIAL | `FAITH_BASED` | Denomination packs | Pastoral WF | Community dash | Custom reports | — | — | — | Faith segment | — | Optional terminology/privacy packs |
| 19 | Home-school / hybrid | C | PARTIAL | `HOME_SCHOOL` | Hybrid attendance packs | Guardian-heavy WF | Home dash | Portfolio reports | — | — | Guardian graph | Home cooperatives | — | Hybrid engagement metrics |
| 20 | Government / ministry | C | PARTIAL | `GOVERNMENT_MINISTRY`; ministry links | Ministry report packs | Audit WF | Ministry dash | Ministry PDFs | — | Federation | — | Govt bids | Ministry SIS | Real ministry PDFs per jurisdiction |
| 21 | NGO | C | PARTIAL | `NGO` | Grant/compliance packs | Grant WF | Program dash | Donor reports | — | — | — | NGO vertical | — | Grant + beneficiary identity |
| 22 | Multi-campus / group | C | PARTIAL | `MULTI_CAMPUS` | Group governance packs | Rollout WF | Group KPI dash | Consolidated reports | — | — | Group roles | School groups | MAT/MIS | Trust templates + rollups |

---

## Tier D — Learning / delivery (wedges 23–30)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 23 | In-person | D | PARTIAL | Default SIS; attendance | Room/schedule packs | Attendance WF | Ops dash | Day reports | — | — | — | Traditional | — | Keep parity with online/hybrid |
| 24 | Fully online | D | PARTIAL | `school.features`; catalog | Online engagement packs | Async WF | Engagement dash | Participation reports | — | LMS depth | — | Virtual schools | OLS | Mode-specific reporting (SOT gap) |
| 25 | Hybrid / blended | D | PARTIAL | Catalog + packs | Hybrid attendance | Blended WF | Hybrid dash | Mixed modality reports | — | LMS | — | Post-COVID norm | — | Single roster truth across modes |
| 26 | Competency-based | D | PARTIAL | Evals/metadata | CBE grading packs | Competency WF | Skills dash | Skills transcripts | — | — | — | Innovative schools | — | CBE report + workflow depth |
| 27 | Mastery-based | D | PARTIAL | Grading scales | Mastery packs | Remediation WF | Mastery progress | Progress reports | — | — | — | Alt schools | — | Align with evals engine |
| 28 | Project-based | D | PARTIAL | Projects (where present) | PBL packs | Project WF | Project dash | Portfolio | — | — | — | PBL networks | — | PBL assessment depth |
| 29 | Self-paced | D | PARTIAL | LMS + pacing | Pace packs | Progress WF | Pace dash | Pace reports | — | LMS | — | Async academies | — | LMS grade passback |
| 30 | Cohort-based | D | PARTIAL | Sections/rosters | Cohort packs | Cohort WF | Cohort dash | Cohort analytics | — | — | — | Cohort programs | — | Cohort attendance/grading |

*Evidence:* Learning APIs, pack install/rollback, playbooks [WEDGES_23_43_STUDIO_PLAYBOOKS.md](setup_studio/playbooks/WEDGES_23_43_STUDIO_PLAYBOOKS.md), tests `test_learning_institution_beyond` (SOT §0.2.1.2).

---

## Tier E — Education types (wedges 31–43)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 31 | General K–12 | E | PARTIAL | Core SIS | Default blueprint | Core WF | School dash | Report cards | — | — | Student graph | Core GTM | All incumbents | Baseline depth |
| 32 | TVET | E | PARTIAL | Catalog W32 | TVET workflow pack | Skills/competency WF | Placement dash | Certification reports | — | Employer interop | Apprentice linkage | Workforce | Workday | TVET-specific workflows (SOT gap) |
| 33 | Trade / apprenticeship | E | PARTIAL | W33 | Apprenticeship packs | Hours WF | Employer dash | Time reports | — | — | Employer entity | Trade schools | — | Hours + employer bridge |
| 34 | Specialized (arts, STEM, sports) | E | PARTIAL | W34 | Specialty packs | Audition/portfolio WF | Specialty dash | Specialty reports | — | — | — | Magnets | — | Metadata extensions |
| 35 | Early years / pre-K | E | PARTIAL | Early years in wedge 1 | EY packs | Guardian WF | EY dash | Development reports | — | — | Guardian | EY segment | — | EY assessment depth |
| 36 | Adult education | E | PARTIAL | W36 | Adult packs | Enrollment WF | Adult dash | CE transcripts | — | — | — | Adult ed | — | CE pacing + billing |
| 37 | Professional development | E | PARTIAL | W37 | PD packs | PD WF | PD dash | PD certificates | — | LMS PD | Staff graph | Corp training | — | PD + HR linkage |
| 38 | Language schools | E | PARTIAL | W38 | Language packs | Level WF | Proficiency dash | CEFR reports | Multi-language | — | — | Language vertical | — | Proficiency + scheduling |
| 39 | Exam prep / tutoring | E | PARTIAL | W39 | Tutoring packs | Session WF | Tutor dash | Session reports | — | — | — | Tutoring | — | Session billing |
| 40 | Special education | E | PARTIAL | W40 | IEP packs | IEP WF | SPED dash | IEP reports | — | — | Care team graph | SPED | — | IEP compliance depth |
| 41 | Gifted / advanced | E | PARTIAL | W41 | Acceleration packs | Placement WF | Gifted dash | Acceleration reports | — | — | — | Gifted | — | Program placement |
| 42 | Alternative provision | E | PARTIAL | W42 | Alt provision packs | Safeguarding WF | AP dash | AP reports | — | — | — | AP schools | — | Safeguarding workflows |
| 43 | Higher education (type) | E | PARTIAL | Shared with wedge 6 | HE type packs | HE type WF | HE dash | HE transcripts | — | — | HE identity | HE segment | Banner | Keep distinct from K–12 messaging |

---

## Tier F — Integration / identity glue (wedges 44–45)

| ID | Wedge | Tier | Status | Surfaces | Packs Δ | WF Δ | Dash Δ | Rpt Δ | L10n Δ | Integ Δ | Id Δ | GTM | vs | Next |
|----|--------|------|--------|----------|---------|------|--------|-------|--------|---------|------|-----|-----|------|
| 44 | Clever/ClassLink-style roster + SSO | F | Implemented (spine + native) | OneRoster v1p1; district hub; CSV; academicSessions; **tenant** native credential store + probe; **super** console | Signed webhook pack | Roster sync WF | Interop health | Export audit | — | **Native HTTP clients + tenant hub** (`clever_classlink_client.py`, `super:native_roster_connectors`, `accounts:district_interop_*_native_*`) | District roster IDs | District sales | Clever, ClassLink | Deeper sandbox fixtures; GTM certification narrative ([WORLD_CLASS_TRIPLE_WEDGE.md](interop/WORLD_CLASS_TRIPLE_WEDGE.md) §44) |
| 45 | Identity and access federation | F | PARTIAL | OIDC, SAML, LTI, login SSO list; tenant `GET /api/learning/identity-graph-summary/`; manager trust + district surfaces show platform rollups | Federation packs | Break-glass WF | Security dash | Audit exports | IdP locale | OIDC/SAML depth | Federation graph | Trust-first GTM | Okta, Entra | Roster↔person graph depth; WC §45 |

---

## Phase mapping (Cursor plan ↔ SOT)

| Cursor phase | SOT / repo anchor |
|--------------|-------------------|
| **Phase 1 — Product spine** | §8.0, §10.4, ZIP phases (design system gate: `scripts/verify_design_system_phase2.py`), Studio OS §4, control plane, runtime-first, BR queue §0.3.3 |
| **Phase 2 — Scorecard** | **This file** + §0.2.1.2 / §0.2.1.3 |
| **Phase 3 — Beachheads 1–6** | §0.2.1.3 deepening rows + Phase I + marketplace/starter stacks; no duplicate roadmap files |

---

## Acceptance criteria (Phase 2 scorecard “complete”)

1. All **45** wedge IDs appear exactly once in the tier tables above.
2. Each row has **Tier A–F**, **Status**, and **Next** aligned with SOT (no contradictory “all DONE forever” claims).
3. **BLOCKED** items (Clever/ClassLink native) appear only where SOT marks them **BLOCKED**.
4. `python scripts/verify_45_wedge_scorecard.py` exits **0**.
5. **Phased wedge execution (1–45):** `python scripts/validate_wedges_phase.py --phase all` exits **0** (extends super-premium phases with catalog invariants; static 14–22 checks when default sqlite is shared/locked).
6. **DB-backed sector registry (14–22):** when the default database is available, run `python scripts/validate_wedges_14_22.py` (see [TEST_DATABASE.md](TEST_DATABASE.md)).
7. **Line-by-line surfaces:** `python scripts/verify_wedge_line_registry.py` exits **0** (45 rows in `wedge_line_registry.py`, URL reverses, beachhead slugs in seed source).
8. **Marketplace kit tagging:** `FIRST_PARTY_APPS` in `seed_marketplace_apps.py` — each app has non-empty `manifest.wedge_ids`, and their union is **1–45**; enforced by `apps/marketplace/tests/test_marketplace_wedge_coverage.py` (also run from `verify_phases_3_11_gates.py`).
9. **Tier A beachhead operator checklists (wedges 1–6):** `apps/platform_runtime/beachhead_operator_checklists.py` + partial `templates/schools/partials/beachhead_operator_checklist.html` on curriculum, One SIS, geography (wedge 3 UK path), district enterprise, advancement, HE pack; `python scripts/verify_beachhead_checklists.py` (also from `verify_phases_3_11_gates.py`). **SiteSettings not required** for this bar.

---

## Appendix A — Line-by-line registry (machine source)

**Nothing missed:** Each wedge **1–45** has a row in `apps/platform_runtime/wedge_line_registry.py` (`WEDGE_LINES`): **id**, **name**, **tier (A–F)**, **execution phase (1–5)**, and **manager URL names** that must reverse on `config.manager_urls`.

- **Gate:** `python scripts/verify_wedge_line_registry.py` (also run from `scripts/verify_phases_3_11_gates.py`).
- **Beachhead blueprint slugs (W1 / W3 / Phase 3):** `BEACHHEAD_BLUEPRINT_PACKS` — must exist in `apps/policies/management/commands/seed_blueprint_policy_packs.py`; listed on **Curriculum & region packs** (`super:curriculum_packs`) for operators.
- **Continuous depth** (statutory PDFs per country, ERP coexistence productization, decision-engine dashboards, identity graph primitives) remains **§0.2.1.3 / §11.4** — update the scorecard **Next** column + SOT rows when closing those items; the line registry stays the **surface + phase** map.

| Band | Wedges | Phase | Registry check |
|------|--------|-------|----------------|
| Tier A + geo start | 1–10 | 1 | `validate_wedges_phase.py --phase 1` + `verify_wedge_line_registry.py` |
| Geo end + systems start | 11–20 | 2 | `--phase 2` |
| Systems end + delivery | 21–30 | 3 | `--phase 3` |
| Institution types | 31–40 | 4 | `--phase 4` |
| Types end + glue | 41–45 | 5 | `--phase 5` |

---

## Cleanup / deprecation

- Do **not** add a second “wedge roadmap” outside this file + SOT §0.2.1.
- Retire informal wedge notes only when their content is merged here or into §0.2.1.3.
