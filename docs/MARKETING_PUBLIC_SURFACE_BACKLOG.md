# Public Marketing Surface Backlog (RunMyCampus)

## Goal
Build a clean, conversion-first, enterprise-grade public surface for `runmycampus.com` with strict host clarity and measurable pipeline outcomes.

## Status Legend
- `done`: implemented and in code
- `next`: prioritized for immediate build
- `later`: queued after core conversion path is stable

## Wave 1 (Core Conversion) - Priority
1. `done` Hero simplification and segment-first messaging.
2. `done` Strong CTA stack: trial + self-guided flow + school finder + login.
3. `done` Three-surface architecture section (public, tenant, manager).
4. `done` Proof strip + outcome stats + institution trust wall.
5. `done` Admissions conversion pipeline section.
6. `done` Pricing snapshot cards with enterprise white-label path.
7. `done` Compliance and trust controls matrix.
8. `done` Reduce public header noise by disabling weather/context strip for marketing pages.

## Wave 2 (SEO and GTM Depth) - Next
1. `next` Build country-language landing variants with localized proof cards.
2. `next` Add dedicated pages for key intents:
   - admissions software
   - school ERP
   - parent app
   - multi-campus school software
3. `next` Expand schema coverage:
   - Organization
   - FAQPage
   - Product/Offer details on pricing routes
4. `next` Add comparison matrix section to `/compare/` route with migration narrative.
5. `next` Add richer case-study cards with quantified outcomes.

## Wave 3 (Sales Enablement and Trust Ops) - Next
1. `next` Add downloadable buyer toolkit and implementation checklist.
2. `next` Add implementation timeline section with role ownership (school lead, IT, finance, admissions).
3. `next` Add integration trust block with major categories (SIS, LMS, payments, messaging, identity).
4. `next` Add public SLA and uptime trust references from observability stack.

## Wave 4 (Optimization and Experimentation)
1. `done` A/B testing: hero/CTA variant in session (marketing_ab_variant); template shows variant B CTA order.
2. `done` Marketing analytics: optional script via MARKETING_ANALYTICS_SCRIPT_URL (injected on landing extrahead).
3. `later` Add conversion event funnel dashboards (visit -> discovery -> signup -> activation).
4. `later` Add evidence-driven copy variations by geo cluster and acquisition channel.
5. `later` Introduce media optimization and lazy strategy for lighthouse budgets.

## Acceptance Checklist
1. Public routes remain marketing-only on apex host.
2. Tenant links always point to `<slug>.runmycampus.com`.
3. Manager links always point to `manager.runmycampus.com`.
4. No hardcoded legacy domain references.
5. Marketing pages pass public smoke tests and Django checks.
