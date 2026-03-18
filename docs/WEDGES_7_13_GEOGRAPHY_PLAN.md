# Wedges 7–13 (Geography) — Plan to Proceed

**Purpose:** Single execution plan for Geography wedges (region packs by continent). All status stays in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.2.1.2; this doc is the **what to do** and **order of execution**.

**Scope (SOT §0.2.1):** Platform must support deployment and **local behavior** in every continent via **region packs** (RegionConfig, grading, terms, statutory, language, currency).

---

## 1. Prerequisites (gate before starting Wedge 7)

| Check | Status | Where to verify |
|-------|--------|------------------|
| Phase I (wedges 1–6) complete | **DONE** | SOT Phase I completion gate; WEDGE_WORLD_CLASS_IMPLEMENTATION.md |
| Phase I.5 gate MET | **DONE** | SOT Phase I.5; execution may proceed to Wedges 7–13 |
| Wedge 1–6 validation passing | **DONE** | `python scripts/validate_wedge_world_class.py` |

**No other gate is required.** You can start Wedge 7 as soon as the above are confirmed.

---

## 2. Wedges 7–13 at a glance

| Wedge | Continent / region | What "support" means (SOT) | Current state |
|-------|--------------------|----------------------------|---------------|
| **7** | Africa | Region packs: Anglophone West Africa/WAEC, Francophone, national; EN, FR, AR, PT; currency; calendar; statutory where applicable. | LCA (Low-Connectivity Africa) in REGIONAL_POLICY_PACKS; country aliases CMR, UGA, KEN, NGA, etc. → LCA. No explicit WAEC/Francophone/national sub-packs. |
| **8** | Asia | East, South, Southeast Asia (India, China, Japan, Singapore, etc.); national curricula/exams; language; calendar; ministry reporting. | No Asia pack in REGIONAL_POLICY_PACKS. RegionConfig may exist for some countries via seed. |
| **9** | Europe (beyond UK) | UK (wedge 3) + EU/national (French, German, Dutch, Nordic); GDPR; language; grading frameworks. | EU pack exists; GBR (UK) exists. get_regional_policy_pack maps FRA, DEU, ESP, etc. → EU. |
| **10** | North America | US (Common Core, state), Canada (provincial); district/ministry; FERPA and local compliance. | US pack exists. Canada: no dedicated CAN pack; could map CA → US or add CAN. |
| **11** | South America | Brazil, Spanish-speaking; PT, ES; calendar; ministry reporting. | BRA pack exists. No dedicated Spanish South America pack (e.g. ARG, COL, CHL). |
| **12** | Oceania | Australia, New Zealand (and Pacific where we target); national curricula; statutory and reporting. | AUS, NZL in REGIONAL_POLICY_PACKS and get_regional_policy_pack. **Implemented.** |
| **13** | MENA | Middle East & North Africa; AR, EN, FR; curricula and ministry; calendar and terms. | No MENA pack. Some African countries (e.g. Egypt) could be MENA or Africa. |

---

## 3. Execution order (recommended)

Deliver **one wedge at a time** so each continent is fully "supported" per SOT before moving on.

| Order | Wedge | Rationale |
|-------|--------|-----------|
| 1 | **Wedge 7 — Africa** | LCA already exists; formalize Africa wedge: WAEC (Anglophone West Africa), Francophone, and/or named "Africa" pack; add aliases and control-plane visibility. |
| 2 | **Wedge 8 — Asia** | New REGIONAL_POLICY_PACKS entry (e.g. "ASIA" or regional: India, Singapore, etc.); RegionConfig + get_regional_policy_pack; moe_presets if needed. |
| 3 | **Wedge 9 — Europe (beyond UK)** | Mostly done (EU + GBR). Add explicit "Europe beyond UK" checklist: ensure FRA/DEU/NLD/Nordic aliases, doc, and any EU statutory presets. |
| 4 | **Wedge 10 — North America** | US done. Add Canada (CAN) pack or CAN → US with Canadian defaults (currency CAD, provincial note); FERPA/compliance doc. |
| 5 | **Wedge 11 — South America** | BRA done. Add Spanish South America pack or aliases (ARG, COL, CHL, PER) to a new "LATAM" or reuse BRA pattern for ES. |
| 6 | **Wedge 12 — Oceania** | Already done (AUS, NZL). Formalize as "Wedge 12 complete" in §0.2.1.2 and geography page. |
| 7 | **Wedge 13 — MENA** | New REGIONAL_POLICY_PACKS entry (e.g. MENA); language AR/EN/FR; calendar/terms; ministry requirements. |

