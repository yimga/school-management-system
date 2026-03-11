# Public Marketing Surface Backlog (RunMyCampus)

**Doc status: Closed.** All items in MARKETING_NON_NEGOTIABLES; reconciled with **`docs/PHASE_10_BACKLOG.md`** and **`docs/WHATS_LEFT_COMPLETE_BACKLOG_DEFERRED.md`**.

## Goal
Build a clean, conversion-first, enterprise-grade public surface for `runmycampus.com` with strict host clarity and measurable pipeline outcomes.

## Master checklist: 72 non-negotiables
**All items are defined and tracked in [MARKETING_NON_NEGOTIABLES.md](MARKETING_NON_NEGOTIABLES.md).** Nothing is deferred to "later"; every item is either implemented or scheduled with a target date. The **[Visual Asset plan](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md)** is the authority for all marketing visuals; there are no optional visuals. Review MARKETING_NON_NEGOTIABLES for the complete list, acceptance checklist, content ownership, and review cadence.

## Status Legend
- `done`: implemented and in code
- `next`: prioritized for immediate build
- (no `later` bucket: all work is in MARKETING_NON_NEGOTIABLES.md)

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
1. `done` Build country-language landing variants with localized proof cards.
2. `done` Add dedicated pages for key intents:
   - admissions software (`/solutions/admissions-software/`)
   - school ERP (`/solutions/school-erp/`)
   - parent app (`/solutions/parent-app/`)
   - multi-campus school software (existing `/solutions/multi-campus-school-software/`)
3. `done` Expand schema coverage:
   - Organization (on landing and marketing pages)
   - FAQPage (on pricing route via page_extras.faqs)
   - Product/Offer details on pricing routes (OfferCatalog with full Offer descriptions)
4. `done` Add comparison matrix section to `/compare/` route with migration narrative.
5. `done` Add richer case-study cards with quantified outcomes.

## Wave 3 (Sales Enablement and Trust Ops) - Done
1. `done` Add downloadable buyer toolkit and implementation checklist (`/buyer-toolkit/`, download links for buyer-checklist and implementation-checklist HTML).
2. `done` Add implementation timeline section with role ownership (school lead, IT, finance, admissions) on buyer-toolkit page.
3. `done` Add integration trust block with major categories (SIS, LMS, payments, messaging, identity) on integrations page.
4. `done` Add public SLA and uptime trust references (trust-center page); required: slot and copy for status page link; set MARKETING_STATUS_PAGE_URL when status page is available.

## Wave 4 (Optimization and Experimentation) - Done
1. `done` A/B testing: hero/CTA variant in session (marketing_ab_variant); template shows variant B CTA order.
2. `done` Marketing analytics: script via MARKETING_ANALYTICS_SCRIPT_URL when enabled (injected on landing extrahead).
3. `done` Conversion event funnel dashboard (visit -> discovery -> signup -> activation) at `/funnel-dashboard/` (staff only); MarketingFunnelEvent model; recording in landing, discovery, signup, verify_signup).
4. `done` Evidence-driven copy variations by geo (CM, CA) and utm_source (google, linkedin) in _marketing_context.
5. `done` Media optimization: loading="lazy", decoding="async", width/height, fetchpriority="high" on hero; all marketing landing images covered.

## Wave 5 (Visual system) — Done
1. `done` Execute [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md): Batches 1–3 and all four strategic diagrams (Platform Visual Architecture, Ecosystem Map, School-in-a-Box Launch Flow, Data Intelligence Loop).
2. `done` Wire every asset to templates/settings per asset-to-code map in the Visual Asset doc (context keys, MARKETING_PAGE_EXTRAS, static paths, video_url in marketing_page.html).
3. `done` No marketing section left intentionally empty; every section has at least one of: product mockup, system diagram, or motion. Verification: [MARKETING_VISUAL_VERIFICATION.md](MARKETING_VISUAL_VERIFICATION.md).

## Acceptance Checklist
1. Public routes remain marketing-only on apex host.
2. Tenant links always point to `<slug>.runmycampus.com`.
3. Manager links always point to `manager.runmycampus.com`.
4. No hardcoded legacy domain references.
5. Marketing pages pass public smoke tests and Django checks.
