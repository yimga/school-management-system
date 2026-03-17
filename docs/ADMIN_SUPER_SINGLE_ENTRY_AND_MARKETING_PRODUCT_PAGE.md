# Admin/Super Single Entry & Marketing Product Page — Plan vs Current State

**Purpose:** Clarify what the plan says about (1) merging manager entry so `/admin/` and `/super/` behave like Salesforce/Shopify/AWS (one control plane, one sign-in), and (2) the marketing product page: product-led storytelling, micro-demos, scroll-driven dark-mode, outcome-focused copy. This doc is the single reference for “what we agreed” and “how to close the gap.”

**Source of truth:** [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0, [NORTH_STAR_PLATFORM.md](NORTH_STAR_PLATFORM.md), [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md), [SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md](SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md), [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md).

---

## 1. Admin + Super: One Entry (Salesforce / Shopify / AWS model)

### What the plan says

- **North Star:** “Salesforce of schools: … **single control plane** for districts and networks.” “Amazon/AWS of school management: … **clear operational surfaces** (Control Plane, School registry, health, usage).”
- **SOT §8.0.1:** “**One shell:** All authenticated surfaces (`/studio/*`, `/admin/*`, `/super/*`, …) must render inside **one unified** AppShell/StudioShell.”
- **SOT §8.0.2:** “`/admin`: Short-term: apply shared shell wrapper. Medium-term: migrate high-value admin workflows into Studio OS / Control Studio.” “`/studio/control/`, `/admin`, and `/super/` must resolve to the **same design tokens and shell**.”
- **CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §2:** “Every page under manage.runmycampus.com … must render inside **one** base shell: same top bar, **one** left sidebar.”

So the plan is: **one control plane, one shell, one sign-in experience** — not two separate “products” at `/admin/` and `/super/`.

### How we’re closing the gap

1. **Single sign-in URL (implemented)**  
   On the **manager host**, unauthenticated requests to `/admin/` (or any path under `/admin/`) now **redirect to `/super/`**. So:
   - **One entry URL:** `https://manager.runmycampus.com/super/`
   - Visiting `https://manager.runmycampus.com/admin/` while logged out sends you to `/super/`, then to the same login; after login you land in the control plane. “Configuration Engine” in the nav still goes to `/admin/` (Django admin) inside the same shell (admin_nav_bridge).
   - **Implementation:** `ManagerHostControlPlaneRequiredMiddleware`: if `path.startswith("/admin")` and user not authenticated → `redirect(reverse("super:dashboard"))`.

2. **One shell (already in place)**  
   When authenticated on the manager host:
   - `/super/*` uses `control_plane_base` (dark bar, one sidebar).
   - `/admin/*` uses Django admin wrapped with `admin_nav_bridge` (same top bar and nav as control plane). So both live under the same visual shell.

3. **Optional next steps**  
   - Add a single “Manager” or “Control plane” entry in marketing/help (e.g. “Sign in at manager.runmycampus.com/super/” only; no separate “Admin” link).
   - Medium-term: move more admin workflows into Studio OS / Control Studio per §8.0.2.

---

## 2. Marketing product page — product-led storytelling, micro-demos, scroll-driven dark mode

### What the plan says

From [SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md](SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md) and the scroll directive:

- **Product-led storytelling:** Show **outcomes and functionality** over abstract feature lists; headlines = specific benefits; **high-fidelity micro-demos** and scroll-driven narrative.
- **Design:** **Opinionated visual minimalism**; **outcome-focused copy**; **developer-centric** tone; “no salesy BS.”
- **Dark-mode / premium:** Dark themes; **scroll-driven dark sections** for focus and contrast.
- **Micro-demos:** **High-fidelity** (not generic screenshots); each frame = real capability; builds trust.
- **Scrollytelling:** [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md): chapters 1–10; **pinned product frame** per chapter; reveal-on-scroll; scroll progress; visual updates per chapter.

### Current state vs plan

| Plan requirement | Current state | Gap |
|------------------|----------------|-----|
| Product page at `/product/` | `marketing_product_page.html` exists; hero, micro-demo grid (if `product_visualization_slides`), Studio OS + Migration sections, outcomes strip, final CTA | Structure present; **pinned product frame** and **scroll-driven dark-mode** behavior need to be clearly visible and polished |
| Micro-demos (high-fidelity) | Grid and `product_visualization_slides` wired; fallbacks (e.g. placeholder) when no assets | **Seed or add real micro-demo assets** (admin, teacher, parent, student, analytics) per MARKETING_FRONT_PLACEHOLDER; ensure each card feels like a real capability |
| Scroll-driven dark mode | `data-dark-mode="true"`, `marketing-product-page.css`, scroll progress bar | **Verify** dark-first tokens (`--mkt-product-bg`, `--mkt-product-surface`), gradient hero, and dark sections; add/align **scroll-driven animations** (reveal, stagger, pinned frame updates) |
| Pinned product frame per chapter | Section “Studio OS” has copy + visual; directive requires **sticky/pinned** frame that updates per chapter | **Implement or enhance** sticky product frame and chapter-triggered visual updates (e.g. `marketing-product-scroll.js`) |
| Outcome-focused copy | Headlines and section copy are outcome-oriented (“See it work”, “Built for operators who ship”) | Keep and extend; ensure **every section** leads with outcome, not feature list |

### How to close the gap (implementation checklist)

1. **CSS / tokens**  
   - Confirm `marketing-product-page.css` (and any product-specific tokens) uses dark-first variables and scroll-aware sections.  
   - Add or tune scroll-driven transitions (e.g. opacity, transform) for `.mkt-reveal`, `.mkt-reveal-stagger`, and chapter boundaries.

2. **JS (scrollytelling)**  
   - In `marketing-product-scroll.js`: wire **chapter progress** (e.g. `data-chapter`) to a **pinned product frame** (desktop) and update frame content or state per chapter (e.g. swap image/section).  
   - Respect `prefers-reduced-motion`; keep animations subtle and purposeful per the directive.

3. **Content and assets**  
   - Seed `product_visualization_slides` (and related context) with real or high-fidelity placeholder assets for: control plane, teacher, parent, student, analytics (or equivalent outcomes).  
   - Ensure `page_extras.metrics` and any “outcomes” strip are populated so “Outcomes, not feature lists” is visible.

4. **Acceptance**  
   - Product page employs **product-led storytelling**: micro-demos and scroll-driven narrative showcase **functionality** over abstract description.  
   - **Opinionated visual minimalism** and **outcome-focused copy**; **dark-mode** and scroll-driven sections create an immersive, developer-centric experience.  
   - Matches [SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md](SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md) and [RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md](RUNMYCAMPUS_SCROLL_STORYTELLING_MARKETING_DIRECTIVE.md).

---

## 3. Where this is tracked

- **Admin/super single entry:** Implemented in `apps/schools/middleware.py` (ManagerHostControlPlaneRequiredMiddleware). No separate checklist item in SOT; this doc is the reference.
- **Marketing product page:** Alignment and remaining work are specified in [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md) §4 (scroll-storytelling, “Remaining: pinned product frame per chapter, visual updates per chapter”) and [SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md](SAAS_LANDING_TRENDS_AND_MARKETING_ALIGNMENT.md). Use the checklist in §2 above to close the gap.

When the product page meets the plan (micro-demos, scroll-driven dark-mode, pinned frame, outcome copy), update CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL §4 and this doc accordingly.
