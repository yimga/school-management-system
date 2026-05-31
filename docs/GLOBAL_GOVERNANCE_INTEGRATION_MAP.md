# Global Governance Integration Map

Links the country governance matrix to existing RunMyCampus localization and reporting layers.

## Core artifacts

| Artifact | Path | Role |
|----------|------|------|
| Country governance matrix | `docs/generated/country_governance_matrix.json` | 249 ISO rows — governance, languages, terminology |
| Per-country shards | `docs/generated/country_governance_matrix/{iso}.json` | Authoritative per-ISO truth |
| Dissection ledger | `docs/generated/country_dissection_ledger.json` | Wave progress (`skeleton` → `verified`) |
| Completion register | `docs/generated/global_governance_completion_register.json` | Program checklist |

## Runtime consumers (wired — global academic OS kernel, batch 1585)

| Matrix / pack field | Consumer | Status |
|---------------------|----------|--------|
| `education_pack_tier` + live `_source` | `apps/governance/academic_pack_bridge.py`, `scripts/verify_global_academic_kernel_assumptions.py`, `scripts/reconcile_matrix_tier_to_live_registry.py` | **wired** |
| `school_types`, `education_levels` | `apps/academics/structure_provisioning.py`, `GET /api/v1/runtime/structural-options` | **wired** |
| `grading_preset_key` | `apps/governance/country_matrix_service.py::signup_governance_defaults`, `apps/policies/resolver.py`, `apps/siteconfig/education_profile_engine.py` | **wired** |
| `supports_multi_shift` | `structural-options` runtime + `apps/academics/scheduling.py::InstructionShift` | **wired** |
| Grade scale families | `apps/registries/services.py::ensure_grade_scale_seed`, `scripts/verify_grading_scale_registry_coverage.py` | **wired** |
| Grading JSON-Logic templates | `apps/policies/grading_nuance_templates.py` → `get_effective_policy` + `CustomNuance` sync | **wired** |
| Academic structure breadcrumb | `apps/siteconfig/terminology_service.py::academic_structure_breadcrumb` | **wired** |
| Structure provision API | `POST /api/v1/runtime/structural-options/initialize` | **wired** |
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
python scripts/verify_global_academic_kernel_assumptions.py --strict --write
python scripts/verify_grading_scale_registry_coverage.py --strict --write
```
