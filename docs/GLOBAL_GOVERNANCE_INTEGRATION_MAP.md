# Global Governance Integration Map

Links the country governance matrix to existing RunMyCampus localization and reporting layers.

## Core artifacts

| Artifact | Path | Role |
|----------|------|------|
| Country governance matrix | `docs/generated/country_governance_matrix.json` | 249 ISO rows — governance, languages, terminology |
| Per-country shards | `docs/generated/country_governance_matrix/{iso}.json` | Authoritative per-ISO truth |
| Dissection ledger | `docs/generated/country_dissection_ledger.json` | Wave progress (`skeleton` → `verified`) |
| Completion register | `docs/generated/global_governance_completion_register.json` | Program checklist |

## Runtime consumers (target wiring)

| Matrix field | Existing service | Phase |
|--------------|------------------|-------|
| `education_pack_tier` | `apps/siteconfig/country_localization_service.py::resolve_country_pack` | 0C sync, 3A runtime |
| `official_languages` | `apps/siteconfig/_seed_country_languages.py` | 0C |
| `local_terminology` | `apps/siteconfig/terminology_service.py` | 0C, 3C |
| `name_order`, formats | `apps/siteconfig/country_formats_service.py` | 0C |
| `deep_layers.mc_profile` | `apps/migration_cloud/country_profiles.py` | 3D |
| `deep_layers.moe_preset` | `apps/reports/moe_presets.py` | 3D |
| `governance_archetype` | Signup wizards, Group Console labels | 3A, 4A |
| `admin_levels` | Group Console + statutory hints | 3A |
| `reporting_chain` | `emis/services.py`, `EMISSubmission` | 4D |
| Subdivisions | `apps/registries` `SubdivisionRegistry` | 3B |

## Wedge cross-links

- Wedges 7–13 (geography): `docs/WEDGES_7_13_GEOGRAPHY_PLAN.md`
- Wedges 14–22 (education systems): `scripts/validate_wedges_14_22.py`
- Wedge 22 (group hierarchy): `apps/schools/mat_group_hub.py` → `Organization` Phase 2
- Institution types 31–43: `apps/platform_runtime/learning_institution_catalog.py`

## Verifiers

```bash
python scripts/verify_country_governance_matrix.py --allow-skeleton
python scripts/verify_country_dissection_ledger.py --allow-skeleton
python scripts/verify_country_layer_consistency.py --allow-skeleton
python scripts/verify_global_governance_plan_completion.py --phase-max 0A
```
