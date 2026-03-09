# Prompt 7 — Global Education Compatibility Audit Report

**Date:** 2026-03-06  
**Scope:** Support for 195 countries — grading, calendar, attendance, compliance, reporting, payment, locale  
**Non-negotiable:** Single-country/region assumptions must be replaced with configurable behavior.

---

## 1. Global education compatibility inventory

| Domain | Current state | Gap |
|--------|----------------|-----|
| Grading | 0-20 scale and Cameroon-style logic in evals/reports; rosetta_stone and grading.py | Hardcoded scale and labels; need grading registry/blueprint per region. |
| Academic calendar | Terms and years per school; get_active_year_and_term(school=...) | Structure is school-scoped; term semantics (semester/trimester) can be extended via blueprint. |
| Attendance / leave | Tenant-scoped models | Logic not tied to single country; leave types could be registry-driven. |
| Compliance / reporting | Report formats and labels; some CMR/XAF in services | Regional formats and regulatory templates should be blueprint/registry-driven. |
| Localization / RTL | i18n and templates | Partial; RTL and locale per tenant to be fully productized. |
| Payment / currency | XAF default in finance, reports, siteconfig | Currency and payment providers must come from tenant runtime and provider registry. |
| Registries / regional config | Geo catalog, education profiles, brand registry | Exist but not yet the single source for all country/region behavior; some code still uses CMR/XAF/Douala. |

---

## 2. Per-domain maturity

| Domain | Maturity (0–10) | Notes |
|--------|------------------|--------|
| Grading | 4 | One scale dominant; registry/blueprint needed for multiple scales. |
| Calendar | 6 | School-scoped years/terms; extensible. |
| Attendance | 5 | Tenant-scoped; leave types could be from registry. |
| Compliance/reporting | 4 | Hardcoded region/currency in places; templates configurable. |
| Localization/RTL | 5 | i18n present; RTL and locale need full support. |
| Payment/currency | 4 | Defaults to XAF; must be tenant + provider registry. |
| Registries/regional | 6 | Geo, education profiles, plans; more behavior must flow from them. |

---

## 3. Refactor map to support 195 countries

1. **Grading:** Introduce grading registry/blueprint; evals and reports resolve scale and labels from tenant blueprint/region.
2. **Currency/payment:** No default currency in code; tenant school settings + provider registry; remove XAF/CMR fallbacks from finance, reports, siteconfig.
3. **Timezone/region:** Default timezone and region from registry/geo catalog; remove Africa/Douala hardcoding.
4. **Reporting/compliance:** Report templates and regulatory formats driven by blueprint/region.
5. **Locale/RTL:** Tenant locale and RTL from settings/blueprint; ensure templates and static support RTL.
6. **Education profiles:** Use education-profiles and system blueprint APIs for levels and school types; remove form/template hardcoding.

---

**Next:** Run Prompt 8 (Architecture-Truth) last for the whole-machine truth pass.
