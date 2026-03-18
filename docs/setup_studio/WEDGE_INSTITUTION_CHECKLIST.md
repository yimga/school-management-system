# Setup Studio — Wedges 23–43 (delivery + institution types)

**Canonical registry:** `apps/platform_runtime/learning_institution_catalog.py`  
**Runtime apply:** `apply_learning_institution_packs` + **Backend → Institution profile**  
**Super:** `super:learning_delivery_packs`, `super:ministry_report_stubs`, `super:learning_institution_catalog.json`

## Learning / delivery (23–30) — verify each mode is understood

| Wedge | Mode | Code |
|-------|------|------|
| 23 | In-person | W23_IN_PERSON |
| 24 | Fully online | W24_FULLY_ONLINE |
| 25 | Hybrid / blended | W25_HYBRID |
| 26 | Competency-based | W26_COMPETENCY_BASED |
| 27 | Mastery-based | W27_MASTERY_BASED |
| 28 | Project-based | W28_PROJECT_BASED |
| 29 | Self-paced | W29_SELF_PACED |
| 30 | Cohort-based | W30_COHORT_BASED |

## Education types (31–43)

| Wedge | Type | Code |
|-------|------|------|
| 31 | General / academic K–12 | W31_GENERAL_K12 |
| 32 | TVET | W32_TVET |
| 33 | Trade / apprenticeship | W33_TRADE_APPRENTICESHIP |
| 34 | Specialized (STEM, arts, sports) | W34_SPECIALIZED_STEM_ARTS |
| 35 | Early years / pre-K | W35_EARLY_YEARS |
| 36 | Adult education | W36_ADULT_EDUCATION |
| 37 | Professional / corporate | W37_PROFESSIONAL_CORPORATE |
| 38 | Language schools | W38_LANGUAGE_SCHOOL |
| 39 | Exam prep / tutoring | W39_EXAM_PREP_TUTORING |
| 40 | Special education | W40_SPECIAL_EDUCATION |
| 41 | Gifted / advanced | W41_GIFTED_ADVANCED |
| 42 | Alternative provision | W42_ALTERNATIVE_PROVISION |
| 43 | Higher education | W43_HIGHER_EDUCATION |

## Checklist

1. [x] Tenant: **Institution profile** — select delivery + type → save.
2. [x] Confirm `school.settings`: `learning_delivery_wedges`, `institution_type_wedge`, `ministry_report_stub_slugs`, `workflow_pack_hints`, `report_template_hints`.
3. [x] Super: confirm catalog tables match this doc; download JSON (`catalog_version` included).
4. [ ] Curriculum packs + education systems aligned to region.
5. [x] Ministry stubs: **PDF export** from wizard + `/api/learning/ministry-pdf/`.
6. [x] **Beyond-reach:** `is_feature_enabled` reads `school.features`; one-click pack install API; terminology API; AI/heuristic suggest; cross-tenant benchmarks (super). Playbooks: `docs/setup_studio/playbooks/WEDGES_23_43_STUDIO_PLAYBOOKS.md`.
