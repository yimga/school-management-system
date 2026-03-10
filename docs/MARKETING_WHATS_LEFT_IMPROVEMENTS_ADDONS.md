# Marketing: What’s Left, Improvements & Add-ons

**Status:** The [Public Marketing Surface Backlog](MARKETING_PUBLIC_SURFACE_BACKLOG.md) **Waves 1–4 are complete;** **Wave 5 (Visual system)** is required per plan. All visual assets are required per [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md). Nothing is left as “next” without a target.

This doc covers: (1) alignment items from the older audit, (2) improvements (image assets and A/B are **required** where they affect visual completeness), (3) add-ons.

**Planned/Implemented:** The *Marketing Improvements, Add-ons and Blueprint Alignment* plan has been executed: Phase 1 (audit alignment), Phase 2 (sticky CTA, Book a demo form/Calendly), Phase 3 (FAQ schema, BreadcrumbList, sitemap priority, image wiring), Phase 4 (preconnect for analytics), Phase 5 (funnel by utm, A/B marketing_cta_variant, Lighthouse/pa11y docs), Phase 6 (geo/channel copy, regional proof), Phase 7 (cookie policy, form→webhook for demo), Phase 8 (docs and blueprint alignment). See [BLUEPRINT_ALIGNMENT.md](BLUEPRINT_ALIGNMENT.md) for external blueprint references.

---

## 1. Additional alignment (from Marketing Page Audit) — required for full 4.11

These items are required for full 4.11 alignment; track in this doc until done. Source: [MARKETING_PAGE_AUDIT.md](MARKETING_PAGE_AUDIT.md).

| Item | Effort | What to do |
|------|--------|------------|
| **Hero: Global features list** | Small | On the new 10-section landing, add a short “Trusted for: Multi-Language, Multi-Currency, …” line under the hero subheadline (reuse `global_features` from context). |
| **Three key features (AI Co-pilot, Real-time Analytics, Customizable Workflows)** | Small | Ensure `/product/` and `/features/` segments or execution_blocks explicitly mention AI Co-pilot, Real-time Analytics, and Customizable Workflows. |
| **Admissions and enrollment** | Done | Already covered by core_modules “Admissions & Enrollment” and platform narrative; no change required. |
| **What you get (Data Security, 24/7 Support, Customizable Branding)** | Done | Covered by security section, badges, and trust copy on landing; security-compliance page exists. |
| **How the platform scales globally** | Small | Add one “Scales globally” bullet or a short line in the migration or solutions section (e.g. “195+ country-ready profiles, multi-currency, data residency”). |

---

## 2. Suggested improvements

### Conversion & UX
- **Sticky CTA on scroll:** Floating “Start Free Trial” or “Book demo” bar after user scrolls past hero (required; implement with JS + CSS).
- **Exit-intent or scroll-based lead capture:** Modal or slide-in for email (e.g. “Get the buyer checklist”) after scroll depth or exit intent; wire to existing lead capture / CRM.
- **Clear “Book a demo” flow:** If `/book-demo/` is only content today, add a form (name, email, school, message) that posts to an endpoint (email or CRM); or embed Calendly/Cal.com link.
- **Social proof refresh:** Replace placeholder trust logos with real partner/school logos (or “As used by X, Y, Z” text) when available; add 1–2 short video testimonials if you have them.

### SEO & discoverability
- **More FAQ schema:** Add `faqs` to other high-intent pages (e.g. product, solutions, why-switch) for FAQPage schema where it makes sense.
- **BreadcrumbList schema:** Add BreadcrumbList JSON-LD on topic and marketing subpages (product, pricing, solutions, etc.) for rich results.
- **Sitemap priority/changefreq:** Differentiate homepage vs. key landing pages in `marketing_sitemap_xml` (e.g. higher priority for `/`, `/pricing/`, `/product/`).
- **Image assets (required):** Add hero, product-demo, and migration studio images per [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md). Use `static/images/marketing/` and set `hero_dashboard_image_url`, `product_visualization_slides`, `migration_studio_image_url` (and other context keys from the Visual Asset doc) in context or settings. No optional migration studio image—all listed assets are required.

### Performance & Core Web Vitals
- **Preconnect / prefetch:** For critical third-party origins (analytics, fonts), add `<link rel="preconnect">` or `dns-prefetch` in marketing base or landing `extrahead`.
- **Critical CSS:** Inline above-the-fold styles for hero (or use a small critical CSS build) to improve LCP where needed.
- **Image format:** Serve WebP/AVIF with fallback for hero and product images (e.g. via `picture` + `source`).

