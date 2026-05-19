# Marketing frontend conversion defect log

- **Generated:** `2026-05-19T02:37:00Z`
- **Surface:** runmycampus.com public marketing (Django templates + static/marketing/)
- **Wave:** v3.35.3 — see `docs/CSS_RETIREMENT_DOCKET.md`

## Bundle metrics (post-fix)

- Critical min.css: **15,789** bytes
- Enhanced min.css: **234,023** bytes (deferred)

## Defect register

| ID | Severity | Category | Status | Finding | Remediation |
|----|----------|----------|--------|---------|-------------|
| P1 | critical | CWV / speed | fixed | 32 synchronous render-blocking stylesheets on every marketing page | marketing-critical.min.css + deferred marketing-enhanced.min.css; 4 blocking links in base_marketing.html |
| P2 | high | CWV / speed | fixed | Blocking Google Fonts CDN without self-hosted preload path | Self-hosted Source Serif 4 WOFF2 + marketing-fonts.css in critical bundle |
| P3 | high | CWV / speed | fixed | Portal-only JS on acquisition traffic (lexicon, friction, launch splash) | Removed from base_marketing.html; hero video JS homepage-only |
| T1 | critical | theme | fixed | Split theme bootstraps caused FOUC and v2 data-theme=system no-op | mkt-theme-bootstrap.js + v3 effective data-theme contract |
| T2 | high | theme / contrast | fixed | Hardcoded colors below AAA on dark marketing chrome | tokens-marketing.css SOT + marketing-accessibility-hardening.css (in critical bundle) + marketing-theme-contrast.spec.js axe critical gate |
| C1 | medium | conversion | fixed | Contact/demo forms lacked inline validation hook | novalidate data-rmc-validate=inline + rmc-form-validation.js |
| S1 | high | SEO | fixed | Duplicate JSON-LD blocks across page templates | Central mkt_structured_data.html in base_marketing.html |
| S2 | medium | SEO | fixed | Missing canonical/OG wiring on some marketing pages | rmc_social_meta.html + canonical_url in base; verify_marketing_seo_shell.py |
| H1 | medium | hero / media | fixed | Hero video referenced but not shipped; MP4 gitignored | hero-home.mp4 + poster + setup_marketing_ci_assets.py + gitignore exceptions |
| B1 | medium | budget | fixed | Original ~40KB critical CSS target not met with full grammar + shell | marketing-critical-path.css + deferred grammar/narrative/full shell in enhanced; critical_max 45000 enforced |

## Prompt deliverable mapping

| Deliverable | Repo artifact |
|-------------|---------------|
| 1. Defect log | This file + `.json` sibling |
| 2. Production rewrite | `base_marketing.html`, bundles, theme/hero partials |
| 3. Sweep 2 QA | `tests/e2e/marketing-theme-contrast.spec.js`, `verify_marketing_lighthouse_budget.*` |
| 4. SOT tokens | `static/marketing/css/tokens-marketing.css` |
