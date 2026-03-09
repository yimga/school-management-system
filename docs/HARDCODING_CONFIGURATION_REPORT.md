# Prompt 4 — Platform Configuration vs Hardcoding Audit Report

**Date:** 2026-03-06  
**Scope:** Hardcoded behavior vs registries, blueprints, policy, runtime  
**Non-negotiable:** Hardcoding must be moved to the correct configuration layer.

---

## 1. Hardcoding inventory

| Location | Hardcoded value / behavior | Correct layer |
|----------|----------------------------|---------------|
| apps/finance (tasks, models, services) | CMR, XAF, country/currency defaults | Registry / tenant runtime / blueprint |
| apps/reports/services.py | REGION_CODE "CMR", default_currency "XAF", grading "0-20" | Registry / blueprint / policy |
| apps/evals (models, grading.py, rosetta_stone.py) | "0-20", "XAF", "Cameroon" in help text and defaults | Blueprint / registry |
| apps/schools/signup_views.py | DEFAULT_SCHOOL_TIMEZONE "Africa/Douala" | Registry / geo catalog |
| apps/siteconfig/context_processors.py | REGION_CODE "CMR", default_currency "XAF" | Runtime / registry |
| apps/schools/super_views.py | header_weather_country_code default "CMR" | Env / registry |
| Forms/templates | School types, education levels, grading labels | Registry / blueprint |
| Sidebar / dashboard | Some entries hardcoded | SIDEBAR_DASHBOARD_REGISTRY_TARGET.md; dashboard/sidebar packs |
| Provider integrations | Some provider-specific logic in code | Provider registry + tenant runtime |

---

## 2. Configuration refactor map

| Category | Target | Action |
|----------|--------|--------|
| Country/region/currency | Brand/geo registry, tenant runtime | Replace CMR/XAF/Africa/Douala fallbacks with registry or env; use tenant school settings for currency/timezone. |
| Grading system | Blueprint / policy / registry | Move 0-20 and scale names to blueprint or grading registry; evals use runtime resolution. |
| School types / education levels | Registry / blueprint | Already partially in registries; remove remaining form/template hardcoding. |
| Sidebar / dashboard widgets | Dashboard packs, sidebar registry | Follow SIDEBAR_DASHBOARD_REGISTRY_TARGET.md; drive from packs and runtime. |
| Workflows | Workflow packs | Move stage names and flows to workflow packs. |
| Feature visibility | Runtime / feature flags | Use get_effective_site_settings / tenant runtime for feature toggles. |

---

## 3. Severity and order

- **P1:** ~~Currency/region/timezone in tenant apps~~ **Done (2026-03-06):** Platform defaults added (config.PLATFORM_DEFAULT_*); get_platform_defaults() in platform_runtime.helpers; finance, reports, siteconfig, signup, super_views, academics, api, schools.models use registry/settings fallbacks (no hardcoded CMR/XAF/Africa/Douala/0-20).
- **P2:** Grading and report defaults — siteconfig/views grading fallback uses get_platform_defaults()["grading_scale"]; reports/services uses same.
- **P2:** Sidebar/dashboard hardcoding — consistency and governance.
- **P3:** Control-plane defaults — super_views weather country uses get_platform_defaults()["region_code"].

---

**Next:** Proceed to Prompt 5 (Superadmin Platform Governance).
