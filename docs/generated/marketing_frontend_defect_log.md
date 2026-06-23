# Marketing frontend conversion defect log

- **Generated:** `2026-06-23T21:44:09Z`
- **Surface:** runmycampus.com public marketing (Django templates + static/marketing/)
- **Wave:** v3.35.3 + v3.37.1 impact + v3.37.2 gear-up — see `docs/CSS_RETIREMENT_DOCKET.md`

## Bundle metrics (post-fix)

- Critical min.css: **21,619** bytes
- Enhanced min.css: **418,174** bytes (deferred)

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
| I1 | high | UX / impact | fixed | Bell timeline + persona tabs showed full-screen dashboards with low narrative impact | Single-panel bell clock + constrained mkt-v3-dashboard-frame--impact + story metric column |
| I2 | high | UX / contrast | fixed | World map labels used #1F2937 on cinematic dark background (illegible / blurred) | mkt-world-map currentColor labels + HTML caption block + marketing-impact.css cinematic tokens |
| I3 | medium | conversion | fixed | Hero lacked live simulated campus dashboard (prompt live-campus pulse) | _hero_live_campus_pulse.html + mkt-live-campus-pulse.js SVG/CSS animations |
| I4 | medium | media | fixed | Walkthrough needed an accessible preview surface without fake video controls | _video_portal.html poster-mode preview + animated walkthrough when footage is absent |
| I5 | medium | IA / lanes | fixed | No short routes or lane-aware chrome accents for academics/admissions/finance | /academics/ /admissions/ /finance/ redirects + mkt-lane-chrome.js + lane tokens in tokens-marketing.css |
| I6 | low | i18n | fixed | Pricing matrix could clip on verbose locales | marketing-impact.css table-layout fixed + overflow-wrap anywhere on mkt-v3-pricing-matrix |
| Q1 | high | Sweep 2 QA | fixed | Responsive impact sections not gated for horizontal scroll on mobile | tests/e2e/marketing-impact-responsive.spec.js + verify_marketing_sweep2.py |
| G1 | high | production proof | fixed | No automated smoke for deployed marketing + lane routes | scripts/verify_marketing_production_smoke.py (PRODUCTION_BASE_URL) + Sweep 2 LCP/CLS when MKT_RUN_SWEEP2_LIVE=1 |
| G2 | high | lane UX | fixed | Academics/admissions/finance lanes shared generic archetype layout | _lane_academics_matrix.html + _lane_admissions_steps.html + _lane_finance_ledger.html + marketing-gear2-lanes.css |
| G3 | high | homepage motion | fixed | Bell and persona sections duplicated; no auto-advance; static globe | _day_role_story.html + data-bell-auto-ms + mkt-globe-tooltips.js + scroll-narrative keyboard/auto |
| G4 | medium | geo | fixed | Hero ignored visitor country; empty _hero_by_country map | apps/schools/marketing_geo.py + _hero_geo_subline.html + country headlines in _marketing_context |
| G5 | medium | conversion | fixed | No illustrative trust strip or ROI proof quote on homepage | marketing_carousel_items logo strip + _proof_quote.html in ROI panel |
| G6 | high | a11y / i18n | fixed | Gear-up a11y/i18n not gated after day|role toggle refactor | marketing-gear2-a11y.spec.js + marketing-pricing-i18n.spec.js + impact-responsive day|role flow |
| G7 | low | architecture | fixed | Risk of parallel Next.js marketing app duplicating Django stack | Explicit Django-only delivery; verify_marketing_gear2_completion.py in audit_marketing_frontend_100 |

## Prompt deliverable mapping

| Deliverable | Repo artifact |
|-------------|---------------|
| 1. Defect log | This file + `.json` sibling |
| 2. Production rewrite | `base_marketing.html`, bundles, theme/hero partials |
| 3. Sweep 2 QA | `tests/e2e/marketing-theme-contrast.spec.js`, `verify_marketing_lighthouse_budget.*` |
| 4. SOT tokens | `static/marketing/css/tokens-marketing.css` |
| 5. Impact layer | `marketing-impact.css`, bell/persona/globe/hero/lane partials + `verify_marketing_impact_layer.py` |
| 6. Gear-up 1–7 | `verify_marketing_gear2_completion.py`, lane/home partials, geo + production smoke |
