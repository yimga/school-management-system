# Catalog-backed dropdowns and admission number config audit

**Goal:** Ensure dropdowns that should be driven by catalogs are, and admission number config is consistent (codebase audit item).

## Catalog sources

| Catalog / registry        | Model / source                    | Used for dropdowns in                    |
|---------------------------|------------------------------------|------------------------------------------|
| RegionConfig              | siteconfig.RegionConfig           | School default_region, locale/region     |
| Subjects                  | academics.Subject                 | Class setup, assignments                 |
| Grading scales            | siteconfig.GradingScaleConfig etc.| Report cards, evals                      |
| Fee types / payment       | finance (FeeType, PaymentMethod)  | Invoicing, payments                      |
| Education levels/systems | registries (education_levels etc.) | School taxonomy                          |

- **Pattern:** Prefer reading options from the catalog table (with tenant/school filter where applicable) instead of hardcoded choices. Where choices are still hardcoded, consider migrating to a catalog model and a single dropdown source.

## Admission number config (centralized)

- **Where configured:**
  - **SiteSettings:** `admission_number_mode`, `admission_number_strategy`, `admission_number_template`, `admission_number_pattern` (global/default).
  - **School-level override (optional):** TenantAdmissionNumberPolicy (OneToOne with School) when present overrides SiteSettings for that school.

- **Usage:**
  - **Admin / API / signup:** When generating or validating an admission number, use the resolved config for the school (TenantAdmissionNumberPolicy for school if exists, else SiteSettings).
  - **Templates:** Placeholders in `admission_number_template`: `{year_2digit}`, `{school_code}`, `{seq_4digit}`, `{spec_code}`, `{class_segment}`.
  - **Validation:** `admission_number_pattern` (regex) validates format.

- **Consistency:** All flows that create or validate student admission numbers should use the same resolution (school → policy or site default) and the same template/strategy/pattern. See `apps/siteconfig/models.py` (SiteSettings, TenantAdmissionNumberPolicy) and any admission number generator in people/schools.

## Tests

- **Admission number:** A test creates a school (with or without TenantAdmissionNumberPolicy), calls the admission number generator with the expected strategy/template, and asserts the output matches the expected format (e.g. regex from pattern).
- **Catalog dropdown:** For one critical dropdown (e.g. default_region), a test can assert that the options are loaded from the catalog model (e.g. RegionConfig) and not from a hardcoded list.

## Related

- `apps/siteconfig/models.py` — SiteSettings (admission_number_*), TenantAdmissionNumberPolicy.
- `docs/SCHOOL_LOCATION_AND_REGION_PICKER.md` — RegionConfig as single picker.
- `docs/RUNMYCAMPUS_CODEBASE_AUDIT_AND_WORLD_CLASS_ROADMAP.md` — audit context.