---

## 4. What to do for each wedge (template)

For **each** of 7–13:

1. **Region pack(s)**  
   - Add or extend `REGIONAL_POLICY_PACKS` in `apps/siteconfig/tenant_config.py` (code, name, defaults: privacy_framework, data_residency_region, default_language, currency, date_format, grading_scale, term_preset if applicable).  
   - Add `get_regional_policy_pack(region_code)` aliases for relevant country codes.

2. **RegionConfig**  
   - Ensure RegionConfig rows exist for target countries (e.g. `seed_regions` / `seed_global_regions` or import_config).  
   - Link to grading, terms, and locale where applicable.

3. **Statutory / reporting (if applicable)**  
   - Add or link moe_presets (e.g. ministry export) for the region; reference from reports or curriculum packs.

4. **Control-plane visibility**  
   - Curriculum & region packs page already lists REGIONAL_POLICY_PACKS. Optionally add a **Geography** super page that lists wedges 7–13 by continent and links to region packs / Create School / Setup Studio.  
   - Update nav if you add a dedicated Geography hub.

5. **Docs and SOT**  
   - Update §0.2.1.2 row "7–13 Geography" with what's implemented (e.g. "Wedge 7 Africa: WAEC + Francophone + LCA; Wedge 12 Oceania: AUS, NZL").  
   - Update this plan with a short "Wedge N done" line and next wedge.

6. **Validation**  
   - Run `scripts/validate_wedge_world_class.py` (extend if you add new templates/URLs).  
   - Optional: add tests that new region codes resolve via `get_regional_policy_pack`.

---

## 5. Wedge 7 (Africa) — First steps (concrete)

1. **Keep LCA** as the low-connectivity / generic Africa pack; document it as "Africa (low-connectivity)" in the curriculum packs or geography page.
2. **Optional but recommended:** Add **WAEC** as a named pack (Anglophone West Africa): e.g. `REGIONAL_POLICY_PACKS["WAEC"]` or `["AFR_WAEC"]` with defaults (EN, WAEC grading, relevant currency). Map country codes (e.g. NGA, GHA, GMB, SLE, LBR) to WAEC in `get_regional_policy_pack`.
3. **Optional:** Add **Francophone Africa** pack (e.g. `AFR_FR` or reuse EU defaults with FR language and XAF/XOF currency) and map CMR, SEN, CIV, etc., or keep mapping to LCA with language/currency in LCA.
4. **Control plane:** Add a "Geography" or "Region packs by continent" section to the curriculum packs page, or a new super view `super_geography` listing Africa, Asia, Europe, etc., with links to Create School and Setup Studio.
5. **SOT:** In §0.2.1.2, set "7–13 Geography" to include "Wedge 7 Africa: LCA + WAEC (optional) + aliases".
6. **Validation:** Add Africa (and any new pack codes) to validation script or tests.

---

## 6. Summary: what you need to proceed

- **Prerequisites:** Phase I + Phase I.5 done (already the case).  
- **Next action:** Start **Wedge 7 (Africa)** using the template in §4 and the concrete steps in §5.  
- **After each wedge:** Update SOT §0.2.1.2 and this plan; then start the next wedge in order 8 → 9 → 10 → 11 → 12 → 13.  
- **Oceania (12):** Consider marking "Wedge 12 done" and moving on; AUS/NZL are already shipped.

No separate "Phase II Geography" doc is required—track completion in the SOT and in this plan. When all seven geography wedges are implemented, §0.2.1.2 row "7–13" should read **Implemented** with a one-line summary of what each wedge delivers.

---

## 7. Execution status (complete)

