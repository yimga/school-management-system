# Marketing page & public site audit (Part 4.11 / 4.13)

Alignment of the internet-facing marketing page with the full design in RUNMYCAMPUS_SINGLE_PLAN_COMPLETE.

## Current state

- **Code:** [apps/schools/marketing_views.py](../apps/schools/marketing_views.py), [templates/schools/marketing_landing.html](../templates/schools/marketing_landing.html), [config/public_urls.py](../config/public_urls.py).
- **Nav (from MARKETING_PAGE_DEFINITIONS):** Product, Solutions, Pricing, Compare, Case Studies, Security, Integrations, Book Demo, **About**, **Features**, **Blog**, **Contact**.
- **Routes:** `/`, `/product/`, `/solutions/`, `/pricing/`, `/compare/`, `/case-studies/`, `/security-compliance/`, `/integrations/`, `/book-demo/`, `/about/`, `/features/`, `/blog/`, `/contact/`.
- **School discovery:** `/discover/`, `/find/` (global_login_discovery, find_school) → tenant subdomain login.

## Plan section vs status

| Section (plan 4.11) | Status | Notes |
|---------------------|--------|--------|
| Header / Nav: About, Features, Blog, Contact | Done | In definitions and public_urls. |
| Hero: Global features list (Multi-Language, Multi-Currency, etc.) | Done | "Trusted for:" line using global_features in marketing_landing.html (Phase 1). |
| Post-enrollment revenue (Events, Online Courses, Alumni) | Done | **`post_enrollment_revenue`** + **#post-enrollment-revenue** section on **`marketing_landing.html`**; same pytest as admissions / what-you-get. |
| Three key features (AI Co-pilot, Real-time Analytics, Customizable Workflows) | Done | product/features segments and product FAQs in MARKETING_PAGE_EXTRAS (Phase 1). |
| Admissions and enrollment | Done | **`admissions_flow`** in **`_marketing_context`** + **#admissions-pipeline** on **`marketing_landing.html`** (steps rendered); **`test_landing_renders_admissions_flow_post_enrollment_and_what_you_get`**. |
| What you get (Data Security, 24/7 Support, Customizable Branding) | Done | **`what_you_get`** trio in **`marketing_views`** + **#what-you-get** section before security; compliance detail remains in **`trust_controls`** / **#security-compliance**. |
| How the platform scales globally | Done | Migration section lead includes "195+ country-ready profiles, multi-currency, and data residency options" (Phase 1). |
| Pricing (Basic, Premium, Enterprise) | Done | /pricing/ page and definition. |
| Compliance and data security | Done | /security-compliance/. |
| Blog / Topics of leading faculties | Done | /blog/, /blog/<slug>/; BlogPost model + admin; CMS-backed. |
| Final CTA + Footer (Privacy, Terms, Cookie Policy, Made with ❤️) | Done | Footer in marketing_landing.html; Cookie Policy link added. |
| Marketing CMS | Done | MarketingContent model (key/locale/content_html); admin. |
| Marketing analytics & A/B testing | Done | MARKETING_ANALYTICS_SCRIPT_URL; hero_variant and marketing_cta_variant A/B in session; funnel by utm. |
| Public API / Developer Portal | Done | /developers/ page; docs/PUBLIC_API_AND_DEVELOPER_PORTAL.md. |
| Marketing demo environment | Done | MARKETING_DEMO_TENANT_URL; "Try demo" CTA when set. |

**Waves 1–4 and the Marketing Improvements/Add-ons plan are implemented.** Lighthouse/pa11y for marketing URLs: see [qa.md](qa.md#marketing-site-lighthouse--pa11y-public-urls).

## Actions

- ~~Add hero "Global features" bullet list~~ — Done: "Trusted for:" + global_features in landing.
- Footer includes Privacy Policy, Terms of Service, and Cookie Policy links.
- Record WCAG/i18n gaps in REPORTS/AUDIT_LOG.md section 6 when running pa11y/Lighthouse; CI step documented in [qa.md](qa.md).
- Tie to [MARKETING_PUBLIC_SURFACE_BACKLOG.md](MARKETING_PUBLIC_SURFACE_BACKLOG.md) and [MARKETING_WHATS_LEFT_IMPROVEMENTS_ADDONS.md](MARKETING_WHATS_LEFT_IMPROVEMENTS_ADDONS.md).
