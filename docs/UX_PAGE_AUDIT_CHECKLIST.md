# UX page audit checklist (§8.0.12)

**Purpose:** Per RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §8.0.12, audit every authenticated and key public page for shell consistency, tokens, and UX quality. Use this checklist when adding or changing pages so `/studio/control/`, `/admin`, and `/super/` feel like one product.

**Reference:** SHELL_ARCHITECTURE_MATRIX.md (which base template per surface), THEME_CANONICAL_TOKENS.md (design token registry — single source for `design-tokens.css` and `design-system-unified.css`), §8.0.13 Required UX acceptance tests. Shared Studio OS components: `templates/studio_os/components/page_header.html`, `card.html`, `action_bar.html`.

---

## 1. Shell and base template

- [ ] Page uses the correct canonical base for its surface (tenant: `portal_base`/`backend_base`; control-plane: `control_plane_base`; Studio: extends `portal_base` with studio shell; marketing: `marketing/base_marketing`).
- [ ] No mixing of shells (e.g. control-plane CSS on tenant pages, marketing-shell on app pages).
- [ ] Studio OS pages render inside the unified shell (rail, canvas, optional right rail); admin/super pages that cannot yet be replaced are visually wrapped or normalized into the same shell where possible.

## 2. Design tokens and theme

- [ ] No hardcoded colors or spacing for layout/UI; use CSS variables from `design-tokens.css` / `design-system-unified.css` (e.g. `var(--color-base-200)`, `var(--studio-radius)`, `var(--vis-text)`, `--school-primary` where appropriate).
- [ ] Dark/light: page respects theme (no fixed white/dark backgrounds that break in the other mode).
- [ ] No token mismatch: same token set as the rest of the shell (no one-off `#hex` or `rgba()` for structural styling).

## 3. Navigation and wayfinding

- [ ] Sidebar/rail is consistent with the rest of the product (same sections, role-aware; no duplicate or legacy labels).
- [ ] Breadcrumbs and page titles are clear and normalized (no "back to /super/" as primary CTA; context preserved).
- [ ] Command palette: page intent is discoverable via command palette keywords where relevant (see `get_studio_command_palette_entries` and COMMAND_PALETTE_PRIMARY.md).

## 4. Actions and click compression

- [ ] One primary CTA or clear "main thing to do here"; next best action obvious.
- [ ] No action dumping or button gardens; contextual secondary actions only where needed.
- [ ] Common tasks achievable in fewer clicks (inline drawers, side panels, sticky action bars preferred over 4–6 page hops).
- [ ] No dead-end actions (every action leads somewhere or gives clear feedback).

## 5. Responsive and accessibility (North star N3, N4)

- [ ] **N3 WCAG 2.1 AA:** Keyboard nav, screen-reader support, focus management, color contrast, skip links; audit critical tenant/manager pages (e.g. `lint_north_star_a11y`, phase_h_audit).
- [ ] **N4 Mobile-first and touch:** Every high-use flow works on phone/tablet; no horizontal scroll; touch targets ≥44px; responsive lint in CI.
- [ ] Layout uses Flexbox or Grid; no fixed-width page wrappers (no `width: 1200px` on main container).
- [ ] Typography and images scale (e.g. `clamp()`, fluid units); no horizontal scroll on small viewports.
- [ ] Focus and keyboard: visible focus states using design tokens; no focus traps.

## 6. Empty states and consistency

- [ ] Empty states use helper content and match design system (no blank panels).
- [ ] Tables/forms/cards use consistent anatomy (same card style, spacing, borders as shell).
- [ ] Marketing and product feel like one company (same color system, typography, premium feel on both sides).

## 7. Inclusive terminology and imagery (North star N23)

- [ ] No internal jargon in user-facing copy; use terms that match "how this school works" in the region.
- [ ] Imagery and examples reflect global diversity and multiple school types where applicable.

---

## How to use

- **New page:** Before merging, run through sections 1–6 for the new template and its view.
- **Refactor:** When touching a template, check at least sections 1–2 and 5.
- **Release audit:** Periodically sample pages from each surface (tenant backend, control-plane, Studio modes, admin, marketing) and tick off this list; log results in docs or RELEASE_CHECKLIST.

**Completion gate (§8.0.11):** A change is not accepted unless the app feels like one premium enterprise platform; `/admin`, `/super/`, and `/studio/*` no longer feel like cousins from different families. This checklist is the operational tool to get there.
