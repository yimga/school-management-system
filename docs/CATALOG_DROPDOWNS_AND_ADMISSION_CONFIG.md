# Catalog-backed dropdowns and admission number config

**Goal:** Dropdowns that should be driven by catalogs are; admission number config is centralized and consistent.

## Catalog sources

- **RegionConfig** — `siteconfig.RegionConfig`: country/region, timezone, grading scale, currency.
- **Subjects** — `academics.Subject` (tenant-scoped).
- **Grading scales** — `siteconfig.GradingScaleConfig` or region defaults.
- **Fee types / payment methods** — `finance.FeeType`, `finance.PaymentMethod` (region/school scoped).
- **Education levels / systems** — `siteconfig` and School-level assignments.

## Dropdown → source mapping (audit)

| Context              | Dropdown        | Source (catalog)                    |
|----------------------|-----------------|-------------------------------------|
| School form          | Default region  | RegionConfig                        |
| Report/export        | Grading scale   | GradingScaleConfig / RegionConfig   |
| Fee/invoice          | Fee type        | FeeType (school/region)             |
| Admission number     | Strategy/template | SiteSettings or School-level config |

## Admission number config (centralized)

- **SiteSettings:** `admission_number_mode`, `admission_number_strategy`, `admission_number_template`, `admission_number_pattern` (validation regex).
- **School-level override:** When `TenantAdmissionNumberPolicy` (or equivalent) exists for a school, it overrides SiteSettings for that school.
- **Usage:** Admin (student create), API (enrollment/apply), signup flows. All should use the same helper (e.g. `generate_admission_number(school, ...)`) so format is consistent.
- **Template placeholders:** `{year_2digit}`, `{school_code}`, `{seq_4digit}`, `{spec_code}`, `{class_segment}` (see SiteSettings help text).

## Verification

- Test: Create a school with a given admission config (template or strategy), create a student with blank admission number, assert generated number matches the expected pattern (see `tests.test_admission_number_generation` or equivalent).