**All Wedges 7–13 implemented.** Validation: `python scripts/validate_wedge_world_class.py` (includes geography packs and template).

| Wedge | Continent | Status | Delivered |
|-------|-----------|--------|-----------|
| 7 | Africa | **Done** | LCA, WAEC (Anglophone West Africa), AFR_FR (Francophone Africa); get_regional_policy_pack aliases; Geography page. |
| 8 | Asia | **Done** | ASIA pack; aliases IND, SGP, CHN, JPN, KOR, MYS, THA, IDN, PHL, VNM, etc.; Geography page. |
| 9 | Europe (beyond UK) | **Done** | EU + GBR; extended aliases (NOR, IRL, AUT, PRT, GRC, POL, CZE, ROU, HUN); Geography page. |
| 10 | North America | **Done** | US, CAN pack (PIPEDA, CAD, ca-central-1); CAN/CA aliases; Geography page. |
| 11 | South America | **Done** | BRA, LATAM_ES (Spanish South America); aliases ARG, COL, CHL, PER, ECU, BOL, PRY, URY, VEN; Geography page. |
| 12 | Oceania | **Done** | AUS, NZL (pre-existing); Geography page lists Oceania. |
| 13 | MENA | **Done** | MENA pack (AR, me-south-1); aliases ARE, SAU, EGY, JOR, LBN, KWT, BHR, QAT, OMN, IRQ, IRN, SYR, DZA, TUN, MAR, LBY; Geography page. |

**Control plane:** `super:geography` → `/super/geography/`; nav "Geography (region packs by continent)"; Curriculum & region packs page links to Geography. **Region packs:** All new packs in `apps/siteconfig/tenant_config.py` REGIONAL_POLICY_PACKS and get_regional_policy_pack.

---

## 8. World-class improvements for Wedges 7–13 (Geography)

To make the Geography wedge **world-class** (same bar as wedges 1–6 in [WEDGE_WORLD_CLASS_IMPLEMENTATION.md](WEDGE_WORLD_CLASS_IMPLEMENTATION.md)), add the following. Track completion in this section and in SOT §11 North star / §0.4 where relevant.

### Per-continent statutory and ministry reporting

| Continent | Improvement | Why | Status |
|-----------|-------------|-----|--------|
| Africa | WAEC preset already in moe_presets; add or link Francophone Africa statutory preset if needed (e.g. CEP, bulletin). | SOT: "statutory reporting where applicable." | WAEC done; Francophone bulletin_fr covers some. |
| Asia | moe_presets placeholder **asia_generic** added; extend with India CBSE, Singapore, Japan when we go to market. | SOT: "ministry reporting where applicable." | **Done** (placeholder). |
| Europe | Ofsted (UK) and EU-style presets; document GDPR/local compliance per pack. | SOT: "GDPR and local compliance." | Ofsted done; EU doc optional. |
| North America | US Common Core preset exists; **canada_provincial** moe_presets placeholder added (extend with Ontario, BC as needed). | SOT: "FERPA and local compliance." | **Done** (placeholder). |
| South America | **latam_es** moe_presets placeholder added for Spanish LATAM (Argentina, Colombia, Chile, etc.). | SOT: "ministry reporting." | **Done** (placeholder). |
| Oceania | AUS/NZL: document or add statutory preset if required (e.g. NAPLAN, NZ ministry). | SOT: "statutory and reporting." | Documented; presets incremental. |
| MENA | **mena_generic** moe_presets placeholder added; extend with UAE, Saudi, Egypt when we go to market. | SOT: "ministry requirements." | **Done** (placeholder). |

### Geography page and control-plane UX

