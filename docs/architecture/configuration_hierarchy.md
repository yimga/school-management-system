# Configuration Hierarchy (Checklist Section 4.8)

Explicit order of precedence for tenant behavior. **Lower in the list overrides higher.** All resolution goes through the Policy/Blueprint layer; app code must not branch on country/tenant directly.

## Order (highest → lowest precedence)

| Level | Name | Description | Source |
|-------|------|-------------|--------|
| 1 | **Platform** | Global defaults (terminology, grading, workflows, features) | `apps.policies.resolver` platform defaults |
| 2 | **Country** | Country-level defaults (currency, timezone, language, RTL, grading scale) | Region/Country registry; `school.default_region` |
| 3 | **Region** | Province/state/region within country | RegionRegistry, ProvinceStateRegistry |
| 4 | **Education level** | Early years, primary, secondary, tertiary, vocational, adult | EducationLevelRegistry (future); school settings |
| 5 | **Institution type** | General, trade, technical, STEM, religious, international | InstitutionTypeRegistry (future); school settings |
| 6 | **Education system** | National, British/GCSE, IB, AP, CBSE, Cambridge, custom | EducationSystemRegistry (future); school settings |
| 7 | **Tenant** | School-specific overrides | `School.settings`, `School.features` (via get_effective_policy only) |
| 8 | **Admin** | Admin-configured overrides (e.g. customizer) | Same as tenant; persisted in school/siteconfig |
| 9 | **Scheduled** | Time-bound or seasonal overrides | Future: scheduled policy versions |
| 10 | **Role** | Role-specific (e.g. teacher vs principal) | Future: role-scoped policy slice |
| 11 | **Campus** | Per-campus overrides (multi-campus schools) | Future: campus_id in policy |
| 12 | **Incident** | One-off overrides (e.g. incident type) | Future: incident-scoped overrides |

## Current implementation

- **Implemented:** Platform (1) → Country/Region (2–3) via `school.default_region` and region attributes → Tenant (7) via `School.settings` and `School.features`. Merged in `get_effective_policy(school)`; optional `TenantBlueprint.active_bundle` when `POLICY_USE_BUNDLES` is set.
- **Partial:** Education level / institution type / education system live in school or siteconfig (e.g. `education_profile`, `education_dna_preset`); not yet full registry-driven (Section 20).
- **Deferred:** Scheduled, role, campus, incident levels (Phase 2+).

## Rules

- No app code may read `school.settings` or `school.features` for behavior; use `get_effective_policy(school)` or `get_tenant_blueprint(request)`.
- Invalidation: when tenant or admin updates settings/features, call `invalidate_policy_cache(school)` so the next request gets fresh policy.
- New levels must be added in this doc and in the resolver merge order.
