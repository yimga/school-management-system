# Website / Competitor Import — Implemented (Non-Negotiable)

**Status:** Implemented.  
**Strategy Report:** Phase 2 — "School provides existing website URL or competitor URL → platform grabs logo, colors, key content."

---

## Scope

- **Input:** School provides a URL (their current website or a competitor’s).
- **Output:** Platform (or assisted tool) extracts where possible: logo, primary/accent colors, key text (school name, tagline).
- **Consent:** Explicit consent and privacy notice before any fetch.
- **Fallback:** When fetch fails or returns nothing useful, fall back to manual upload and color picker (existing flow).

---

## Implementation (completed)

- **Backend:** `apps/siteconfig/brand_import.py` — `fetch_and_parse_brand_url(url)` fetches HTML, parses `<meta theme-color>`, `og:image`, `og:title` / `<title>`, returns `primary_color`, `logo_url`, `site_name`.
- **Public API:** `apps/schools/signup_views.brand_import_api` — POST `/api/brand-import/` with `url` + `consent`; rate limit 10/h by IP; returns JSON.
- **Theme & Experience:** Form "Import from your website" POSTs to `siteconfig:brand_import_from_url`; applies `primary_color` and `site_name` to SiteSettings.
- **Onboarding step 3:** Same flow; result stored in session (`onboarding_import_*`); shown as "We found: ...".

---

## Implementation options (to be decided by owner)

1. **Backend scraper:** Server-side fetch of URL; parse HTML for `<meta>` theme-color, og:image, title; optional favicon/logo detection. No headless browser required for v1.
2. **Third-party API:** Use a licensed or partner API for brand extraction if available.
3. **Browser extension or client-side:** User pastes URL; client fetches (CORS permitting) or backend proxy; same parsing as (1).

---

## Where it appears in product

- Onboarding wizard, step 3 (branding): "Import from your website" form; fetch stores result in session.
- Theme & Experience: "Import from your website" card; fetch and apply updates SiteSettings.

---

## Non-negotiable

Implemented; consent and fallback (manual upload) as specified. No backlog.