| Improvement | Description | Status |
|-------------|-------------|--------|
| **"What's in this pack"** | On Geography page, per continent show: currency, language(s), grading scale, data residency, privacy framework (from pack defaults). | **Done** — super_geography passes pack details; template shows Currency, Language, Grading, Data residency, Privacy. |
| **Choose region → Create School** | Link "Create school" with region or pack pre-selected (e.g. query param or Create School step 1 default from geography). | **Done** — Geography per-pack "Create school (this pack)" links with `?pack=CODE`; wizard pre-selects country and shows initial_pack; SOT and BEYOND_REACH recorded. |
| **Compare packs** | Optional: side-by-side or expandable "Compare region packs" (e.g. US vs CAN vs GBR). | Not done. |
| **Performance and a11y** | Geography page in performance budgets (advisory); ensure template uses content-max, i18n, and accessibility.css. | **Done** — Super geography in check_performance_budgets.py and PERFORMANCE_BUDGETS.md; template has role="main", aria-label, i18n. |

### RTL and regional UX (N22)

| Improvement | Description | Status |
|-------------|-------------|--------|
| **MENA / RTL** | MENA pack has `defaults.rtl: True`; tenant_config compiler sets `is_rtl` from pack; Geography page shows RTL badge for MENA. | **Done** — REGIONAL_POLICY_PACKS MENA defaults.rtl=True; Geography displays RTL badge. |
| **Regional packs as installable** | SOT N22: "regional packs as installable products." Geography and Curriculum packs already list packs; ensure Create School / Setup Studio let user pick a region pack explicitly. | Partial; pack choice in signup/setup. |

### National curricula and exams (Asia / others)

| Improvement | Description | Status |
|-------------|-------------|--------|
| **Asia sub-packs or presets** | ASIA pack is generic. Extend with India (CBSE, state boards), Singapore, Japan, China (Gaokao) as curriculum presets or education_dna entries **when needed for sales**; moe_presets asia_generic is the placeholder. | Documented; add presets when we go to market. |
| **Canada provincial** | CAN pack exists; **canada_provincial** moe_preset placeholder added; add province-specific templates (e.g. Ontario, BC) when needed for sales. | **Done** (placeholder); extend by province when needed. |

### Data residency and trust per region

| Improvement | Description | Status |
|-------------|-------------|--------|
| **Trust center: per-continent data residency** | Trust center already has "Data residency & sovereignty." Add a sentence or link: "Region packs define default data residency; see Geography." | Optional; Geography page shows per-pack data residency. |
| **Geography → Trust** | On Geography page, link to Trust center for "Where does my data live?" per pack. | **Done** — "Where does my data live?" button links to super:trust_center. |

### Grading and qualification frameworks

| Improvement | Description | Status |
|-------------|-------------|--------|
| **Per-pack grading visible** | Packs already have grading_scale (0–100, 0–20, A*-G). Surface on Geography or in "What's in this pack" so operators see at a glance. | **Done** — Geography "What's in this pack" shows Grading per pack. |
| **Qualification frameworks** | Document or link EU (EQF), UK (RQF), etc. where relevant for compliance. | Not done (optional). |

### Summary: world-class Geography execution (complete)

1. **Done:** Geography page "What's in this pack" (currency, language, grading, data residency, privacy); link Geography → Trust center ("Where does my data live?").
2. **Done:** Performance budget for `/super/geography/`; a11y (role="main", aria-label) and i18n on template.
3. **Done:** moe_presets placeholders: asia_generic, canada_provincial, latam_es, mena_generic (extend with country-specific when we go to market).
4. **Done:** RTL/MENA: MENA pack defaults.rtl=True; is_rtl set in tenant config; Geography shows RTL badge.
5. **Done:** Asia and Canada documented as "extend when needed for sales"; placeholders in moe_presets.
6. **Done:** Choose region → Create School: per-pack links and wizard pre-select (see table above).

---

## 9. Validation before continuing

Before proceeding past the Geography wedge, run:

| Check | Command | Expected |
|-------|---------|----------|
| Wedge world-class script | `python scripts/validate_wedge_world_class.py` | Exit 0, "validation passed" |
| Django system check | `python manage.py check` | No issues |
| Wedge unit tests | `python manage.py test apps.schools.tests.test_wedge_world_class_implemented --no-input` | All 7 tests pass (run when no other process holds test DB) |

**When all pass:** Wedges 7–13 (Geography) are complete; you can continue to the next phase (e.g. BEYOND_REACH remaining items, §6 app-by-app, or next wedge work per SOT).
