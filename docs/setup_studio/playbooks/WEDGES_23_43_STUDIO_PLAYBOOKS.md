# Studio playbooks — Wedges 23–43 (delivery + institution)

**Catalog version:** see `CATALOG_VERSION` in `apps/platform_runtime/learning_institution_catalog.py`  
**Machine export:** `super:learning_institution_catalog_json`

## Per-wedge quick refs

| Range | Playbook focus |
|-------|----------------|
| **W23–W26** | Physical + online spine: scheduling, attendance, LMS/LTI, competency rubrics. |
| **W27–W30** | Mastery retakes, portfolios/PBL, async paths, cohort rollover. |
| **W31–W34** | K–12 core, TVET hours, apprenticeship dual records, specialty tracks. |
| **W35–W38** | Early years observations, adult session billing, corporate PD credits, CEFR cycles. |
| **W39–W43** | Exam prep packages, IEP/MDT, acceleration, alternative provision, HE degree audit. |

## Operator steps

1. **Tenant:** Backend → Institution profile → select delivery checkboxes + institution type → Apply.  
2. **Suggest:** Use “Load suggestion” (heuristic) or `GET /api/learning/institution-suggest/?ai=1` when gateway enabled.  
3. **Pack install:** `POST /api/learning/pack-install/` with `pack_slug` from catalog `pack_slugs`; `record_marketplace:true` creates first-party marketplace install row.  
4. **Pack rollback (N20):** `POST /api/learning/pack-rollback/` JSON body `pack_slug`, `confirm_learning_wedge_rollback: "ROLLBACK"`, optional `sync_marketplace` (default true). Removes pack from `wedge_marketplace_installs`, clears mapped features only when no other installed wedge still needs them, emits `learning_wedge_pack_rolled_back`.  
5. **Features:** Pack-derived keys live in `school.features`; `is_feature_enabled(school, code)` honors them.  
6. **Ministry PDF:** From wizard links or `GET /api/learning/ministry-pdf/?stub=…`.  
7. **Terminology:** `GET /api/learning/terminology/?locale=fr&institution_code=W43_HIGHER_EDUCATION`.  
8. **Benchmarks (super):** `GET /api/internal/learning-wedge-benchmarks/` — anonymized adoption counts.

## RFP / accreditation narrative

Map selected **institution type** to ministry stub list in catalog; export PDF shells for attach to compliance packets. Upgrade path: replace stub PDFs with live ministry connector aggregates when available.
