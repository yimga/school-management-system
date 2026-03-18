# Core Web Vitals — RunMyCampus marketing & product

**Targets (Google / B2B best practice):**

| Metric | Target | Notes |
|--------|--------|-------|
| **LCP** | ≤ 2.5s | Hero image: `fetchpriority="high"`, `loading="eager"` on landing; prefer WebP/AVIF; CDN. |
| **INP** | ≤ 200ms | Defer non-critical JS (analytics at end with `defer`); reduce long main-thread tasks. |
| **CLS** | < 0.1 | Reserve space for hero/fonts; explicit width/height on above-the-fold images. |

## Implemented (marketing)

- Third-party **analytics** loads with **`defer`** at end of page (not blocking `async` in `<head>`).
- Hero uses **`fetchpriority="high"`** + **`loading="eager"`** on LCP image; **`rel="preload" as="image"`** when `hero_dashboard_image_url` is set (with optional `imagesrcset`).
- **Below-fold CSS:** `mkt-live-flow.css` loads via **`rel="preload" as="style"`** + `onload` → stylesheet (non-blocking).

## CI / measurement

1. **Local:** `npx lighthouse https://YOUR_MARKETING_URL --only-categories=performance --output=html`
2. **GitHub Actions:** `.github/workflows/lighthouse-ci.yml`
   - **Variable:** Repository → Settings → Secrets and variables → Actions → **Variables** → create **`LHCI_URL`** (full marketing home URL, e.g. `https://tenant.runmycampus.com/`).
   - PRs that touch marketing paths run the workflow when `LHCI_URL` is non-empty; use **Actions → Lighthouse CI → Run workflow** for a manual run.
   - No public URL yet: use a preview deploy or tunnel (ngrok, etc.) and set `LHCI_URL` to that origin.
3. **Optional:** `LHCI_BUILD_TOKEN` if you upload results to a Lighthouse CI server ([docs](https://github.com/GoogleChrome/lighthouse-ci/blob/main/docs/getting-started.md)).

## Budgets (optional CI gate)

Add to `lighthouserc.cjs` under `assert.assertions`: `first-contentful-paint`, `largest-contentful-paint`, `cumulative-layout-shift`.

## Changelog

- 2026-03: Doc + deferred analytics + Lighthouse workflow skeleton.
- 2026-03: `LHCI_URL` setup steps + optional LHCI server token.
