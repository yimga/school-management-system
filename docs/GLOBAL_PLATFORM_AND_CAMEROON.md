# Global Platform and Cameroon (Gilead Tenant)

The platform is **global**: one codebase works for any country. Regional behaviour (grading, currency, timezone) is driven by **RegionConfig** and **School.default_region**.

## Cameroon as one region

- **RegionConfig** with `code='CMR'` (Cameroon) has:
  - `grading_scale`: `0-20`
  - `grading_rule`: `{"type": "coefficient", "scale_max": 20}` for coefficient-based report card average
  - `default_currency`: `XAF`
  - `timezone`: `Africa/Douala`
- Any school (including **Gilead**) can use Cameroon by setting **School.default_region** to the CMR region.

## Gilead tenant

- To use Gilead with the **Cameroon** education system:
  1. In Django admin (or data migration), set the Gilead school’s **Default region** to **Cameroon (CMR)**.
  2. Report cards and transcripts will use the coefficient-based average when the region’s `grading_rule.type` is `coefficient`.
- The same platform can host other schools in other countries; each school chooses its own **default_region** (USA, UK, Kenya, etc.).

## Plan addons (global)

- Financial Aid / Higher Ed addons are registered globally: `financial_aid_basic`, `financial_aid_pro`, `endowment_manager`, `degree_audit`, `graduate_research`, `admissions_crm`, `student_success`.
- Enable them per school via **Plan** or **School.addons** so that `is_feature_enabled(school, "admissions_crm")` etc. work.

## Lead Capture API

- `POST /api/admissions/lead/` with JSON: `school_slug`, `first_name`, `last_name`, `email`, optional `lead_source`.
- Resolves school by `school_slug`; creates **Applicant**. Use Gilead’s slug (e.g. `gilead` or your configured slug) to capture leads for that tenant.
