# Runtime precedence + tenant-editable registry keys

**Canonical precedence:** [runtime_precedence.md](runtime_precedence.md) (platform → registry → blueprint → policy → entitlement → tenant → sandbox).

## Tenant compiled config layers

`apps/siteconfig/tenant_config.compile_effective_tenant_config` merges, in order:

1. **Global** platform defaults  
2. **Region pack** (continent/country)  
3. **Education profile** (systems on the school)  
4. **Plan add-ons**  
5. **Tenant override** (`school.settings` keys allowed by product)  
6. **Campus override** (multi-campus)  
7. **User override** (where implemented)

Persisted snapshot: `school.settings["tenant_compiled_config"]` via `persist_compiled_tenant_config`.

## Tenant-editable registry keys (code paths)

| Area | Model / API | Resolution |
|------|-------------|------------|
| Attendance codes | `registries.TenantAttendanceCode` | `registries.services.get_effective_attendance_codes(school)` — tenant rows replace defaults |
| Fee line types | `registries.TenantFeeTypeEntry` | `get_effective_fee_types_for_school(school)` — tenant rows or `FeeCategoryRegistry` by country |
| Terminology | `AcademicTerminologyRegistry` + policy | `get_terminology_packs_for_country` |
| Grading | `GradingScaleConfig` / policy | `get_effective_policy` grading keys |

Enable **live compliance** per school: `school.settings["compliance_live_validation"] = true` — enrollment/attendance payloads validated via `POST /api/internal/br/compliance/validate-enrollment/` and `validate-attendance/`.

**Messaging retention (BR-08):** `school.settings["messaging_retention_days"]` or `comms_retention_days`.

**Legacy SIS read-only (BR-09):** `school.settings["legacy_sis_readonly"]` — see [BR_LAND_AND_EXPAND_LEGACY_SIS.md](BR_LAND_AND_EXPAND_LEGACY_SIS.md).

*SOT: RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §0.2.2, Tier 1b.*
