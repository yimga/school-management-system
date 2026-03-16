# Responsive & device optimization audit

**Purpose:** Ensure the app is high-end and optimized for all screen/device types. Avoid "mobile view on desktop" (narrow strip) and ensure viewport/layout contracts are consistent.

**Audit date:** 2025-03 (codebase-wide).

---

## 1. Viewport and base templates

| Template | Viewport meta | Notes |
|----------|----------------|--------|
| `templates/base.html` | `width=device-width, initial-scale=1` | ✓ |
| `templates/portal_base.html` | ✓ (included via base or head block) | ✓ |
| `templates/control_plane_skeleton.html` | `width=device-width, initial-scale=1` | ✓ |
| Marketing base | ✓ | ✓ |

**Contract:** Every base/layout that renders a full page must include viewport meta so mobile devices don’t scale down the whole page.

---

## 2. Global CSS breakpoints (source of truth)

- **design-tokens.css:** `--bp-mobile-max: 767px`, `--bp-tablet: 991px`, `--bp-desktop: 1024px`, `--bp-wide: 1440px`, `--bp-extra-narrow: 575px`.
- **design-system-unified.css:** Mobile-first at `479px` / `767px`; desktop at `1024px` / `1440px`. Base styles are mobile; overrides use `min-width` for larger screens.
- **dashboard-responsive.css:** Uses 1600px max for dashboard sections; no narrow-forcing on desktop.

**Contract:** Avoid applying a single small `max-width` (e.g. 480px) to key containers without a `min-width` (e.g. 992px) override so desktop gets a proper width.

---

## 3. Control plane login (manager / admin)

**Issue (fixed):** `control-plane-ultra.css` applied to `body.control-plane-shell` and forced:

- `.cp-login-container` → `max-width: 480px` at **all** viewports  
- `.manager-login-hero` / `.admin-login-hero` → `max-width: 480px` at all viewports  
- `.manager-login-card` / `.admin-login-card` → `max-width: 420px` at all viewports  

That made desktop login look like a narrow mobile strip.

**Fix applied:**

- **control-plane-ultra.css:**  
  - `.cp-login-container`: keep 480px by default; at `min-width: 992px` set `max-width: 560px`.  
  - Hero: `max-width: 100%` by default; at `max-width: 991.98px` cap at 480px.  
  - Login card: keep 420px by default; at `min-width: 992px` set `max-width: 460px` and `min-width: 380px`.
- **manager-login.css:** Already had desktop overrides (720px / 560px container, 440px / 460px card at 992px / 1200px). Specificity: `body.control-plane-shell .cp-login-container` wins for the container; both files now agree on desktop card width.

**Load order:** control_plane_skeleton → control-plane-ultra.css; manager_login.html adds manager-login.css in `extrastyle`. Desktop layout now uses 560px container and 460px card when viewport ≥ 992px.

---

## 4. Tenant login (auth/login.html)

- Desktop block at `min-width: 992px`: `.auth-landing .container` max-width 1140px; hero and cards have min-width and scaling.  
- No global rule forces a narrow strip on desktop.

---

## 5. Portal and marketing

- **portal_base.html:** Uses `platform-fluid-everywhere.css`; layout uses `min-width: 0` and overflow containment.  
- **portal-layout-professional.css:** Sidebar/main scroll contract; breakpoint 992px for row layout.  
- **platform-fluid-everywhere.css:** Fluid containers, no fixed narrow max on body/main.  
- Marketing base: Uses platform-fluid; no desktop narrow-forcing found.

---

## 6. Checklist for future CSS

- [ ] Viewport meta present on any new full-page base template.  
- [ ] No single rule that sets a small `max-width` (e.g. 480px) on a main container without a `min-width: 992px` (or similar) override for desktop.  
- [ ] Prefer mobile-first: base = mobile; use `@media (min-width: …)` for tablet/desktop.  
- [ ] If a "mobile-only" rule is needed, use `@media (max-width: 991.98px)` (or similar) so it doesn’t apply on desktop.

---

## 7. Files touched in this audit

- **static/css/control-plane-ultra.css** – Login container/hero/card made responsive (desktop width at ≥992px).  
- **docs/RESPONSIVE_DEVICE_AUDIT.md** – This document.

No changes to viewport meta were required; all base templates already had it.
