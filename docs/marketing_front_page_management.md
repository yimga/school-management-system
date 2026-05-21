# Marketing Front Page Management

This document keeps new marketing pages from drifting back into generic page copies.

## Add A Marketing Page

1. Add or update the JSON source in `config/marketing_content/<slug>.json`.
2. Include `label`, `seo_title`, `seo_description`, `headline`, `subheadline`, `schema_type`, and at least three `segments`.
3. Add page-specific `extras` for visuals, role benefits, workflow steps, related links, CTAs, and trust language.
4. Register the route in `config/urls.py`, `config/public_urls.py`, and `config/tenant_urls.py` only when the page is intentionally public on those hosts.
5. Add or extend tests in `apps/schools/tests/`.

## Platform Pages

Platform detail JSON should include `problem_section`, `workflow_steps`, `benefits_by_role`, `related_platform_links`, one visual reference, and SEO title/description.

The canonical public platform routes are `/platform/student-information-system/`, `/platform/admissions/`, `/platform/attendance/`, `/platform/fees-payments/`, `/platform/grading-report-cards/`, `/platform/parent-portal/`, `/platform/teacher-portal/`, `/platform/student-portal/`, `/platform/communications/`, `/platform/analytics/`, `/platform/workflows/`, `/platform/offline-first/`, and `/platform/security/`. Do not redirect these to verb hubs.

## Navigation And Conversion

The global IA is `Platform`, `Solutions`, `Why RunMyCampus`, `Pricing`, `Resources`, `More`, plus the persistent `Book demo` CTA. `More` is utility-only: company, contact, marketplace, developers, status, login, legal, and privacy.

Pricing CTAs must carry `data-plan-name` so plan-interest analytics can be emitted without collecting buyer PII. Demo and contact forms must keep intent controls accessible and route migration, offline, procurement, support, partnership, and developer/integration interest.

## Media

Do not render empty video sources or play buttons unless real footage is available. Poster-only walkthroughs must be labeled as product walkthroughs or animated previews, not videos.

## Visual Assets

Put self-hosted marketing visuals under `static/images/marketing/` and document purpose and page usage in `static/images/marketing/README.md`.

## Analytics

The privacy-safe client layer lives in `static/marketing/js/marketing-analytics.js` and is configured by `MARKETING_ANALYTICS_ENDPOINT_URL`. Keep the event schema aligned with `docs/generated/marketing_analytics_event_contract.md`.

Do not collect PII. Do not add provider keys to source.
