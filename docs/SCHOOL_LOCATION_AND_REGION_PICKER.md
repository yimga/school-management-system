# School location and RegionConfig single picker

**Goal:** One clear, verified way to set school location and region in settings.

## Canonical place

- **School edit (admin):** The primary place to set school location and region is **Django Admin → Schools → School** (or Entity Console school form when enabled).
- **Relevant fields (single source of truth):**
  - `default_region` — FK to `siteconfig.RegionConfig` (region implies country, timezone, currency, grading).
  - `country_code` — ISO country (e.g. CM, GB, US); can be derived from default_region or set explicitly.
  - `subdivision` — Optional FK to subdivision when using GlobalGeoCatalog.
  - `compliance_region` — Optional string for regulatory scope.
  - `timezone` — Can be set from RegionConfig or overridden per school.

## Single picker behavior

- Prefer **one RegionConfig dropdown** for “School region”: selecting a region sets `default_region_id` and can optionally backfill `country_code`, `timezone` from the region (see RegionConfig model).
- If the UI shows both “Country” and “Region”, ensure they stay in sync: e.g. region implies country, or country filters the list of regions.
- **Site customizer (SiteSettings)** holds global/default branding and company details; it does **not** override per-school `School.default_region`. School-level location is on the School model only.

## Where these fields are used

- **Signup/provisioning:** Can set `default_region_id` and `country_code` when creating a school (e.g. from signup form or onboarding).
- **APIs:** Government/aggregate and reporting APIs often scope by school or by `school.default_region`.
- **Reports:** Report templates and locale may use `get_tenant_locale(school)` and region-specific grading.

## Verification

- Run the test: `tests.test_school_region_picker` (or equivalent) that creates a school, sets `default_region`, and asserts `default_region_id` and optionally `country_code`/timezone are set.
- Audit: Search codebase for `default_region`, `country_code`, `compliance_region`, `timezone` on School and ensure only the canonical admin/API paths write them for school location.
