# Current SaaS Landing Page Trends — Analysis and RunMyCampus Alignment

**Purpose:** Reference for marketing and product page design. Aligns RunMyCampus marketing with current SaaS landing page trends and documents how the product page and ultra high-end work map to them.

**Sources:** Industry summaries and audits (e.g. dev tool landing pages 2025, SaaS landing trends 2026, product-led storytelling). See links in §4.

---

## 1. Current SaaS landing page trends (summary)

| Trend | Description |
|-------|--------------|
| **Product-led storytelling** | Show outcomes and functionality over abstract feature lists. Headlines communicate specific benefits (“Ship 40% faster”) rather than product categories. Interactive previews, embedded demos, and guided tours in hero or scroll. |
| **Story-driven narratives** | Problem → solution arc; “little narrative moments” that speak to the audience. Visual storytelling above the fold; scroll reveals the story step by step (scrollytelling). |
| **Developer-centric tone** | Clean, minimal layout; “no salesy BS.” Centered composition, strong typography, breathing room. Micro-demos that show real functionality; avoid flashy decoration. |
| **Dark-mode / premium feel** | Dark themes common for dev tools and premium SaaS; scroll-driven dark sections for focus and contrast. |
| **Micro-demos and proof** | High-fidelity micro-demos (not generic screenshots); each frame shows a real capability. Builds trust through transparency. |
| **Outcome-focused copy** | Benefit-driven language; “See examples built for you” outperforms generic “Sign up.” First-person or outcome CTAs. |
| **Personalization** | Dynamic content by referral, segment, or behavior where applicable; benefit-driven CTAs. |
| **Technical quality** | Micro-animations that demonstrate functionality; mobile optimization; social proof near CTAs; strong, clear CTAs. |

---

## 2. RunMyCampus alignment

| Trend | Implementation |
|-------|----------------|
| **Product-led storytelling** | **Product page** (`/product/`): Dedicated template `marketing_product_page.html` with outcome-focused headlines, micro-demo grid (`product_visualization_slides`), Studio OS and Migration sections with sticky visual, and final CTA. **Landing** (`/`): Scroll-storytelling directive (chapters, reveal-on-scroll, progress bar); proof hero and why-switch. |
| **Story-driven / scrollytelling** | **Landing:** `RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md`; `data-chapter`, `.mkt-reveal`, `marketing-landing-scroll.js`. **Product page:** Same reveal + progress; chapters 1–6 (hero, demos, Studio OS, migration, outcomes, capabilities, final CTA). |
| **Developer-centric** | **Product page:** Opinionated minimalism; outcome blocks (Migration, APIs); “Built for operators who ship”; no clutter. **Landing:** Design tokens; developer platform section; product tour and demo links. |
| **Dark-mode** | **Product page:** Dark-first (`--mkt-product-bg`, `--mkt-product-surface`); gradient hero; dark sections. **Landing:** Dark hero and sections; tokens support dark. |
| **Micro-demos** | **Product page:** `mkt-product-demos-grid` with one outcome per card; `product_visualization_slides` (admin, teacher, parent, student, analytics). **Landing:** Product visualization section and slides. |
| **Outcome-focused copy** | **Product page:** “See it work — not just read about it”; “Outcomes, not feature lists”; metrics from `page_extras.metrics`. **Landing:** Outcome metrics, by-the-numbers, why-switch bullets. |
| **Responsive / technical** | **§8.0.6:** Fluid layout, clamp typography, Grid/Flexbox; `platform-fluid-everywhere.css` on all bases. Marketing and product use fluid containers and responsive grids. |

---

## 3. Marketing “ultra high-end” — assets and wiring

Per [MARKETING_FRONT_PLACEHOLDER.md](MARKETING_FRONT_PLACEHOLDER.md):

- **Wiring:** All context keys and template slots are wired; fallbacks exist so the site never breaks.
- **Remaining (content/asset pipeline):** Replace placeholders with final creative where desired:
  - **Hero:** Real hero image/video (env or static); `proof_hero_image_key`, `hero_dashboard_image_url`.
  - **Migration diagram:** `migration_studio_image_url`, `migration_diagram_url`; add images to `static/images/marketing/` or set env.
  - **Ecosystem/control-plane diagram:** `ecosystem_diagram_url`, `control_plane_diagram_url`.
  - **Role preview images:** `role_preview_images` (per-role: principal, teacher, parent, student).
  - **Setup-studio visuals:** `setup_studio_flow_image_url`, `health_score_visual_url`.

When these are added (via env or static), the marketing and product pages will show the **full final look**; until then, intentional fallbacks (e.g. `platform-diagram-marketing.svg`, `hero-placeholder.svg`) keep the experience consistent and premium-feeling.

---

## 4. References (for further reading)

- Dev tool landing pages (2025): centered composition, minimalism, micro-demos, no salesy language.
- SaaS landing trends (2026): story-driven narratives, product-led storytelling, personalization, technical quality.
- Product-led growth: outcome-focused copy, interactive demos, guided tours.

---

*Source: RUNMYCAMPUS §8.0, §8.4; CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL; MARKETING_FRONT_PLACEHOLDER; RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.*
