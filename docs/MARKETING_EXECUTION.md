# Marketing — category-defining execution

**Goal:** Marketing is decoupled from app shell; content and footer/header decoupled from product chrome; SEO and performance budgets; required experimentation (A/B).

## Shell and assets

- **Base:** `templates/marketing/base_marketing.html` — loads only design-tokens, tokens-marketing, marketing-shell CSS. No design-system-unified, no dashboard-*, no app-only assets. See docs/SHELL_ARCHITECTURE_MATRIX.md, docs/MARKETING_SHELL_VIEWS.md.
- **Tests:** `apps/platform_runtime/tests/test_marketing_shell.py` — marketing base does not load app-only CSS; control-plane skeleton does not load marketing-only CSS.

## Content and footer/header

- **Content:** Product/pricing/solutions copy may be code-defined or config/CMS; document owner and update process. Move to config or CMS where product wants to edit without code deploy.
- **Seeding:** Run `python manage.py seed_marketing_cms` (or full `bootstrap_runmycampus_platform`) so `/blog/` and optional **MarketingContent** hero/blog intro are populated. See [MARKETING_SEEDING.md](MARKETING_SEEDING.md).
- **JSON page overrides:** `config/marketing_content/{slug}.json` — validated by `python manage.py validate_marketing_urls` (parse + required keys). Fix failures before release.
- **Footer/header:** Marketing-specific partials; avoid app context (request.school, tenant_runtime) in marketing footer/header unless intentional. Shared partials only where documented.

## Deploy / release checklist (marketing)

- **Validate routes and JSON:** `python manage.py validate_marketing_urls` — resolves key marketing URL names, runs Django `check`, and validates every `config/marketing_content/*.json`. For HTTP smoke on canonical host: `python manage.py validate_marketing_urls --smoke`.
- **Demo / example tenant URLs:** Set `TENANT_EXAMPLE_SLUG` (e.g. `gilead-school`) so marketing links and the “Try demo” CTA resolve; if `MARKETING_DEMO_TENANT_URL` is unset, settings derive `https://{TENANT_EXAMPLE_SLUG}.{MULTI_TENANT_BASE_DOMAIN}/`. Override with explicit `MARKETING_DEMO_TENANT_URL` when needed.
- **Hero and AI asset slots:** Optional `MARKETING_HERO_IMAGE_URL`, `MARKETING_HERO_VIDEO_URL`, `MARKETING_HERO_VIDEO_POSTER_URL`, and per-key `MARKETING_MIGRATION_FLOW_IMAGE_URL` / `MARKETING_SETUP_STUDIO_IMAGE_URL` / `MARKETING_ECOSYSTEM_IMAGE_URL` / `MARKETING_MARKETPLACE_IMAGE_URL` for CDN or PNG/video. When unset, `apps.schools.marketing_ai` serves **static SVG** fallbacks under `static/images/marketing/` (no binary hero assets in-repo required).

## SEO and performance

- **SEO:** Add meta title, description, and structured data to all marketing and regional landing pages. Sitemap and robots.txt for public marketing.
- **Performance:** Lazy load below-fold assets; critical CSS for above-fold; required bundle size budget for marketing JS/CSS (e.g. Lighthouse or CI step).
- **Experimentation:** Session-sticky **`hero_variant`** (`A`/`B`) and **`marketing_cta_variant`** (`default`/`secondary`) are set in `_marketing_context` and exposed on the landing root as `data-marketing-hero-variant`, `data-marketing-cta-variant`, and `data-marketing-experiment` for analytics. **Variant B** appends an extra line to **`hero_ai_line`** (the primary hero subcopy in the template) when CMS did **not** set `landing_hero_ai_line` (override text with **`MARKETING_HERO_VARIANT_B_SUBLINE`**). **Secondary CTA** puts **Book a Demo** before **Start Free Trial** in the hero CTA row. Document experiments in your analytics tool using those attributes.
- **Assets (PNG/video/CDN):** Full env map in [MARKETING_ASSETS.md](MARKETING_ASSETS.md).
- **Regional JSON:** [MARKETING_REGIONAL_JSON.md](MARKETING_REGIONAL_JSON.md) + `config/marketing_content/README.md`.
- **Perf gates:** PR workflow `.github/workflows/marketing-n10-pr.yml` enforces server-side **`/marketing/`** budget (`PERF_BUDGET_STRICT_GATE_ROWS=n10_public`). Lab CWV: `.github/workflows/lighthouse-ci.yml` when repo variable **`LHCI_URL`** is set.

## References

- docs/MARKETING_NON_NEGOTIABLES.md
- docs/MARKETING_SEEDING.md
- docs/CSS_RATIONALIZATION.md
- docs/SHELL_ARCHITECTURE_MATRIX.md
- docs/MARKETING_SHELL_VIEWS.md
- templates/marketing/base_marketing.html
