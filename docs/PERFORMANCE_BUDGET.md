# Performance Budget & CI (2025–2026)

This doc defines **targets** and **optional automation** so the team can keep speed and Core Web Vitals under control without rigid rules. Adjust numbers as your stack and priorities change.

---

## 1. Budget targets (guidance, not hard gates)

| Asset type | Soft target | Rationale |
|------------|-------------|-----------|
| **JS (total, first load)** | ≤ 200 KB (gzipped) | Leaves room for React + Bootstrap + app code; trim or code-split if over. |
| **CSS (total, first load)** | ≤ 80 KB (gzipped) | Multiple sheets (Bootstrap, design-system, themes); consider concatenation or critical CSS later. |
| **LCP** | < 2.5 s | Hero/logo above fold; images with dimensions + priority. |
| **CLS** | < 0.1 | All images have width/height; no layout shifts from late content. |
| **INP** | < 200 ms | Touch targets ≥ 44px; avoid heavy JS on first interaction. |

These are **forward-looking** defaults. Tighten (e.g. 150 KB JS, 50 KB CSS) if you add CI; relax if you’re still consolidating.

---

## 2. How to measure

- **Lighthouse** (Chrome DevTools → Lighthouse): run on a representative page (e.g. portal dashboard, login) for LCP, CLS, INP and overall score.
- **Bundle size**: if you introduce a build step (Vite, Webpack, etc.), use their size reports or [size-limit](https://github.com/ai/size-limit) for JS/CSS.
- **Real User Monitoring (RUM)**: optional; tools like Cloudflare Web Analytics, Vercel Analytics, or Sentry can report LCP/CLS/INP from production.

---

## 3. Optional CI / scripts

You can add these when you’re ready; nothing is required.

### A. Lighthouse CI (Node) — configured

- **Config**: `lighthouserc.js` in project root (LCP &lt; 2.5s, CLS &lt; 0.1, performance/accessibility min scores; upload to temporary-public-storage).
- **Run**: Start dev server (`python manage.py runserver`), then `npm run lighthouse`. Or set `LHCI_COLLECT_URL` (e.g. staging URL) and run the same script.
- In CI, set `CI=1` for 3 runs; otherwise 1 run locally.

### B. Size budget (when you have a JS/CSS build)

- In `package.json`, add a script that runs [size-limit](https://github.com/ai/size-limit) or your bundler’s `--stats` and checks total JS/CSS size.
- Example (conceptual):  
  `"size-check": "size-limit"`  
  with a `.size-limit` config capping JS and CSS.

### C. Image dimensions check (included)

- **Script**: `scripts/check_image_dimensions.py`  
  Scans `templates/` for `<img>` tags missing `width` and `height`; exits 1 if any are found (so you can use it in CI or pre-commit).
- **Run**: `python scripts/check_image_dimensions.py` (from repo root).  
  Optional npm script: `"check:images": "python scripts/check_image_dimensions.py"` in `package.json`.

---

## 4. What we’ve already done

- **Images**: Dimensions and `loading="lazy"` / `decoding="async"` added across portal, reports, profile, footer, etc.; LCP images use `fetchpriority="high"` or `loading="eager"` where appropriate. See `docs/FRONTEND_IMAGE_GUIDELINES.md` for ongoing rules.
- **Fonts**: Inter loaded with `display=swap` (avoids invisible text); `preconnect` to `fonts.googleapis.com` and `fonts.gstatic.com` in portal base. Any future custom `@font-face` should use `font-display: swap`.
- **Layout**: Sticky header, footer accordion on mobile, breakpoint tokens (`--bp-*`) in `design-tokens.css` used in portal_base, responsive-performance, dashboard-responsive, footer.
- **Theme**: Contrast and focus visibility in light/dark; overlay tokens for modals/dropdowns.

---

## 5. Next steps (when you’re ready)

1. Run Lighthouse on staging once per sprint and log LCP/CLS/INP.
2. Add Lighthouse CI or a size check to your pipeline if you want automated gates.
3. If you add a front-end build, introduce a size budget and code-splitting for heavy routes.
4. Consider a single “performance” script in `package.json` (e.g. `npm run perf`) that runs Lighthouse + optional size check for local feedback.

Use this doc as a living checklist: update targets and tools as the product and tooling evolve.
