# Blueprint Registry — Current State vs Section 20

Maps checklist Section 20 (Global Blueprint Registry) to what exists today and what remains to add.

## Section 20.1 – Country, regions, timezone/currency, formatting

| Requirement | Current state | Location |
|-------------|---------------|----------|
| Country, country code, names | **Done** | `apps.registries.models.CountryRegistry` (code, name, default_language, default_currency, default_timezone, labels, metadata) |
| Regions/provinces/states | **Done** | `apps.registries.models.SubdivisionRegistry` (country FK, code, name, subdivision_type, labels) |
| Calendars, school week, timezone/currency | **Done** | CountryRegistry defaults + TimeZoneRegistry, CurrencyRegistry, CalendarSystemRegistry |
| Number/date formatting | **Done** | LocaleRegistry (date_format, time_format, number_format, is_rtl) |

## Section 20.2 – Education levels, institution types, systems, grading, etc.

| Requirement | Current state | Location |
|-------------|---------------|----------|
| Education levels | **Done** | `apps.registries.models.EducationLevelRegistry` (code, name, ...) |
| Institution types | **Done** | InstitutionTypeRegistry (code, name, country_labels) |
| Education systems | **Done** | EducationSystemTypeRegistry (use as EducationSystemRegistry); school/siteconfig can reference by code |
| Grading, attendance models, admissions documents | **Partial** | Resolver merges from region/school; SiteSettings has admission_number_*; no dedicated registry tables for grading/attendance presets |
| Compliance/privacy, finance/tax/comms defaults | **Partial** | In get_effective_policy from region/school; no dedicated registry models |
| Language/RTL, terminology, branding | **Partial** | Region/school in resolver; CountryProfile (policies) has is_rtl, grading_scale |
| Academic year, holiday strategy, address model, student identifier, admission number patterns | **Partial** | SiteSettings admission_number_*; rest in school/siteconfig |

## Section 20.3–20.5 – Education levels / institution types / systems (labels and multi-select)

- **Education levels:** EducationLevelRegistry with country_labels for country-sensitive labels. **Done.**
- **Institution types:** InstitutionTypeRegistry (multi-select; country_labels for localization). **Done.**
- **Education systems:** EducationSystemTypeRegistry (multi-select; country_labels; use as EducationSystemRegistry). **Done.**

## Section 20.6 – Control-plane models

| Model | Current state | Location / note |
|-------|---------------|------------------|
| CountryRegistry | **Done** | apps.registries.models |
| RegionRegistry | **Done** (as SubdivisionRegistry) | apps.registries.models |
| ProvinceStateRegistry | **Same as SubdivisionRegistry** | Use SubdivisionRegistry with subdivision_type |
| TimeZoneRegistry | **Done** | apps.registries.models (code, name, utc_offset, metadata) |
| CurrencyRegistry | **Done** | apps.registries.models (code, name, symbol, decimal_places) |
| LocaleRegistry | **Done** | apps.registries.models (code, date/time/number format, is_rtl) |
| CalendarSystemRegistry | **Done** | apps.registries.models (code, term_count_per_year, country_code) |
| EducationLevelRegistry | **Done** | apps.registries.models |
| InstitutionTypeRegistry | **Done** | apps.registries.models (code, name, country_labels) |
| EducationSystemRegistry | **Done** (as EducationSystemTypeRegistry) | apps.registries.models; use for curriculum/system multi-select |
| AcademicTerminologyRegistry | **Done** | apps.registries.models (code, terminology JSON, country_code) |
| TenantBlueprint | **Done** | apps.policies.models (school → active_bundle) |
| TenantPolicyPack | **Partial** | PolicyBundle in policies.models; name overlap |
| TenantFeatureEntitlement | **Partial** | School.features / plan; no dedicated model |
| TenantBrandProfile | **Partial** | SiteSettings/school branding; no single TenantBrandProfile model |
| TenantDashboardAssignment | **Open** | Dashboard-by-role assignment |
| TenantWorkflowRegistry | **Partial** | siteconfig workflow template; no full registry model |
| TenantModuleConfig | **Partial** | School.settings per module; no dedicated model |
| TenantAdmissionNumberPolicy | **Partial** | SiteSettings admission_number_*; people.StudentProfile.generate_admission_number; no dedicated policy model |
| TenantComplianceProfile | **Open** | Compliance settings per tenant |
| MarketplaceApp | **Check** | apps.marketplace |
| MarketplacePermissionScope | **Check** | apps.marketplace |
| TenantInstalledApp | **Check** | apps.marketplace (AppInstallation or similar) |
| AppLifecycleEvent | **Open** | Audit events for app install/uninstall |

## Next steps (after Section 20 Phase 5)

1. **Use new registries:** Prefer TimeZoneRegistry, CurrencyRegistry, LocaleRegistry, CalendarSystemRegistry, InstitutionTypeRegistry, AcademicTerminologyRegistry in forms/APIs instead of hardcoded lists or CountryRegistry-only defaults. Seed data can be added via management command or admin.
2. **Section 21–22:** Geography/school setup and TenantAdmissionNumberPolicy (Section 22) remain; use registries for province/state, calendar, terminology.
3. **Marketplace:** Verify MarketplaceApp, AppInstallation, scopes in apps.marketplace and align names to Section 20.6.
4. **TenantBrandProfile, TenantDashboardAssignment, etc.:** Optional control-plane models; currently covered by School/SiteSettings/policy where sufficient.
