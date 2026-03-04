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
| Hero: Global features list (Multi-Language, Multi-Currency, etc.) | Content | Add to hero segment copy in template or definitions. |
| Post-enrollment revenue (Events, Online Courses, Alumni) | Done | Section on landing; post_enrollment_revenue in marketing_views. |
| Three key features (AI Co-pilot, Real-time Analytics, Customizable Workflows) | Partial | Align copy in product/features segments. |
| Admissions and enrollment | Partial | Solutions/product copy; ensure admissions_flow in context. |
| What you get (Data Security, 24/7 Support, Customizable Branding) | Partial | security-compliance, product segments. |
| Pricing (Basic, Premium, Enterprise) | Done | /pricing/ page and definition. |
| Compliance and data security | Done | /security-compliance/. |
| How the platform scales globally | Partial | solutions/regional; add scaling segment if needed. |
| Blog / Topics of leading faculties | Done | /blog/, /blog/<slug>/; BlogPost model + admin; CMS-backed. |
| Final CTA + Footer (Privacy, Terms, Made with ❤️) | Done | Footer in marketing_landing.html. |
| Marketing CMS | Done | MarketingContent model (key/locale/content_html); admin. |
| Marketing analytics & A/B testing | Done | MARKETING_ANALYTICS_SCRIPT_URL; hero_variant A/B in session. |
| Public API / Developer Portal | Done | /developers/ page; docs/PUBLIC_API_AND_DEVELOPER_PORTAL.md. |
| Marketing demo environment | Done | MARKETING_DEMO_TENANT_URL; "Try demo" CTA when set. |

## Actions

- Add hero "Global features" bullet list to landing template or MARKETING_PAGE_DEFINITIONS["product"]/home.
- Ensure footer includes Privacy Policy and Terms of Service links.
- Record WCAG/i18n gaps in REPORTS/AUDIT_LOG.md section 6 when running pa11y/Lighthouse.
- Tie to [MARKETING_PUBLIC_SURFACE_BACKLOG.md](MARKETING_PUBLIC_SURFACE_BACKLOG.md) for Wave 4 and CMS/analytics.
