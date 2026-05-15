# Optimization Plan: Responsive Design, Performance & Theme Visibility

**References:** [Responsive & performance (2025–2026)](https://share.google/aimode/y6U4EKw2ZHTNZ5yub), [Light/Dark theme optimization](https://share.google/aimode/knNwhtWkY3gsFS4e9)

---

## Scan Summary (Post–Code Review)

After scanning portal, admin, backend bases, static CSS, and key dashboards:

| Area | Status | Notes |
|------|--------|--------|
| **Viewport** | ✅ | `width=device-width, initial-scale=1` in portal_base, base, emails |
| **Design tokens** | ✅ | `design-tokens.css`: fluid typography (`clamp`), breakpoints, **semantic portal vars** (--portal-text, --portal-text-muted, --portal-border, --portal-nav-pill, shadows) |
| **Responsive CSS** | ✅ | `dashboard-responsive.css`, `responsive-performance.css`, container queries, touch targets 44px, reduced motion |
| **Theme** | ✅ | Portal: `data-bs-theme` (light/dark/system); inline script sets before first paint; `prefers-color-scheme` listener |
| **Theme toggle** | ✅ | Light → Dark → System; `localStorage` key `theme`; icon and title update |
| **Skip link** | ✅ | `.skip-link-theme` – light default, dark override; visible in both themes |
| **Focus states** | ✅ | `:focus-visible` high-contrast in `portal-theme-modes.css`; `--focus-ring-color` in design-tokens |
| **Text & overlays** | ✅ | Body/text use `var(--portal-text)`; sidebar and widget titles use `--portal-text-muted`, `--portal-nav-pill`; dark overrides set semantic vars in `html[data-bs-theme="dark"]` |
| **Dropdown / cards** | ✅ | Dropdown and card box-shadow/border use `--portal-shadow`, `--portal-border-strong`; dark mode vars override |
| **Images** | Partial | Logo: width/height, `fetchpriority="high"`, `decoding="async"`; KB/article and footer use `loading="lazy"`; no `srcset`/WebP yet |
| **Scripts** | Partial | Bootstrap + React at end of body; no `defer` on optional widgets; no formal performance budget |

---

## 1. Responsive Design (Mobile-First & Fluid)

### 1.1 In place
- **Fluid typography:** `design-tokens.css`: `--text-xs` … `--text-3xl` with `clamp()`
- **Content-based breakpoints:** `--bp-narrow` (360px) … `--bp-max` (1280px)
- **Fluid containers:** `responsive-performance.css`: `clamp(0.75rem, 2vw, 1.5rem)` padding
- **Container queries:** Sidebar and cards use `container-type: inline-size` where supported
- **Touch targets:** `min-height/min-width: 44px` for buttons/links on `pointer: coarse`
- **Reduced motion:** `prefers-reduced-motion: reduce` respected
- **Breakpoints in templates:** portal_base uses 479px, 767px, 575px, 1023px, 768px; design-system-unified uses 360px, 767px, 768px, 1024px, 1440px

### 1.2 Optional next steps
- [ ] Use design-token breakpoint variables in media queries where practical (e.g. `var(--bp-content-md)`) for consistency
- [ ] Apply fluid typography classes (e.g. `var(--text-hero)`) on hero/headings where still fixed
- [ ] Ensure `font-display: swap` for any custom webfonts (Bootstrap Icons / CDN typically handle this)

---

## 2. Performance (LCP, CLS, INP)

### 2.1 In place
- **CLS:** Logo and brand images have explicit `width`/`height`; `responsive-performance.css` reserves space for `.brand-logo`
- **Above-the-fold:** Header logo has `fetchpriority="high"` and `decoding="async"`
- **Below-the-fold:** KB article images, dashboard footer logos use `loading="lazy"` and dimensions where applicable
- **INP:** Touch targets 44px; reduce motion respected

### 2.2 Optional next steps
- [ ] Add `loading="lazy"` to profile photos in list/card contexts (e.g. teacher dashboard avatar when below fold)
- [ ] Prefer WebP/AVIF from backend or CDN; use `<picture>` or content negotiation
- [ ] Optional `srcset` for logo/hero if multiple resolutions are served
- [ ] Defer non-critical JS (e.g. React/TanStack) only if no first-paint dependency
- [ ] Minification in production (ManifestStaticFilesStorage or pipeline)
- [ ] **Performance budget:** Document targets (e.g. LCP < 2.5s, CLS < 0.1, INP < 200ms) and add Lighthouse to smoke-test steps

---

## 3. Theme Visibility (Light, Dark, System)

### 3.1 Principles (from references)
- Avoid pure black/white in dark mode; use dark gray and off-white
- Desaturate accents in dark to reduce glare
- WCAG contrast: 4.5:1 normal text, 3:1 large text
- Shadows on light → use borders or lighter borders in dark
- Focus outline high-contrast in both themes
- User toggle + `localStorage` with fallback to `prefers-color-scheme`

### 3.2 Implemented (this pass)
- **Semantic CSS variables:** `design-tokens.css` defines light defaults: `--portal-text`, `--portal-text-muted`, `--portal-border`, `--portal-border-strong`, `--portal-shadow`, `--portal-shadow-hover`, `--portal-nav-pill`, `--portal-nav-pill-hover`, `--portal-nav-pill-bg-hover`, `--portal-nav-pill-bg-active`
- **Dark overrides:** `portal-theme-modes.css` sets all of the above under `html[data-bs-theme="dark"]` so text, borders, shadows, and nav pills are readable and consistent
- **Body color:** Uses `var(--portal-text, #111827)`; dark override in theme-modes
- **Widget title / stat labels:** `.widget-title`, `.dashboard-stat-label`, summary tiles use `var(--portal-text-muted)`; dashboard stats block uses class `dashboard-stat-label`
- **Sidebar:** `portal_sidebar.html` uses `var(--portal-text-muted)`, `var(--portal-nav-pill)`, `var(--portal-border)`, `var(--portal-nav-pill-bg-hover)` etc.; dark theme overrides ensure visibility
- **Cards & dropdowns:** Card box-shadow and dropdown border use `var(--portal-shadow)` and `var(--portal-border-strong)`; dark vars provide appropriate contrast
- **Skip link, focus ring, dropdown items:** Already theme-aware; focus ring and skip link styled for both themes

### 3.3 Optional next steps
- [ ] Audit admin and backend bases for any hardcoded text/overlay colors and align with tokens or theme-specific overrides
- [ ] Run WAVE or axe in both light and dark; fix any contrast issues
- [ ] Test with “Emulate CSS media feature prefers-color-scheme” in DevTools

---

## 4. Implementation Checklist (Prioritized)

### Phase A – Done ✅
1. Theme toggle: Light / dark / **system**; `localStorage`; inline script sets `data-bs-theme` before first paint; `prefers-color-scheme` listener
2. Skip link: `.skip-link-theme` – visible and focusable in both themes
3. Focus ring: High-contrast `:focus-visible` in portal-theme-modes; `--focus-ring-color` in design-tokens
4. Semantic portal variables: `--portal-text`, `--portal-text-muted`, `--portal-border`, shadows, nav-pill colors in design-tokens; dark overrides in portal-theme-modes
5. Body, widget title, dashboard stat labels, sidebar nav/section text: Use CSS variables so light/dark both readable
6. Cards and dropdowns: Theme-aware shadow and border via variables
7. Sidebar partial: Borders, section titles, nav pills, stat labels use variables
8. Header logos: `decoding="async"`; dimensions and `fetchpriority="high"` for LCP/CLS

### Phase B – Performance (optional)
- Add `loading="lazy"` to below-the-fold images (profile lists, report thumbnails)
- Ensure every layout-affecting `<img>` has `width` and `height` (or aspect-ratio)
- Document LCP/CLS/INP targets and add Lighthouse to `docs/SMOKE_TEST_STEPS.md`
- Consider WebP/AVIF and `srcset` for key images

### Phase C – Consistency (optional)
- Replace any remaining hardcoded colors in admin/backend with design tokens or theme overrides
- Use design-token breakpoints in media queries where it improves maintainability
- Optional: Single design-token file or shared layer for admin/backend/portal

---

## 5. Files Touched (This Pass)

- **`static/css/design-tokens.css`** – Added `--portal-border`, `--portal-border-strong`, `--portal-shadow`, `--portal-shadow-hover`, `--portal-nav-pill`, `--portal-nav-pill-hover`, `--portal-nav-pill-bg-hover`, `--portal-nav-pill-bg-active`
- **`static/css/portal-theme-modes.css`** – Dark semantic variable block; sidebar border overrides; `.widget-title`, `.dashboard-stat-label` use `var(--portal-text-muted)`; nav-pill vars in dark
- **`templates/portal_base.html`** – Body color `var(--portal-text)`; `.widget-title` and card/dropdown use vars; dashboard stat label class `dashboard-stat-label`; logo `decoding="async"`
- **`templates/partials/portal_sidebar.html`** – Sidebar borders, section title, info text, nav-pill, stat-label use CSS variables

---

## 6. Testing

- **Responsive:** Resize viewport 320px → 1280px; check portal, backend, admin dashboards on key pages
- **Theme:** Toggle light / dark / system; verify skip link, focus ring, dropdowns, cards, sidebar, widget titles, stat labels, and all text readable
- **Accessibility:** WAVE or axe; contrast in both modes; keyboard nav and focus visibility
- **Performance:** Lighthouse (LCP, CLS, INP) on a representative dashboard page; optional real-device testing (e.g. BrowserStack)

---

## 7. Summary Checklist (2025–2026)

| Feature | Best practice | Status |
|---------|----------------|--------|
| Design | Mobile-first, fluid grids, Flexbox/Grid | ✅ |
| Typography | `clamp()` / fluid, design tokens | ✅ |
| Theme | CSS variables, light/dark/system, no pure black/white in dark | ✅ |
| Text & overlays | Semantic vars, visible in all theme states | ✅ |
| Images | Dimensions (CLS), `fetchpriority`/`loading`, optional WebP/`srcset` | Partial |
| Code | Minification in prod, optional code splitting | Partial |
| Caching | Browser + CDN (deploy-dependent) | Deploy |
| Testing | Lighthouse, contrast, keyboard, optional device cloud | Doc’d |