### Analytics & optimization
- **Funnel by channel:** Extend funnel dashboard (or analytics) to break down visit/discovery/signup/activation by `utm_source` / `utm_medium` (store in MarketingFunnelEvent or in your analytics tool).
- **More A/B levers (required for ongoing optimization):** Use `hero_variant` (or new flags) to test alternate headlines, CTA copy, or CTA order beyond the current A/B; document variant flags and target in marketing docs.
- **Lighthouse / pa11y in CI:** Add a step in CI to run Lighthouse or pa11y on `/` and key marketing URLs and fail or warn on regressions (see audit note in MARKETING_PAGE_AUDIT.md).

### Content & localization
- **More geo/channel copy:** Extend `_hero_by_country` and `_hero_by_channel` to more countries and utm_sources (e.g. facebook, newsletter) for evidence-driven copy.
- **More regional proof:** Add more entries to `_proof_by_country` (and testimonials by region where available) for regional landings.
- **Blog and resources:** Keep publishing blog posts and, if useful, “Resources” or “Guides” (e.g. “How to evaluate school management software”) to support SEO and nurture.

---

## 3. Suggested add-ons

### Scheduling & demo
- **Calendly / Cal.com / similar:** Embed or link from “Book a demo” so visitors can pick a slot; server-side sync (e.g. webhook) to create a lead in your CRM or internal tool.
- **Demo environment:** You already have `MARKETING_DEMO_TENANT_URL`; add the required block (MARKETING_DEMO_WHAT_YOU_SEE; implemented. See “What you’ll see” in marketing_page.html.)

### Trust & operations
- **Public status page:** If you run one (e.g. status.runmycampus.com), set `MARKETING_STATUS_PAGE_URL` in settings so the trust-center SLA block can link to it.
- **Certifications / badges:** When you have SOC 2, ISO, or similar, add them to the security/trust section and, if useful, as image badges with alt text.
- **Legal pages:** Ensure Privacy and Terms are complete and linked from footer (already linked); add Cookie policy if you use non-essential cookies.

### Lead capture & CRM
- **Form → CRM/email:** Ensure contact, book-demo, or “Get the checklist” forms post to your CRM or email (e.g. Zapier, Make, or custom endpoint).
- **Lead scoring:** When more fields exist (school size, country, role), score leads and route them (e.g. enterprise vs. SMB).

### Content & tools
- **ROI / savings calculator:** Simple “See how much time you save with RunMyCampus” calculator (e.g. hours per term) as a micro-tool on product or pricing.
- **Comparison PDF:** One-pager “RunMyCampus vs. spreadsheets / legacy SIS” as a downloadable PDF (or HTML like the buyer checklist) for sales enablement.
- **Interactive product tour:** Required “Click through the platform” tour (e.g. Product Fruits, Navattic, or custom) linked from product or demo section.

### Technical
- **PDF export for checklists:** Server-side PDF generation (e.g. WeasyPrint, reportlab) for buyer and implementation checklists so “Download PDF” returns a real PDF instead of HTML.
- **Newsletter signup:** Required “Subscribe to product updates” form that writes to your email tool or a simple list; link from footer or Resources.
- **Chat widget:** Live chat or chatbot (e.g. Intercom, Crisp, or custom) on marketing pages for high-intent visitors.

---

## 4. Visual asset execution (required)

All assets in [RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md](RunMyCampus_Marketing_Visual_Asset_and_AI_Prompt_Pack.md) are **required**. Execution order: Batch 1 → Batch 2 → Batch 3 + four strategic diagrams. Verification: use [MARKETING_VISUAL_VERIFICATION.md](MARKETING_VISUAL_VERIFICATION.md) (or the checklist in SWEEP_VERIFICATION_COMPLETE) so every asset has a "Verified in" path; no row left TBD without an owner and target date. See also [MARKETING_PUBLIC_SURFACE_BACKLOG.md](MARKETING_PUBLIC_SURFACE_BACKLOG.md) Wave 5.

---

## 5. Summary

- **Backlog:** Waves 1–4 are **complete**; Wave 5 (Visual system) is **required**; nothing left as “next” without a target.
- **Visual assets:** All assets in the Visual Asset doc are required; image assets and A/B levers are required per plan; verification via Marketing Visual Verification checklist.
- **Improvements:** Focus on conversion (sticky CTA, demo form, social proof), SEO (FAQ/breadcrumb schema, sitemap, images), performance (preconnect, critical CSS, image formats), and analytics (funnel by channel, more A/B with documented variant flags).
- **Add-ons:** Most impact from demo booking (Calendly/Cal.com), status page link, form→CRM, and real images; then ROI calculator, comparison PDF, chat, newsletter, and PDF export.

Use this doc as a living list: tick items when done and add new ideas as you run experiments or get feedback.
