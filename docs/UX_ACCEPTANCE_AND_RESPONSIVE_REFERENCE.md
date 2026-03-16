# UX Acceptance and Responsive Reference (§8.0.6, §8.0.11, §8.0.13)

**Purpose:** Single reference for the platform-wide UX acceptance standard and responsive requirements so every page and surface can be checked against one place. Authority: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0.

**Scope:** Applies to **every page** — tenant portal, backend (finance, evals, academics, people, reports, compliance), `/admin`, `/super/`, `/studio/*`, control-plane, marketing, onboarding, auth, error pages. No exceptions.

---

## §8.0.6 Responsive layout (platform-wide)

- **Fluid:** No fixed-width page wrapper that causes horizontal scroll on mobile. Use `max-width: 100%`, `min-width: 0`, fluid containers.
- **Layout:** Flexbox or Grid; no fixed pixel width/height for **layout** (content boxes, main, sidebar).
- **Typography:** `clamp()` or media queries for font sizes; type scales across viewports.
- **Images:** Scale with container; `max-width: 100%` where appropriate.
- **CSS:** `platform-fluid-everywhere.css` included on control_plane_skeleton, portal_base, marketing base; key templates use fluid wrappers.

**Verification:** Resize viewport to 375px, 768px, 1280px; no horizontal scroll; readable text and usable controls.

---

## §8.0.11 UX acceptance standard

A change is not accepted unless:

- `/studio/control/`, `/admin`, and `/super/` feel like **one product** (same shell, tokens, navigation).
- Dark/light behavior is **consistent** across surfaces.
- Sidebars are **consistent and role-aware**.
- Common tasks achievable in **fewer clicks**; no routine bounce to `/super/`.
- Every studio-like task available through **Studio OS**.
- Marketing and product feel like **one company**.
- Onboarding/guidance **contextual**, not annoying.
- **UI is fully responsive** (mobile, tablet, desktop): fluid layout, no fixed pixel layout dimensions, typography and images that scale.

**Final bar:** One premium enterprise platform; one shell, one design system, one navigation, one theme; layout responsive everywhere; no page with a lower or different standard.

---

## §8.0.13 Required UX acceptance tests

For **all pages and surfaces**, a change is not accepted unless:

1. `/studio/control/`, `/admin`, and `/super/` feel like one product  
2. Dark/light consistent  
3. Sidebars consistent and role-aware  
4. Fewer clicks for common tasks  
5. No bounce to `/super/` for routine work  
6. Studio tasks via Studio OS  
7. Marketing and product feel like one company  
8. Onboarding contextual, not annoying  
9. **UI fully responsive** on every page: fluid layout, no fixed pixel layout dimensions, typography and images that scale (§8.0.6)

---

## Cross-references

- **Design system behavior:** [DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md) — archetypes, drawers, wizards, modals.  
- **Decision architecture:** [DECISION_ARCHITECTURE_CHECKLIST.md](DECISION_ARCHITECTURE_CHECKLIST.md) — seven questions per page/dashboard.  
- **Dashboard taxonomy:** [DASHBOARD_TAXONOMY_AND_REGISTRY.md](DASHBOARD_TAXONOMY_AND_REGISTRY.md) — registry and archetypes.  
- **Control plane and marketing checklist:** [CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md](CONTROL_PLANE_AND_MARKETING_UX_OVERHAUL.md).  
- **Phase H manual pass:** [PHASE_H_MANUAL_CHECKLIST.md](PHASE_H_MANUAL_CHECKLIST.md) §4 (responsive).

---

*SOT ref: RUNMYCAMPUS §8.0.6, §8.0.11, §8.0.13; PATH_TO_100 Phase H / UX.*
