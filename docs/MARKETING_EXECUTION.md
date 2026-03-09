# Marketing — category-defining execution

**Goal:** Marketing is decoupled from app shell; content and footer/header decoupled from product chrome; SEO and performance budgets; optional experimentation.

## Shell and assets

- **Base:** `templates/marketing/base_marketing.html` — loads only design-tokens, tokens-marketing, marketing-shell CSS. No design-system-unified, no dashboard-*, no app-only assets. See docs/SHELL_ARCHITECTURE_MATRIX.md, docs/MARKETING_SHELL_VIEWS.md.
- **Tests:** `apps/platform_runtime/tests/test_marketing_shell.py` — marketing base does not load app-only CSS; control-plane skeleton does not load marketing-only CSS.

## Content and footer/header

- **Content:** Product/pricing/solutions copy may be code-defined or config/CMS; document owner and update process. Move to config or CMS where product wants to edit without code deploy.
- **Footer/header:** Marketing-specific partials; avoid app context (request.school, tenant_runtime) in marketing footer/header unless intentional. Shared partials only where documented.

## SEO and performance

- **SEO:** Add meta title, description, and structured data to all marketing and regional landing pages. Sitemap and robots.txt for public marketing.
- **Performance:** Lazy load below-fold assets; critical CSS for above-fold; optional bundle size budget for marketing JS/CSS (e.g. Lighthouse or CI step).
- **Experimentation:** Optional A/B or feature-flag hook (e.g. experiment_id in template or config) for marketing copy; implement when needed.

## References

- docs/CSS_RATIONALIZATION.md
- docs/SHELL_ARCHITECTURE_MATRIX.md
- docs/MARKETING_SHELL_VIEWS.md
- templates/marketing/base_marketing.html
