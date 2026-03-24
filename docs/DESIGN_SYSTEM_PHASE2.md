# Phase 2 — Design system + token enforcement

**Goal:** Stop theme drift and page-by-page styling inconsistency. One product family: portal, backend, control plane, admin, marketing.

**Authority:** Complements [DESIGN_SYSTEM_BEHAVIOR.md](DESIGN_SYSTEM_BEHAVIOR.md) §8.0 / §14; [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §8.0.11.

---

## 1. Single source of truth (load order)

| Layer | File | Role |
|-------|------|------|
| Core tokens | `static/css/design-tokens.css` | Color scale (`--color-base-*`), spacing (`--token-space-*` / `--spacing-*`), typography (`--type-*`, `--heading-*`), radii (`--token-radius-*`), motion (`--motion-*`), shell elevation, **Phase 2 semantic `--ds-*`**, dark overrides |
| Luxury / polish | `static/css/design-tokens-luxury.css` | Rich black, gallery white, motion duration for premium surfaces |
| Unified legacy bridge | `static/css/design-system-unified.css` | Shared `--color-*`, radius/shadow scale; **brand primary now aliases `--school-primary`** (no separate pink system) |
| Platform premium | `static/css/platform-high-end.css` | Cards, sidebars, `--platform-premium-*` |
| Component grammars | `static/css/card-grammar.css`, `form-system.css`, `table-system.css` | Card variants, form sections, table density / `.table-family` |
| **Phase 2 enforcement** | `static/css/design-system-phase2-enforcement.css` | `.ds-card`, `.ds-empty`, `.ds-alert`, `.ds-action-bar`, `.ds-drawer-panel`, `.ds-form-stack`, `.ds-table-wrap` |

Marketing adds `static/marketing/css/tokens-marketing.css` — **`--mkt-*` values now alias product tokens** (`--color-base-*`, `--token-space-*`, `--studio-font-display`, etc.) so the marketing front cannot diverge into a second palette.

---

## 2. Semantic tokens (`--ds-*`)

Defined in `design-tokens.css` (`:root` + dark block). Use for new UI and chip/alert styling:

- **Surface/text:** `--ds-text`, `--ds-text-muted`, `--ds-surface`, `--ds-surface-raised`, `--ds-surface-muted`, `--ds-border`, `--ds-border-strong`
- **Elevation:** `--ds-shadow-sm|md|lg`
- **Radius:** `--ds-radius-sm` … `--ds-radius-xl`
- **States:** `--ds-success`, `--ds-warning`, `--ds-danger`, `--ds-info` (+ `--ds-*-bg` tints)
- **Motion:** `--ds-motion-content`, `--ds-motion-decorative`

Dark/light coherence: `html[data-theme="dark"]` / `html[data-bs-theme="dark"]` / `body.portal-backend-dark` — same variables, recalculated once.

---

## 3. Component classes (prefer on new / touched pages)

| Class | Use |
|-------|-----|
| `.ds-card` (with `.card`) | Cards aligned to admin/content surfaces + platform shadow |
| `.ds-table-wrap` | Wrapper around `.table` / `.table-family` for bordered, rounded shell |
| `.ds-form-stack` | Vertical rhythm for labels + controls (use with `.form-system`) |
| `.ds-drawer-panel` | Offcanvas / drawer inner surface |
| `.ds-empty` + `__icon` / `__title` / `__body` / `__actions` | Empty states |
| `.ds-alert` (with `.alert` / `.alert-*`) | Semantic alert borders/backgrounds from `--ds-*` |
| `.ds-action-bar` / `.ds-action-bar--sticky` | Footer action rows, bulk actions |

**Bootstrap:** Keep using `.alert`, `.card`, `.table`; add `ds-*` classes — no duplicate framework.

---

## 4. Marketing + product alignment

- **Tokens:** `--mkt-type-hero` → `var(--studio-font-display)`; spacing/radius/shadows → product scales.
- **Bridge:** `--school-primary` / `--school-accent` on marketing `:root` → `--mkt-primary` / `--mkt-accent` so proof/marketing components resolve the same names as product.
- **Surfaces:** `--mkt-on-primary`, `--mkt-on-accent`, `--mkt-checkmark`, `--mkt-star-rating` → DS semantic colors (no raw `#fff` / `#22c55e` in marketing shell CSS).
- **System theme:** `templates/marketing/base_marketing.html` sets `data-bs-theme` from `data-theme` (`light` / `dark` / `system`); `tokens-marketing.css` uses `@media (prefers-color-scheme: dark)` when `data-theme="system"`.
- **Brand overrides:** `PUBLIC_BRAND_MODE` inline styles still override `--mkt-primary` / hero colors on `:root` (allowed; feeds the same `--mkt-*` pipeline).

---

## 5. Line-by-line task completion (Phase 2 scope)

### Task 1 — Centralize tokens (color, spacing, typography, radii, shadows, states, motion)

| Item | Status | Where |
|------|--------|--------|
| Color scale + semantic neutrals | Done | `design-tokens.css` `--color-base-*`, `--ds-*` |
| Spacing 4px grid | Done | `--token-space-*`, `--spacing-*` aliases |
| Typography scale | Done | `--type-*`, `--heading-*`, `--studio-font-*` |
| Radii sm→2xl | Done | `--token-radius-sm` … `--token-radius-2xl`, `--ds-radius-*` |
| Shadows / depth | Done | `--shell-elevation-*`, `--ds-shadow-*`, `--platform-premium-*` |
| States (success/warning/danger/info) | Done | `--ds-success` … `--ds-info` (+ `-bg`), dark block |
| Motion | Done | `--motion-*`, `--ds-motion-*`, luxury motion in `design-tokens-luxury.css` |

### Task 2 — Standardize dark/light mode behavior

| Item | Status | Where |
|------|--------|--------|
| Portal/backend `data-theme` / `data-bs-theme` | Done | `portal_base.html`, `base.html` scripts; `design-tokens.css` dark block |
| Mobile `theme-color` meta | Done | `--meta-theme-color-light` / `--meta-theme-color-dark` in `design-tokens.css`; portal script + `theme_toggle.html` set content via `getComputedStyle` (no hardcoded hex) |
| Dashboard header theme partial | Done | `static/css/theme-toggle-component.css` (tokens only); `templates/components/theme_toggle.html` links stylesheet, no inline `<style>` block |
| Marketing `system` + OS preference | Done | `base_marketing.html` script + `tokens-marketing.css` `@media` + `html[data-theme="dark"]` |
| DS tokens recalculated in dark | Done | Same `--ds-*` names; values in dark selector block |

### Task 3 — Normalize components

| Component | Status | Mechanism |
|-------------|--------|-----------|
| Cards | Done | `card-grammar.css` + `platform-high-end.css` + `.ds-card` |
| Tables | Done | `table-system.css` (`.table-family`, chips → `--ds-*`) + `.ds-table-wrap` |
| Forms | Done | `form-system.css` + `.ds-form-stack`; `.form-actions.ds-action-bar` |
| Drawers | Done | `.ds-drawer-panel` + `offcanvas` selectors in enforcement CSS |
| Empty states | Done | `.ds-empty` (+ sub-elements) |
| Alerts | Done | `.ds-alert` + Bootstrap `.alert-*`; marketing messages use `ds-alert` |
| Action bars | Done | `.ds-action-bar`, `--sticky`; form actions bridged |

### Task 4 — Remove local visual improvisation (touched surfaces)

| Area | Change |
|------|--------|
| Unified primary palette | `--color-primary` → `--school-primary` (no orphan pink scale) |
| Marketing shell | Nav/hero/footer/CTAs/modules: hex → `var(--mkt-*)` / `var(--color-base-*)` / `var(--ds-*)` |
| Proof pages | Hero gradient, cards, metrics, tables → product tokens + `--school-*` bridge |
| Studio OS shell | Rail gradient, cmd palette shadow/radius → tokens |
| Control rail | `border-radius: 4px` → `var(--token-radius-sm)` |
| Admin bridge / control nav | Inline `#0B0E14` / `#0f172a` → `var(--color-base-900)` / `var(--platform-navy)` |
| Admin skip-link + preview cues | Hex → `--color-base-*` / `--ds-*` |
| Portal sidebar accent | RGBA indigo → `color-mix` + `var(--stat-admin)` |
| Dashboard header component | `dashboard-header-component.css` (tokens); template links stylesheet; no inline `<style>` block |
| Studio mode rails (Experience / Output / Automation / Launch) | `studio-mode-rail.css` (tokens); mode templates link one shared sheet |
| **Studio shell layout grid** | **Done** — `static/css/studio-shell-layout.css`; `shell_extrastyle.html` only links the sheet (same pattern as `dashboard_header` / `theme_toggle`). Tenant Studio inherits **design-tokens.css** + **design-system-phase2-enforcement.css** via `portal_base.html`; manager Studio uses **control_plane_skeleton** + `shell_control_plane.html`. |

**Documented exceptions (not theme drift):** Print-oriented report templates (`term_report.html`, etc.) may keep minimal inline sizing for PDF/layout. New work should still prefer tokens where possible.

### Task 5 — Marketing = product family language

| Item | Status |
|------|--------|
| `--mkt-*` aliases product scales | Done (`tokens-marketing.css`) |
| No parallel hero/type scale | Done (`--mkt-type-hero` = `--studio-font-display`) |
| Shared semantic states | Done (`--mkt-checkmark`, `--mkt-star-rating` → `--ds-*`) |

---

## 6. Acceptance criteria (all satisfied for Phase 2)

| Criterion | Met |
|-----------|-----|
| Touched surfaces no longer read as a separate “theme” | Yes — primary brand, marketing, proof, Studio, admin bridge aligned to tokens |
| Dark/light coherent | Yes — single variable pipeline + marketing system theme |
| Cards / forms / tables share one visual grammar | Yes — grammar sheets + `--ds-*` + `.ds-*` utilities |

---

## 7. Verification

- Visual: spot-check portal (light/dark), `/super/` (dark shell), marketing `/product/` (system theme), **`/studio/`** (tenant + manager host if applicable).
- **Phase 2 gate (required for “complete”):** `python scripts/verify_design_system_phase2.py` — asserts required CSS files, canonical bases (`portal_base`, `base`, `marketing/base_marketing`, `admin/base_site`, `control_plane_skeleton`) load `design-tokens.css` + `design-system-phase2-enforcement.css`, no inline `<style>` in `dashboard_header.html` / `theme_toggle.html` / `shell_extrastyle.html`, required static includes **`studio-mode-rail.css`** + **`studio-shell-layout.css`** on disk, and `verify_section10_5_layers.py` passes.
- **Studio OS (Phase 4 spine):** not a separate Phase 2 base template; Studio extends `portal_base` (tenant) or `control_plane_base` (manager). After Studio CSS/template edits, run `python -m pytest apps/studio_os/tests/ -q` per [STUDIO_OS_PHASE4_VALIDATION.md](STUDIO_OS_PHASE4_VALIDATION.md).
- Also: `python scripts/verify_section10_5_layers.py`; `python manage.py check`; run `bash scripts/pre_deploy_gate.sh` after broad CSS edits.
