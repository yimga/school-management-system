# Wedges 14–22 (Education systems) — Plan and checklist

**Purpose:** Single execution plan for Education system types (sector). All status stays in [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §0.2.1; this doc is the **what to do** and **validation** checklist.

**Scope (SOT §0.2.1):** Platform must support every **system type** we target: Public/state, Private, Charter, International, Faith-based, Home-school, Government/ministry, NGO, Multi-campus/group. Delivered via configuration, packs, and RBAC.

---

## 1. Registry and data model (single source for sector)

| # | Code | Name | What "support" means | Registry | Config/RBAC hook |
|---|------|------|----------------------|----------|-------------------|
| 14 | PUBLIC | Public / state | Funding and compliance; district/ministry reporting; statutory returns; role model (state, district, school). | EducationSystemTypeRegistry (category=sector) | moe_presets, statutory reporting (Ofsted, WAEC, ministry exports). |
| 15 | PRIVATE | Private / independent | Tuition, fees, aid; admissions; same platform as public. | Same | Tuition/aid workflows; fee defaults. |
| 16 | CHARTER | Charter | Hybrid public accountability and school autonomy; reporting and funding rules. | Same | Reporting templates; funding rules. |
| 17 | INTERNATIONAL | International | Multi-country, multi-curriculum (IB, UK, US, national); one school, many systems; language and currency. | Same | REGIONAL_POLICY_PACKS, multi-language, multi-currency. |
| 18 | FAITH_BASED | Faith-based | Same as private plus optional faith-specific reporting or branding. | Same | Optional faith reporting/branding. |
| 19 | HOME_SCHOOL | Home-school / hybrid | Part-time, external, or home-school students; attendance and assessment flexibility. | Same | Attendance/assessment config. |
| 20 | GOVERNMENT_MINISTRY | Government / ministry | Ministry or regional authority as tenant or aggregator; district control plane; national reporting. | Same | moe_presets, statutory returns; control plane. |
| 21 | NGO | NGO / non-profit | Donor and program reporting; grants; often private + advancement. | Same | Advancement (Phase 2): donor/campaign/gift/receipt. |
| 22 | MULTI_CAMPUS | Multi-campus / group | One tenant or hierarchy (group → campuses); shared reporting and governance. | Same | parent_school_id, hierarchy_path; Group & campuses. |

**Single registry:** EducationSystemTypeRegistry holds all nine with `category="sector"`. Seeded in `apps/registries/services.py` (DEFAULT_EDUCATION_SYSTEM_TYPES, WEDGE_14_22_SECTOR_CODES). School has `primary_sector` (CharField) and `education_system_types` (M2M).

---

## 2. Control-plane visibility

- **Super view:** `super:education_systems` — lists all nine with "what support means"; links to Create School, Setup Studio, Geography, Curriculum packs, Runtime inspector (RBAC/config), Registries, Report library (ministry/statutory), Advancement hub (NGO), Schools list (multi-campus).
- **Nav:** Control plane → Schools → "Education systems (14–22)".
- **Multi-campus (22):** View and docs call out hierarchy (parent_school_id, hierarchy_path); link to Schools list and how to create/link group and campuses.

---

## 3. Create School / Setup Studio

- **Sector step/field:** Create School wizard includes "Primary sector (Wedges 14–22)" dropdown; choices from list_sector_system_types_14_22(). At least one sector should be selected (primary_sector and/or education_system_type_codes).
- **Persistence:** School.primary_sector set from first sector code in education_system_type_codes; education_system_types M2M set from full list.

---

## 4. RBAC and config by system type

**Mapping (document and where useful implement):**

| System type | Compliance / reporting defaults | Concrete examples |
|-------------|--------------------------------|--------------------|
| PUBLIC (14) | Ministry reporting; statutory returns | moe_presets; Ofsted, WAEC, ministry exports; role model state/district/school. |
| PRIVATE (15) | Tuition, fees, aid | Fee workflows; aid services; admissions. |
| CHARTER (16) | Hybrid accountability; funding rules | Reporting templates; funding rules. |
| INTERNATIONAL (17) | Multi-curriculum; multi-language/currency | REGIONAL_POLICY_PACKS; locale; currency. |
| FAITH_BASED (18) | As private + optional faith reporting | Optional faith branding/reports. |
| HOME_SCHOOL (19) | Flexible attendance/assessment | Attendance rules; assessment config. |
| GOVERNMENT_MINISTRY (20) | District control plane; national reporting | moe_presets; statutory; control plane. |
| NGO (21) | Donor/campaign reporting | Advancement hub; Phase 2 donors/campaigns/gifts. |
| MULTI_CAMPUS (22) | Hierarchy; shared reporting | parent_school_id; hierarchy_path; Group & campuses. |

Role sets or permission templates can differ by system type (e.g. ministry reporting roles for public, tuition/aid for private, donor reporting for NGO). Feature flags or reporting defaults can be driven by school.primary_sector or education_system_types. **Runtime:** `TenantRuntime.tenant.primary_sector` (and `inspect_runtime` output) expose the school's primary sector so resolvers and RBAC can key off it on one platform.

**Implemented:** Sector-based role suggestions are in `apps.registries.services`: `SECTOR_ROLE_SUGGESTIONS` (mapping sector code → `suggested_roles` list and `description`) and `get_sector_role_suggestions(primary_sector)`. Use when assigning default roles or in Setup Studio / Education systems to show "suggested roles for your sector" (e.g. PUBLIC → PRINCIPAL, BURSAR, CENSOR; NGO → ADMIN, BURSAR, COMMS_STAFF).

---

## 5. High-impact links (non-negotiable)

- **Ministry / statutory (14, 20):** Public/state and Government/ministry linked to moe_presets and statutory reporting (Ofsted, WAEC, ministry exports) — Report library and Education systems view.
- **NGO (21):** Linked to Advancement (Phase 2) and donor/campaign reporting — Advancement hub from Education systems view.
- **International (17):** Linked to REGIONAL_POLICY_PACKS, multi-language, multi-currency — Geography and Curriculum packs from Education systems view.

---

## 6. World-class bar (validation)

- All nine sector codes exist in EducationSystemTypeRegistry (category=sector).
- Super view "Education systems (14–22)" exists and lists all nine with descriptions.
- Create School wizard has sector field and persists primary_sector + education_system_types.
- Validation script: `python scripts/validate_wedges_14_22.py` — exits 0 when all checks pass.

---

## 7. Validation script

Run: `python scripts/validate_wedges_14_22.py`

Checks:
1. All nine codes in WEDGE_14_22_SECTOR_CODES exist in EducationSystemTypeRegistry and are active.
2. Super view URL `super:education_systems` resolves.
3. Template `schools/super_education_systems.html` exists.
4. School model has field `primary_sector`.
5. list_sector_system_types_14_22() returns exactly nine items.

---

## 8. Verification record

| Check | Result |
|-------|--------|
| `python scripts/validate_wedges_14_22.py` | **PASS** (exit 0) — template, URL, view, nine registry rows (`category=sector`), `School.primary_sector`, `list_sector_system_types_14_22()` count/codes |
| Create School wizard | **Present** — `super_create_school_wizard.html`: Primary sector (14–22) + education system types; server requires ≥1 sector |
| Control plane | **Present** — `super:education_systems`, nav entry, links (Create school, Setup Studio, Geography, curriculum packs, runtime inspector, registries, report library, advancement, group/campuses); schools list filter by `primary_sector` |
| Wedge 22 | **Present** — `super:group_campuses`, hierarchy + add campus URL |

**World-class closure (2026):**

1. **Education systems accordion:** All **nine** sectors have expandable “What support means” rows with next-action links via `build_education_system_support_accordion()` (`apps/registries/services.py`).
2. **Bootstrap AccessRoles:** On provisioning with a contact email, `apply_wedge_14_22_sector_access_roles_to_user()` attaches `AccessRole` rows for sector `suggested_roles` (skips STUDENT/PARENT/EMPLOYER) plus **ADMIN**. Logged as `SchoolProvisioningEvent` `SECTOR_ROLES_APPLIED`. Test: `ProvisioningJobTests.test_provision_applies_wedge_14_22_sector_access_roles`.
3. **Create School API:** `school.settings.provisioning` stores `sector_suggested_roles` and `sector_role_description`.
4. **Setup Studio:** Payload includes `sector_staff_roles` (suggested codes + bootstrap note). `_recommended_by_sector` includes PRIVATE, CHARTER, FAITH_BASED, HOME_SCHOOL.

*Verify: `python scripts/validate_wedges_14_22.py` (includes accordion checks).*
