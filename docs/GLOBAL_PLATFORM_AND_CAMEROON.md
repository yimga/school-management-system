# Global Reach and Multi-Region Platform

**The platform is built for global reach.** One codebase serves schools in any country or region. Regional behaviour (grading, currency, timezone, curricula, report templates) is driven by **RegionConfig** and **School.default_region**. Cameroon (CMR) is one of many supported regions—not the default focus.

## No single country, region, currency, or language

- **Country / region:** The platform does not assume or favour one country. Schools choose their region (CMR, USA, GBR, KEN, NGA, etc.); deployment defaults use `REGION_CODE` or `PLATFORM_DEFAULT_REGION_CODE` in `.env`, not a hardcoded single region.
- **Currency:** All currency display and tolerance use the **tenant’s or region’s currency** (XAF, USD, EUR, GBP, KES, NGN, etc.). No single-currency assumption in copy, help text, or defaults.
- **Language:** Default language is region- or tenant-driven (`RegionConfig.default_language`, site settings). Multiple languages are supported; no single-language lock-in.
- **Copy and UI:** Messaging and placeholders say “region”, “country or region”, “tenant’s currency”, and “worldwide” where appropriate—never implying one country, region, currency, or language only.

## Global-first design

- **No single-country default:** Use `REGION_CODE`, `PLATFORM_DEFAULT_REGION_CODE`, and `PLATFORM_DEFAULT_CURRENCY` in `.env` for deployment defaults. Platform-neutral fallbacks (e.g. USD, 0–100 scale, UTC) apply when no tenant/region context exists.
- **Multi-region:** Schools choose their **default_region** (CMR, USA, GBR, KEN, NGA, etc.). Grading scales, currencies, date formats, and report templates follow that region.
- **Registries and seeds:** Blueprint packs, policy bundles, and finance profiles include both regional (e.g. Cameroon Francophone/Anglophone, UK GCSE, US K-12) and generic/global options.

## Cameroon as one supported region

- **RegionConfig** with `code='CMR'` (Cameroon) provides:
  - `grading_scale`: `0-20`
  - `grading_rule`: `{"type": "coefficient", "scale_max": 20}` for coefficient-based report card average
  - `default_currency`: `XAF`
  - `timezone`: `Africa/Douala`
- Any school can use Cameroon by setting **School.default_region** to the CMR region. The same platform hosts schools in other countries; each school chooses its own **default_region**.

## Gilead or any tenant

- To use a tenant with the **Cameroon** education system: set that school’s **Default region** to **Cameroon (CMR)** in admin or via data migration. Report cards and transcripts then use the region’s grading and templates.
- For other countries: set **Default region** to the appropriate RegionConfig (USA, UK, Kenya, etc.). The platform does not assume one country.

## Plan addons (global)

- Financial Aid / Higher Ed addons are registered globally: `financial_aid_basic`, `financial_aid_pro`, `endowment_manager`, `degree_audit`, `graduate_research`, `admissions_crm`, `student_success`.
- Enable them per school via **Plan** or **School.addons** so that `is_feature_enabled(school, "admissions_crm")` etc. work.

## Lead Capture API

- `POST /api/admissions/lead/` with JSON: `school_slug`, `first_name`, `last_name`, `email`, optional `lead_source`.
- Resolves school by `school_slug`; creates **Applicant**. Use the tenant’s slug to capture leads for that school.
