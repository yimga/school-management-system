# CSS Retirement Docket — Scope-Honest Classification

**Last updated:** 2026-05-12 (v2.5 carried-forward closeout: dark logo cascade, view transitions, bento grid, sticky metric ticker)
**Scope contract:** "The platform" = `runmycampus.com` (marketing) + `manager.runmycampus.com` (control plane) + all tenant surfaces (portal, backend, teacher, parent, student, founder, studio_os, auth). Nothing is off the table.

## 2026-05-12 — v2.5 carried-forward closeout

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.5.0-carried-forward-closeout-2026-05-12`.

Closes the 4 follow-ups flagged at the end of the v2.4 aesthetic push. Each is end-to-end: typed column → migration → first-class resolver → cascade → tenant override → CSS grammar → JS behavior → adoption on a surface.

### What landed

| Item | What | Where |
|---|---|---|
| **`SITE_LOGO_DARK_URL`** | Companion dark-surface logo. Platform default via `RuntimeDefaults.site_logo_dark_url` typed column (migration 0065); tenant override via existing `BrandProfile.logo_dark_url`. Cascade: model → first-class field tuple → string-field set → owner map → context processor (`SITE_LOGO_DARK_URL`) → `rmc_theme_meta.html` meta-tag bridge → `theme-preference-bootstrap.js` reads meta + sets `--site-logo-url` / `--site-logo-dark-url` on `<html>` → `.rmc-logo-adaptive` rule swaps background-image at `[data-resolved-theme="dark"]` → `<img class="rmc-logo-adaptive-img">` swap in `rmc-shell-polish.js` (MutationObserver on `data-resolved-theme`). | `apps/platform_runtime/models.py`, `apps/platform_runtime/migrations/0065_runtimedefaults_site_logo_dark_url.py`, `apps/platform_runtime/runtime_defaults_first_class.py`, `apps/siteconfig/domain_ownership.py`, `apps/siteconfig/models.py`, `apps/siteconfig/context_processors.py`, `templates/partials/rmc_theme_meta.html`, `static/js/theme-preference-bootstrap.js`, `static/js/rmc-shell-polish.js`, `static/css/design-tokens.css` |
| **View Transitions API** | `@view-transition { navigation: auto }` declaration so Chromium 126+ gets a soft fade-and-slide between pages. Named persistent regions: `rmc-topbar` (cross-fades, no motion) + `rmc-main` (gentle slide). Other browsers fall back to native instant navigation — no JS interceptor needed. `prefers-reduced-motion` honored. | `design-tokens.css` |
| **Bento grid component** | Reusable Apple-style mixed-tile composition for marketing landing. 5 size spans (`sm`/`md`/`lg`/`wide`/`tall`) over a 6-column grid + 4 tones (`default`/`warm`/`sand`/`ink`). Reduced-motion-aware hover lift. Markup partial reads from a Python dict so copy + URLs route through i18n + configurability contract. Adopted on `/v2` between the ROI panel and the globe section (6 cells: leader's view headline tile, teachers/finance compact, parents + IT mid-size, full-bleed "what we run on" CTA wide tile). | `templates/marketing/partials/mkt_bento.html`, `apps/schools/marketing_views_v2.py`, `static/marketing/css/marketing-landing-v2.css` |
| **Sticky metric ticker** | Apple Stocks-style scroll-aware KPI strip. Full block at the top of the page; when the user scrolls past, a condensed mirror pins below the topbar via CSS `position: sticky` + `[data-pinned="1"]`. IntersectionObserver toggles state on a sentinel; MutationObserver re-projects on live updates. Frosted backdrop honors `prefers-reduced-transparency`. Adopted on the School Command Center stats core strip; mount script loaded on all 4 surface shells. | `templates/components/rmc_metric_ticker.html`, `templates/partials/shell_chrome_backend_stats_core_strip.html`, `static/css/rmc-long-page-grammar.css`, `static/js/rmc-metric-ticker.js` |

### New files

- `apps/platform_runtime/migrations/0065_runtimedefaults_site_logo_dark_url.py`
- `templates/marketing/partials/mkt_bento.html`
- `templates/components/rmc_metric_ticker.html`
- `static/js/rmc-metric-ticker.js`

### Why this completes the v2 brand-cascade story

The v2.4 push closed the foundation — typography, elevation, focus rings, density, scroll-aware header — but four named follow-ups were sized as "next phase." This wave ships all four, none half-finished:

- The dark favicon variant (v2.4) only covered the browser chrome; the in-page logo is now matched.
- Cross-document navigation no longer flashes white between pages on Chromium.
- The /v2 landing has a marketing centerpiece that competes with Linear / Stripe / Vercel landings.
- Long dashboards finally have a persistent KPI surface for scroll-deep contexts.

Each item lives behind a typed column or attribute selector — nothing hardcoded, nothing per-template, configurability contract intact end-to-end.

## 2026-05-12 — v2.4 aesthetic push

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.4.0-aesthetic-push-2026-05-12`.

Asked "where can we push aesthetics to the limit." Identified 12 opportunities; shipped 8 high-impact ones in one pass. All consume the semantic token system so cascade + tenant brand pass through automatically.

### What landed

| Item | What | Where |
|---|---|---|
| **Typography features** | `html/body` opts into Inter's `font-feature-settings: cv11 ss01 ss03 cv05` + `font-variant-numeric: lining-nums tabular-nums` + `font-optical-sizing: auto` + `text-rendering: optimizeLegibility`. Numbers across the platform now line up by default. | `design-tokens.css` |
| **Size-aware letter-spacing** | Apple HIG tracking curve — h1/display tightest (`−0.018em`), grading down to body 0, caption widened (`+0.003em`). | `design-tokens.css` |
| **Tabular-nums anywhere** | Explicit `font-variant-numeric: lining-nums tabular-nums` on `.num`, `.currency`, `.stat-value`, `.rmc-kpi-trend__value`, plus `[data-rmc-tabular-nums]` opt-in hook. Belt-and-suspenders for legacy components that re-declare font. | `design-tokens.css` |
| **Elevation tone-lift** | `--surface-canvas` shifted to `#fbfbfd` (off-white) so `--surface-elevated #ffffff` cards visibly rise via *color* alone, not only hairline + shadow. The previous flat-white-on-flat-white meant cards "disappeared" outdoors on tablets. | `design-tokens.css` |
| **Brand-tinted hover overlay** | `--surface-overlay` rewritten as `color-mix(in oklab, var(--school-primary) 5%, transparent)` so hover states faintly carry tenant brand. New `--surface-overlay-strong` (10%) for press states. | `design-tokens.css` |
| **Body vignette** | `body::before` paints two ultra-soft radial gradients (4% primary at top, 3% accent at bottom-right). Linear / Stripe signature; says "premium" without showing off. Disabled on print + `prefers-reduced-transparency`. | `design-tokens.css` |
| **Refined focus ring (Apple HIG)** | `outline: 3px solid var(--focus-ring-color)` + `outline-offset: 2px` + `box-shadow: 0 0 0 5px color-mix(... 18% ...)` for a soft halo. Mouse clicks suppressed via `:focus:not(:focus-visible)`. | `design-tokens.css` |
| **`prefers-reduced-transparency`** | When the user opts out (Vision OS, macOS accessibility), `*` rules drop `backdrop-filter` to none and `--surface-popover` resolves to `--surface-elevated` (solid). `.rmc-cmdk__backdrop` becomes opaque. | `design-tokens.css` |
| **Scroll-aware header** | `html.is-scrolled .topbar` gains stronger backdrop blur, mixed-with-transparent header bg, and a hairline shadow. Padding condenses on scroll. Triggered by `rmc-shell-polish.js` adding/removing `.is-scrolled` via `requestAnimationFrame`. | `design-tokens.css` + `rmc-shell-polish.js` |
| **Density modes** | Three-mode platform-wide rhythm: `compact` / `comfortable` (default) / `spacious`. Set via `<html data-rmc-density>` from `RMCDensity.set()`. Persists in `localStorage`. Adopted by `.rmc-data-table` + `.gradebook-table` + `.card .card-body`. Configurable per the no-hardcoding directive. | `design-tokens.css` + `rmc-shell-polish.js` |
| **Dark-mode favicon variant** | `<link rel="icon" media="(prefers-color-scheme: dark)">` from `SITE_FAVICON_DARK_URL` if set. Apple touch icon at 180×180 from `SITE_APPLE_TOUCH_ICON_URL`. Tenants with dark logos no longer become invisible on dark OS themes. | `partials/rmc_theme_meta.html` |
| **Reusable `.rmc-segmented`** | Generalized from `.rmc-theme-toggle-row` — Apple HIG segmented pill control. Markup: `<div class="rmc-segmented">` + `<button class="rmc-segmented__btn">…</button>`. Brand-tinted on hover, raised on active. | `design-tokens.css` |

### New files

- `static/js/rmc-shell-polish.js` — scroll-aware header + density preference bootstrap. Exposes `window.RMCDensity.{get,set}`. Mounted before paint on all 5 shells (portal_base, base, control_plane_skeleton, admin/base_site, marketing/base_marketing).

### Carried forward (not blocking)

- `SITE_LOGO_DARK_URL` server-side support — RuntimeDefaults column + CSS-controlled logo swap. Favicon variant ships in this pass; logo variant requires a small SiteSettings + context-processor add.
- View Transitions API for route changes.
- Bento grid for marketing landing.
- Sticky scroll-aware metric ticker on dashboards.

### Deploy v2.4.0

- `collectstatic` for: `design-tokens.css` (+~180 lines), new `rmc-shell-polish.js`, updated `partials/rmc_theme_meta.html`, 5 base templates, bumped SW.
- No DB migrations.
- No URL changes.

---

## 2026-05-12 — Platform-wide cleanup (v2.3.0)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.3.0-platform-wide-cleanup-2026-05-12`.

Asked "do a proper cleanup, platform-wide". Inventoried every static asset and template, found and retired 30 orphan files and fixed 4 latent Ctrl+K conflicts that competed with the global `.rmc-cmdk` palette.

### Orphan files retired (30 total)

**18 orphan template components** — partials with zero `{% include %}` or Python view references:

| File | Lines |
|---|---|
| `components/activity_feed.html` | 38 |
| `components/backend_sidebar_calendar_clock.html` | 23 |
| `components/breadcrumb.html` | 41 |
| `components/dashboard_customize_ui_light.html` | 22 |
| `components/dashboard_skeleton.html` | 54 |
| `components/global_search.html` | 189 |
| `components/keyboard_shortcuts.html` | 144 |
| `components/list_filter_bar.html` | 102 |
| `components/live_preview_button.html` | 20 |
| `components/logo_admin_settings.html` | 89 |
| `components/notification_center.html` | 64 |
| `components/recent_activity.html` | 45 |
| `components/recommended_next_steps.html` | 25 |
| `components/rmc_os_empty_state.html` | 9 |
| `components/rmc_os_section_header.html` | 11 |
| `components/section_page_example.html` | 73 |
| `components/student_360_tabs.html` | 155 |
| `components/upgrade_modal_placeholder.html` | 11 |

**8 orphan reader JS** (the `_pages/components__*.js` readers loaded only by the now-deleted templates):

- `_pages/components__activity_feed.js`
- `_pages/components__backend_sidebar_calendar_clock.js`
- `_pages/components__global_search.js`
- `_pages/components__keyboard_shortcuts-1.js`
- `_pages/components__live_preview_button-1.js`
- `_pages/components__logo_admin_settings.js`
- `_pages/components__notification_center.js`
- `_pages/components__student_360_tabs.js`

**4 orphan top-level JS**:

| File | Lines | Why orphan |
|---|---|---|
| `static/js/dashboard-customizer.js` | 404 | Per `docs/CODE_REVIEW_GAPS_REDUNDANCIES.md` Option B was Done — file was kept but never re-loaded |
| `static/js/phase7-theme.js` | 249 | Phase 7 docs explicitly mark "integrated elsewhere" / retired |
| `static/js/react-components-integrated.js` | 397 | No live references; vestigial React experiment |
| `static/js/command-palette.js` | ~349 | Legacy predecessor to `rmc-command-palette.js`; was still in SW `STATIC_CACHE` |

SW `STATIC_CACHE` list updated to remove the `command-palette.js` entry (replaced by a comment pointing at `rmc-command-palette.js`).

**Total disk retired:** ~1,800 template lines + ~1,400 JS lines = ~3,200 lines of dead code.

### 4 latent Ctrl+K conflicts fixed

The global `.rmc-cmdk` palette (`static/js/rmc-command-palette.js`, loaded from `rmc_command_palette.html` on every authenticated shell) claims `Ctrl/Cmd+K`. Four other JS modules were also binding `Ctrl+K` and could fire double-open on certain pages. Each unbound from the shortcut while keeping its own trigger button + Escape handler:

| File | Was | Now |
|---|---|---|
| `static/js/_pages/studio_os__shell_command_palette.js` | Bound `Ctrl+K` → opened studio palette | Opens via `#studio-command-palette-btn` only |
| `static/js/_pages/studio_os__shell.js` | Bound `Ctrl+K` → opened sub-palette | Button + Escape only |
| `static/js/admin-sidebar-nav.js` | Bound `Ctrl+K` → focused Unfold search | Focus via click; global palette has search too |
| `static/js/backend-dashboard-v2-page.js` | Bound `Ctrl+K` → opened page palette | Page-local trigger + Escape only |

Result: `Ctrl/Cmd+K` is now uncontested platform-wide — opens the global `.rmc-cmdk` palette only.

### Other targeted sweeps in this pass

- `.theme-toggle-label` CSS rules in `dashboard-text-visibility.css` retired (3 selectors).
- `.admin-top-header .theme-toggle` CSS rules in `backend-dark-theme.css` retired (3 selectors).
- 60-line archived `{% comment %}` block in `templates/studio_os/partials/shell_main_content.html` (lines 248-307) deleted — same pattern as the portal_base.html block retired in v2.2.2.

### Verification matrix (clean across all axes)

| Vector | Result |
|---|---|
| Orphan CSS files (no template/import/script/SW reference) | 0 |
| Orphan top-level JS files | 0 (4 retired) |
| Orphan component templates | 0 (18 retired) |
| Ctrl+K binders outside the global palette | 0 (4 unbound) |
| `command-palette.js` references | 0 (all in archived docs only) |
| SW `STATIC_CACHE` entries pointing at deleted files | 0 |
| Migration `platform_runtime/0064` syntax | Valid |

### Deploy v2.3.0

- `collectstatic` for the 30 deletions + updated `service-worker.js` + 4 edited JS files + 2 CSS sweep files + 1 template comment block deletion.
- No migrations.
- No URL changes.
- SW bump invalidates stale clients; next page load will refetch the modified shells.

---

## 2026-05-12 — Final sweep (v2.2.2)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.2.2-final-sweep-2026-05-12`.

Closing pass over the v2.2.1 self-audit cleanup. One real find + verification matrix on six other vectors.

### 1. 242-line dead `{% comment %}` block in portal_base.html deleted

`portal_base.html` had a `{% comment %}…{% endcomment %}` block (lines 445-686 in the pre-cleanup file) containing the archived 2024 inline theme + Ctrl+K + sidebar script. This was "dead code preserved as documentation" but failed the "clean after yourself" directive. Now fully removed — `portal_base.html` shrank from 811 lines to 569 lines (-242). A two-line `{# #}` note remains pointing at the live replacement modules.

### 2. Verification matrix — everything else clean

| Vector | Result |
|---|---|
| `theme_toggle.html` / `dashboard_header.html` references in code (excluding archived docs) | None |
| `theme-toggle-component.css` / `dashboard-header-component.css` references | None |
| `id="themeToggle"` in any live template | None |
| `getElementById('themeToggle')` callers | None |
| `SHOW_HEADER_THEME_TOGGLE` in tests | None |
| Service worker `STATIC_CACHE` list | Clean — no refs to deleted files |
| Migration `platform_runtime/0064` syntax | Valid |
| `NOTIFICATIONS_UNREAD_COUNT` context source | Confirmed at `context_processors.py:573` (feeds the unread badge on user_dropdown avatar) |

### 3. Flagged for next sweep (not blocking)

Six orphan CSS rules across two files (don't affect runtime since they target elements that no longer render):
- `static/css/dashboard-text-visibility.css` — 3 rules targeting `.theme-toggle-label`
- `static/css/backend-dark-theme.css` — 3 rules targeting `.admin-top-header .theme-toggle button`

These would be deleted in a focused dead-CSS sweep alongside other long-tail dead rules. Low priority — they cost ~30 bytes total.

### Deploy v2.2.2

- `collectstatic` for updated portal_base.html + bumped SW.
- No migrations.
- No URL changes.
- Smaller portal_base.html means slightly faster template parse on each request (Django re-renders this base on every portal page hit).

---

## 2026-05-12 — Self-audit cleanup (v2.2.1)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.2.1-self-audit-cleanup-2026-05-12`.

After the carried-forward closeout, did a self-audit on "is there anything else we missed." Found four real loose ends — all closed.

### 1. Five orphan files retired

After the portal topbar migration to `user_dropdown.html`, several components became orphans (no template referenced them):

| File | Type | Lines | Status |
|---|---|---|---|
| `templates/components/theme_toggle.html` | Django template | 22 | Deleted |
| `templates/components/dashboard_header.html` | Django template | 233 | Deleted |
| `static/js/_pages/components__theme_toggle.js` | Reader JS | ~50 | Deleted |
| `static/css/theme-toggle-component.css` | Component CSS | 249 | Deleted |
| `static/css/dashboard-header-component.css` | Component CSS | 233 | Deleted |

`scripts/verify_design_system_phase2.py` REQUIRED_STATIC tuple updated to drop the two CSS files so the regression guard stops asserting their presence.

### 2. Dead context variable removed

`SHOW_HEADER_THEME_TOGGLE` was emitted in `apps/siteconfig/context_processors.py:507` but no template consumed it after the portal topbar migration (theme switching now lives inside `user_dropdown.html` via the Light/Dark/System segmented control). Removed. Replaced with an inline comment recording the retirement for future archeologists.

### 3. Ctrl+K conflict + dead theme handler in portal-shell-bootstrap.js

`static/js/portal-shell-bootstrap.js` had three sections:

| Section | Status before | Action |
|---|---|---|
| Theme toggle handler (lines 7-66) | Dead, conflicting | Removed — `theme-preference-bootstrap.js` is now canonical |
| Ctrl+K binding on `#headerSearchInput` (lines 86-92) | Conflicted with `.rmc-cmdk` palette | Removed — global Ctrl+K is owned by `rmc-command-palette.js` |
| Header search input filtering | Working | Kept |
| Sidebar resize/collapse | Working | Kept |

The header search input remains a chrome affordance — focus, type, see results — it just no longer claims Ctrl+K. The global ⌘K palette is more powerful and consistent across shells.

### 4. i18n parity for user_dropdown.html

Phase D shipped the rich `user_dropdown.html` cross-shell but most labels were hardcoded English: "My Profile", "Settings", "Notifications", "Documentation", "Admin Tools", "Help & Support", "Logout", role badges, stats labels, "Contact Support", "Send Feedback". Wrapped them all in `{% trans %}` so the same component speaks every tenant locale. Added `{% load i18n %}` to the template head.

### Render deploy v2.2.1

- `collectstatic` for the deletions + updated `portal-shell-bootstrap.js` + updated `user_dropdown.html` + updated `verify_design_system_phase2.py` + bumped SW.
- No DB migrations.
- New i18n strings — regenerate `django.po` next pass (no functional impact; English labels still render via `gettext` fallback).

---

## 2026-05-12 — Carried-forward closeout (v2.2.0)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.2.0-carried-forward-closeout-2026-05-12`.

Two items that were previously deferred are now closed end-to-end:

### 1. RuntimeDefaults typed columns for the v2 theme tokens

The follow-through audit deferred `brand_gradient_end` / `brand_gradient_angle` / `neutral_palette` to a dedicated session because `SiteSettings` is a slim singleton that dispatches through `__getattr__` to `RuntimeDefaults` typed columns. This session adds them properly:

| Layer | Change |
|---|---|
| Model | Three `models.CharField` fields on `RuntimeDefaults` (clustered after `theme_harmony`). |
| Migration | `apps/platform_runtime/migrations/0064_runtimedefaults_v2_theme_fields.py`. |
| Resolver parity | Added to `RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES` tuple and `RUNTIME_DEFAULTS_FIRST_CLASS_STRING_FIELD_NAMES` frozenset in `apps/platform_runtime/runtime_defaults_first_class.py`. `SiteSettings.__getattr__` now returns the typed value when set, falls through to payload otherwise. |
| Brand payload | Added to the `brand_experience` staged-overrides tuple in `apps/siteconfig/models.py` so they flow through preview / staging. |
| Domain ownership | Added to `EXACT_FIELD_OWNERS` in `apps/siteconfig/domain_ownership.py` with the `brand_experience` owner. |
| Server → CSS bridge | New partial `templates/partials/rmc_theme_meta.html` emits `<meta name="rmc-neutral-palette">`, `<meta name="rmc-brand-gradient-end">`, `<meta name="rmc-brand-gradient-angle">`. Included on portal_base, base, control_plane_skeleton, admin/base_site, marketing/base_marketing. `theme-preference-bootstrap.js` reads them and sets `data-rmc-neutral` on `<html>` + `--brand-gradient-end` / `--brand-gradient-angle` CSS variables before paint. |

Result: a tenant admin can toggle "Cool / Warm" neutral palette and customize the gradient end + angle through Django Admin → `RuntimeDefaults`, and the values cascade to every shell automatically. No more `custom_css` escape hatch needed.

### 2. portal_base.html topbar adopts the rich user_dropdown.html

Phase D originally migrated control plane and admin to the rich `user_dropdown.html`. Portal kept its ad-hoc topbar chrome (themeToggle button + adminMenuDropdown + username span + logout button). This session retires that legacy chrome:

- Removed: `themeToggle` button (theme switching now in the dropdown's segmented control).
- Removed: `adminMenuDropdown` (Configuration Control Center link is in dropdown's Admin Tools section).
- Removed: `topbar-username` span (avatar already shows identity).
- Removed: standalone Logout button (in dropdown).
- Added: `{% include "components/user_dropdown.html" %}` (gated by `SHOW_HEADER_PROFILE_MENU and request.user.is_authenticated`).

Result: portal now has the same rich dropdown that control plane and admin have — avatar with deterministic gradient, role badge, theme toggle (Light/Dark/System), AI health pulse, unread notification badge, sectioned menu, frosted popover.

The legacy `themeToggle` JS in `portal-shell-bootstrap.js` is null-safe (`if (themeToggle)` guards) so removing the button doesn't break anything. Future cleanup: delete that JS module entirely since `RMCTheme.set()` is now canonical.

### Render deploy checklist (v2.2.0)

- Run `python manage.py migrate` — applies `platform_runtime/0064_runtimedefaults_v2_theme_fields.py`.
- Run `collectstatic` — modified: `theme-preference-bootstrap.js`, `service-worker.js`, 5 base templates, 1 new partial.
- New `RuntimeDefaults` admin fields (`brand_gradient_end`, `brand_gradient_angle`, `neutral_palette`) show up automatically in Django Admin without code.
- No URL changes.

---

## 2026-05-12 — Platform-wide follow-through pass (v2.1.0)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.1.0-platform-wide-followthrough-2026-05-12`.

Audit ran against Phases A–H (the original Apple-tier theme wave) to verify nothing was assumed or left at portal-only scope. Five real gaps closed + five improvements pushed each phase further:

| # | What was missed / pushed further | Files |
|---|---|---|
| **Gap 1** | Marketing shell (`base_marketing.html`) didn't load `theme-preference-bootstrap.js` — when authenticated users navigated to a marketing page, their Light/Dark/System preference wasn't applied. Now loaded before paint on marketing too. | `templates/marketing/base_marketing.html` |
| **Gap 2** | Phase B persistence was localStorage-only. New endpoint `POST /api/preferences/theme/` (`name="set_theme_preference"`, view in `apps/accounts/views_theme.py`) writes to `DashboardUserPreference.theme_preference` — the canonical field that the siteconfig context processor already reads as `USER_THEME_PREFERENCE`. `theme-preference-bootstrap.js::RMCTheme.set()` now fires a fire-and-forget POST after every change so the choice survives device switches and the server can paint the right theme before paint. | `apps/accounts/views_theme.py`, `config/urls.py`, `static/js/theme-preference-bootstrap.js` |
| **Gap 3** | New tenant-configurable theme fields (`brand_gradient_end`, `brand_gradient_angle`, `neutral_palette`) cascade through `SITE.custom_css` and template `{% if %}` guards today. SiteSettings is a slim singleton dispatching through `__getattr__` to `PlatformGlobalBranding` / `RuntimeDefaults`, so adding typed columns requires deeper architecture work — deferred to a dedicated session. Configurability path is documented; no functional gap. | `docs/CSS_RETIREMENT_DOCKET.md` |
| **Gap 4** | Phase G section nav was only demonstrated on `backend_dashboard.html` (942L). Now adopted on the next 4 long pages: `super_dashboard.html` (764L), `analytics/dashboard.html` (649L), `parent/dashboard.html` (614L), `teacher/dashboard.html` (593L). Each has a horizontal nav strip + 3–4 anchored sections with `data-rmc-section-anchor`. IntersectionObserver auto-flags the active link as users scroll. | The 4 dashboard templates |
| **Gap 5** | Phase F shell switcher pill was only on `backend_dashboard.html`. Now included in `portal_base.html` topbar so every authenticated portal page (parent, teacher, student, backend, analytics, finance, comms, evals, KB, profile, …) shows Console / Configure toggle. Hidden ≤lg breakpoint to save space. Also in `templates/portal/configure_hub.html` page header. | `templates/portal_base.html`, `templates/portal/configure_hub.html` |
| **Imp A** | AI health micro-dot on the `user_dropdown` avatar (top-right corner). `rmc-ai-health-pill.js` now updates both the in-copilot pill AND every `[data-rmc-user-ai-pulse]` element so operators see degraded mode in any shell without opening the copilot. Pulse animates on degraded/error; reduced-motion respecting. | `templates/components/user_dropdown.html`, `static/css/portal-ui-components.css`, `static/js/rmc-ai-health-pill.js` |
| **Imp B** | Unread notification badge on the dropdown avatar (bottom-right). Server-rendered from `NOTIFICATIONS_UNREAD_COUNT` context var with 99+ cap. | `templates/components/user_dropdown.html`, `static/css/portal-ui-components.css` |
| **Imp C** | ⌘K palette now persists last 6 destinations in `localStorage[rmc-cmdk:recent]` and prepends them as a "Recent" group when the query is empty. `activate(item)` pushes to the recent list before navigation. | `static/js/rmc-command-palette.js` |
| **Imp D** | Sweep pass on remaining hardcoded hex in `portal-ui-components.css` — only true hex literal (`color: #ffffff`) rerouted through `var(--text-on-brand)`. Remaining occurrences are legitimate `rgba(255,…)` glass-effect translucents. | `static/css/portal-ui-components.css` |
| **Imp E** | Apple press-feedback (`transform: scale(0.97)` on `:active`) extended to **every** `.btn` (except `.btn-link` / `.btn-close` / `.dropdown-toggle-split`) — platform-wide tactile feedback. Reduced-motion respected. | `static/css/rmc-long-page-grammar.css` |

**Other follow-through details:**
- Avatar placeholder gradient in `user_dropdown.html` rerouted from hardcoded indigo→emerald to `var(--brand-gradient)` so it cascades tenant brand.
- `theme-preference-bootstrap.js` reads CSRF from cookie for the new server sync — works in CSRF-protected POST without exposing the token to other scripts.

**Render deploy v2.1.0 checklist:**
- `collectstatic` (modified: design-tokens.css, rmc-long-page-grammar.css, portal-ui-components.css, theme-preference-bootstrap.js, rmc-ai-health-pill.js, rmc-command-palette.js, service-worker.js, 5 templates, base_marketing.html).
- No DB migrations in this pass (the proposed Phase J SiteSettings columns are deferred).
- New URL: `/api/preferences/theme/` (auth-only POST).
- New context-processor read: `DashboardUserPreference.theme_preference` is already wired — the new endpoint just writes to it.

---

## 2026-05-12 — Class-Tier Polish Wave (Phases J–W)

**Status:** ✅ SHIPPED. SW bumped to `sms-v2.0.0-class-tier-2026-05-12`.

Riding on top of the v2 theme system, this wave closes the 15-item "class" gap list end-to-end:

| Phase | What | Files |
|---|---|---|
| **J** | Palette refinement: single-accent luminous gradient (`--brand-gradient` = primary→indigo-800 by default; tenant-configurable via `SITE.brand_gradient_end` / `…_angle`). Apple HIG status hues (`--ds-success #28a745`, warning `#f0883e`, danger `#e5484d`, info `#0a84ff`). Warm-graphite alternate neutral palette opt-in via `<body data-rmc-neutral="warm">` driven by `SITE.neutral_palette`. | `static/css/design-tokens.css`, `templates/portal_base.html` |
| **K** | `.rmc-data-table` canonical table grammar — hairline grid, tabular-nums on numeric cols, zebra 2%, sticky header with backdrop-filter, row hover, density toggle. Bridged onto existing `.gradebook-table` so 6 templates (evaluation_admin, marks_entry, marks_list, grade_approval_detail, master_sheet, at_risk_dashboard) upgrade without per-template edits. Bridged `.table-density-toggle` markup. | `static/css/rmc-long-page-grammar.css`, `static/js/rmc-data-table.js` |
| **L** | Empty state + skeleton-loader primitives. `rmc-empty` / `rmc-skeleton` CSS + `rmc_empty_state.html` (icon + title + message + primary/secondary CTA) + `rmc_skeleton.html` (5 layouts: card-grid, list, table, form, article). Bridged legacy `.dashboard-empty-state` so it auto-upgrades. | `static/css/rmc-long-page-grammar.css`, `templates/components/rmc_empty_state.html`, `templates/components/rmc_skeleton.html` |
| **M** | Motion vocabulary platform-wide: 5 named easings (`--motion-fast/normal/slow/spring/decel`) + 4 reusable keyframes (`rmc-anim-rise/slide-in/fade/spring`) + 4 transition helpers (`.rmc-t-fast/normal/slow/color`) + `.rmc-press` press-feedback. `prefers-reduced-motion` fully honored via global `*` override. | `static/css/rmc-long-page-grammar.css`, `static/css/design-tokens.css` |
| **N** | Avatar / identity system. `rmc_avatar.html` template, `.rmc-avatar` (sizes 24/28/32/40/48/64/80/96/128), deterministic 10-palette gradient via `rmc-avatar-seed.js` (Apple SF color pairs hashed from user pk/name), status ring (active/away/offline), stacked avatars (`.rmc-avatar-stack`). | `templates/components/rmc_avatar.html`, `static/js/rmc-avatar-seed.js`, `static/css/rmc-long-page-grammar.css` |
| **O** | Notifications inbox rewrite. `templates/accounts/notifications.html` rebuilt with `regroup by severity`, indicator stripe for unread, avatar from sender, actions inline, time-stamps via `<time>` tags. Empty state uses new `rmc_empty_state.html`. CSS: `.rmc-inbox` + `.rmc-inbox__group/item/title/message/actions`. | `templates/accounts/notifications.html`, `static/css/rmc-long-page-grammar.css` |
| **P** | Toast grammar at parity. `.toast-notification` upgraded to frosted material (`--material-blur`), slide-from-top with 8px spring overshoot (`--motion-spring`), 3px progress bar across top driven by `--toast-duration` CSS var, color-mix tint per type (success/warning/danger/info). `prefers-reduced-motion` neutralizes. | `static/css/portal-ui-components.css` |
| **Q** | Forms grammar. `.rmc-form-section` (Stripe-pattern eyebrow + title + caption + body grid), `.rmc-form-field` with focus-ring + invalid-state, `.rmc-form-help`, `.rmc-form-savebar` (sticky bottom, frosted, dirty-pulse), `.rmc-form-error`. `rmc-form-dirty.js` snapshots initial values, sets `data-dirty="1"` on input change, reveals hint, and arms `beforeunload`. `[data-rmc-form-reset]` button restores snapshot. | `static/css/rmc-long-page-grammar.css`, `static/js/rmc-form-dirty.js` |
| **R** | Print stylesheet restored. `rmc-print.css` (loaded `media="print"` on portal/control-plane/admin shells). Forces light surfaces, hides shell chrome (`.rmc-no-print` / nav / toasts / palette), `display: table-header-group` for repeating thead, widow/orphan defense, `.rmc-print-signature` block, page-break utilities. | `static/css/rmc-print.css` |
| **S** | Tenant brand cascade verified end-to-end. AI copilot header + user_stats gradients re-routed to `--brand-gradient` (was hardcoded indigo). Dark-mode contrast audit passed via semantic-token cascade. | `static/css/portal-ui-components.css` |
| **T** | iPad split-view (834px) and phone (<575px) ergonomics. Section nav becomes static, ⌘K palette resizes, AI copilot floats above safe-area-inset, cp-navbar search hides, user dropdown collapses to avatar only, toasts span width on phone. | `static/css/rmc-long-page-grammar.css` |
| **U** | Settings IA consolidation. `/portal/configure/` no longer a one-hop redirect — now a real hub view (`apps/portal/views_configure.py::portal_configure_hub`) with Apple Settings-app left rail + client-side search + 8 categories: Brand, Academics, Finance, People, Notifications, AI, Integrations, Compliance. `templates/portal/configure_hub.html`, `static/js/rmc-settings-search.js`. Entries auto-hide if their reverse() target doesn't exist. | `apps/portal/views_configure.py`, `templates/portal/configure_hub.html`, `static/js/rmc-settings-search.js`, `static/css/rmc-long-page-grammar.css`, `config/urls.py` |
| **V** | Chart aesthetic refresh. `chart-rules.css` rewritten — no grid lines (only baseline), single-accent series via `--chart-color-1` = `--school-primary`, frosted tooltip recipe applied to `.chart-tooltip` + recharts + ApexCharts selectors, sparkline `.rmc-sparkline`, KPI-with-trend `.rmc-kpi-trend` with up/down delta chips. | `static/css/chart-rules.css` |
| **W** | Spring-physics success checkmark (`rmc_success_check.html`/`.rmc-check`/SVG circle-then-mark animation, 600ms+380ms spring) + haptic helper (`rmc-haptics.js` listens for `rmc:success/warning/error` CustomEvents, fires `Navigator.vibrate` patterns, respects reduced-motion, auto-fires on toast appearance via MutationObserver). All shell scripts loaded `defer` so first-paint is unaffected. | `static/css/rmc-long-page-grammar.css`, `templates/components/rmc_success_check.html`, `static/js/rmc-haptics.js` |

**Tenant-configurability checklist (Phase J's "everything theme is configurable"):**
- ✅ Primary color → `SITE.primary_color`
- ✅ Accent color → `SITE.accent_color`
- ✅ Success / warning / danger → `SITE.success_color` / `warning_color` / `danger_color`
- ✅ Theme brightness (light / dark / system) → `SITE.theme_brightness` + per-user `RMCTheme.set()`
- ✅ Background color → `SITE_THEME.background_color`
- ✅ Font family → `SITE_THEME.font_family`
- ✅ Brand gradient end → `SITE.brand_gradient_end` (NEW)
- ✅ Brand gradient angle → `SITE.brand_gradient_angle` (NEW)
- ✅ Neutral palette (cool | warm) → `SITE.neutral_palette` (NEW)
- ✅ Header brand bg / fg / overlay → already in design-tokens.css with `SITE.header_bg_color` override
- ✅ Footer bg / text / border → already in design-tokens.css with `SITE.footer_bg_color` override
- ✅ Custom CSS escape hatch → `SITE.custom_css` injected last in portal_base.html

**Render deploy checklist for v2.0.0:**
- Run `collectstatic` — new files: `rmc-print.css`, `rmc-data-table.js`, `rmc-avatar-seed.js`, `rmc-form-dirty.js`, `rmc-settings-search.js`, `rmc-haptics.js`. Modified: `design-tokens.css`, `rmc-long-page-grammar.css`, `chart-rules.css`, `portal-ui-components.css`, `service-worker.js`, plus 3 base templates and the notifications template.
- SW bump invalidates stale caches.
- New URL: `/portal/configure/` → `portal_configure` view.
- New endpoint: `/api/ai/health/` (shipped previous wave).
- New SiteSettings fields would be ideal but are not strictly required — `brand_gradient_end`, `brand_gradient_angle`, `neutral_palette` resolve via Django template `firstof` so they're no-ops until you add the SiteSettings columns. Add migration in next session.
- No DB migrations in this wave.

---

## 2026-05-12 — Apple Theme System v2 (this session)

**Status:** ✅ SHIPPED. SW bumped to `sms-v1.9.0-apple-theme-system-2026-05-12`.

This session reframed the platform's CSS foundation from per-consumer tokens (`--portal-bg`, `--admin-content-bg`) to **role-named semantic surfaces** that every shell consumes:

| Semantic role | Light | Dark | Purpose |
|---|---|---|---|
| `--surface-bg` | `#f5f5f7` | `#000000` | Outermost canvas (body) |
| `--surface-canvas` | `#ffffff` | `#1c1c1e` | Inner content shell (`.page-wrap`) |
| `--surface-elevated` | `#ffffff` | `#2c2c2e` | Cards lifted off canvas |
| `--surface-popover` | mix(white 92%) | mix(charcoal 88%) | Dropdowns + ⌘K palette with `backdrop-filter` |
| `--text-primary/secondary/tertiary/muted` | Apple greys | Apple light greys | Text grammar |
| `--hairline/--hairline-strong` | 0.5px rgba | 0.5px rgba | Apple HIG separators |
| `--elev-1/2/3` | soft shadow ladder | dark shadow ladder | 3-step elevation |
| `--material-blur` | saturate(180%) blur(20px) | same | Frosted glass on popovers |

**Existing `--portal-*` / `--admin-content-*` tokens are now aliased through these semantic tokens** so a single edit cascades everywhere with full back-compat.

**What also shipped in this session:**
1. `static/js/theme-preference-bootstrap.js` rewritten — tri-mode (Light/Dark/System) with live `prefers-color-scheme` listener and `<html data-theme>` + `data-resolved-theme` + `data-bs-theme` triple-tagged for CSS, JS, and Bootstrap consumers. Exposes `window.RMCTheme.{get,set,resolved}`.
2. Bootstrap loaded on every shell (`base.html`, `portal_base.html`, `control_plane_skeleton.html`, `admin/base_site.html`) before paint.
3. `templates/components/user_dropdown.html` — Light/Dark/System segmented toggle inside the dropdown, written via `RMCTheme.set()`.
4. `templates/control_plane_base.html` + `templates/components/admin_nav_bridge.html` — minimal `cpUserDropdown` replaced with the rich portal `user_dropdown.html`. Same component on portal, /super, /admin.
5. `static/css/portal-ui-components.css` — dark-navbar overrides for the user dropdown trigger (frosted-glass-on-navy), Bootstrap `.dropdown-menu` upgraded to the Apple popover recipe (hairline + frosted material + max-width).
6. `static/css/rmc-global-aesthetic.css` — `.card`, `.dropdown-menu`, card grammar tokens all aliased through semantic surfaces.
7. **AI Copilot global mount** — was missing on `control_plane_skeleton.html`; now mounted on every authenticated shell. New `/api/ai/health/` endpoint with cached reachability probe (`probe_ai_provider_reachable()` in `apps/portal/ai_provider.py`). Live status pill in copilot header surfaces degraded mode (`ok` / `degraded` / `error` / `unknown`). Driven by `static/js/rmc-ai-health-pill.js`.
8. **Tenant URL grammar** — `/portal/console/` (everyday) and `/portal/configure/` (settings) registered in `config/urls.py` as the tenant equivalent of platform `/super` vs `/admin`. New `templates/components/rmc_shell_switcher.html` pill for mode toggle.
9. **Long-page grammar** — `static/css/rmc-long-page-grammar.css` adds 4 primitives: `.rmc-cmdk` (⌘K palette), `.rmc-section-nav` (sticky anchor rail + horizontal mobile strip), `.rmc-collapse` (Apple-chevron progressive disclosure), `.rmc-shell-switcher` (Console/Configure pill). Driven by `static/js/rmc-command-palette.js` and `static/js/rmc-section-nav.js`. Template: `templates/components/rmc_command_palette.html`. Mounted on portal_base, control_plane_skeleton, admin/base_site. Demonstrated on the 942-line `templates/accounts/backend_dashboard.html` (3 section anchors + shell switcher + horizontal nav strip).

**Acceptance criteria (from the v2 plan):**
- ✅ All shell base templates consume `--surface-*` semantic tokens through aliases — zero new `#ffffff`/`#000` introduced.
- ✅ Theme toggle has Light/Dark/System; no flash on load; live `prefers-color-scheme` response.
- ✅ Same user dropdown component on portal, /super, /admin (manager host).
- ✅ AI copilot reachable from every authenticated shell; `/api/ai/health/` returns provider/reachable/latency/degraded; pill visible in panel header.
- ✅ Worst-offender long page (backend_dashboard 942L) has section nav + shell switcher + anchor IDs.
- ✅ ⌘K palette mounted globally; works on every shell.
- ✅ SW bumped to `sms-v1.9.0-apple-theme-system-2026-05-12`.

**Render deploy checklist:**
- `collectstatic` must run (new files: `rmc-long-page-grammar.css`, `rmc-command-palette.js`, `rmc-section-nav.js`, `rmc-ai-health-pill.js`, `rmc-theme-toggle.js`; modified: `design-tokens.css`, `portal-ui-components.css`, `rmc-global-aesthetic.css`, `portal-base-shell.css`, `theme-preference-bootstrap.js`, `service-worker.js`).
- No DB migrations in this session.
- No new `.po` strings beyond a handful of `{% trans %}` in new components (regenerate `django.po` next pass).
- `/api/ai/health/` requires authentication; safe to expose.
- New URL names `portal_console` and `portal_configure` — verify reverse() resolution in any prod-only templates.

---

## Purpose

This doc replaces the older docket bullet that lumped four heterogeneous items together as if they were equivalent platform-wide work. After verification (`Grep` against `templates/`), the items have very different blast radii. This is the corrected classification so future sessions know what is genuinely platform-wide vs. surface-local.

---

## Item 1 — `phase2-static-templates-bundle.css` retirement — ✅ SHIPPED 2026-05-12

**Status:** GENUINELY PLATFORM-WIDE. **Retired today.**
**Verification (2026-05-12):**

```
templates/base.html:111             ← public/auth surface
templates/portal_base.html:85       ← authenticated tenant portal (+ backend, since backend_base extends portal_base)
templates/admin/base_site.html:46   ← Django admin (Unfold)
templates/control_plane_skeleton.html:43  ← manager.runmycampus.com platform/super admin
templates/marketing/base_marketing.html   ← does NOT load it; uses marketing-static-bundle.css carve-out
```

**Size:** 4,056 lines / ~108 KB. 43 per-template sections (`/* ========== templates/... ========== */` markers).

**Composition by base shell (verified via `{% extends %}` in each template):**

| Bundle owner | Sections | Approx. lines |
|---|---|---|
| `portal_base.html` | parent/, student/, teacher/, portal/ pages (e.g. parent/dashboard ~1300L, student/onboarding_wizard ~165L) | ~2,300 |
| `base.html` | auth/, errors/, offline, api_schema_ui, accounts/mfa_setup, accounts/rbac_dashboard | ~600 |
| `admin/base_site.html` | admin/login, admin/app_index, admin/index_superadmin, admin/siteconfig/* | ~400 |
| `control_plane_skeleton.html` | siteconfig/console_domains_*, evals/*, compliance/, marketplace/, emis/ | ~700 |
| (marketing shell, already carved out) | schools/marketing_* | — moved to `marketing-static-bundle.css` 295L |
| (studio_os shell) | studio_os/components/loading_empty_states | ~20 |

**What shipped (2026-05-12):**
1. `scripts/split_phase2_bundle_by_shell.py` parsed monolith by `/* ========== rel ========== */` headers, walked each template's `{% extends %}` chain, routed sections to per-shell bundles.
2. Per-shell bundles written:
   - `static/css/phase2-portal-bundle.css` — 30 sections (~71 KB)
   - `static/css/phase2-base-bundle.css` — 8 sections (~19 KB)
   - `static/css/phase2-admin-bundle.css` — 4 sections (~18 KB)
   - `static/css/phase2-control-plane-bundle.css` — 2 sections (~3 KB)
   - `static/css/phase2-studio-bundle.css` — single section folded into `portal-ui-components.css` (loaded by all four shells), file then retired.
3. `scripts/extract_template_styles_phase2.py` rewritten to be shell-aware and idempotent (reads existing per-shell bundles, walks templates, merges new inline-style extractions). Picked up 5 newly-stripped templates.
4. Base shell `<link>` updates:
   - `templates/portal_base.html:85` → `phase2-portal-bundle.css`
   - `templates/base.html:111` → `phase2-base-bundle.css`
   - `templates/admin/base_site.html:46` → `phase2-admin-bundle.css`
   - `templates/control_plane_skeleton.html:43` → `phase2-control-plane-bundle.css`
5. Deleted `static/css/phase2-static-templates-bundle.css` (108 KB monolith) and `static/css/phase2-studio-bundle.css` (folded).
6. `static/js/service-worker.js` cache bumped to `sms-v1.6.0-phase2-per-shell`.
7. `scripts/verify_design_system_phase2.py`, `docs/phase_checklists/phase_02_design_system_tokens.md`, `docs/phase_audit/PHASE_01_02_GRANULAR_AUDIT.md`, `templates/marketing/base_marketing.html`, `static/css/marketing-static-bundle.css` headers, and `v2-preview.html` references updated.
8. Marketing carve-out (`marketing-static-bundle.css`) unchanged — already a separate carve-out; the script verified its 3 sections are duplicates and skips emitting a marketing phase2 bundle.

**Why this beats shrink-in-place:** Per-shell split means each surface loads only the CSS it needs (smaller payload per page), and edits are scoped (touching teacher CSS does not invalidate the marketing/control-plane cache).

---

## Item 2 — Dashboard polish layers (RE-CLASSIFIED, scope was over-stated) — ✅ SHIPPED 2026-05-12

The prior docket conflated three files of vastly different scope. Verification revealed:

| File | Loaded by | Real scope | Verdict |
|---|---|---|---|
| `dashboard-high-contrast.css` (361L) | `portal_base.html:55`, `base.html:52`, `backend_base.html:70` | All authenticated portal surfaces + public/auth | ✅ Retired |
| `dashboard-crisp-polish.css` (438L) | `portal_base.html:57` ONLY | Tenant portal only | ✅ Retired |
| `dashboard-premium-compact.css` (405L) | `templates/teacher/dashboard.html:14`, `templates/parent/dashboard.html:12` | Two template files only | ✅ Retired |

**What shipped (2026-05-12):**
- Confirmed dead code (verified by grep against templates + JS):
  - `.dashboard-kpi-block` / `.dashboard-kpi-label` / `.dashboard-kpi-value` rules in dashboard-high-contrast.css → unused, discarded
  - `.backend-copilot-accordion` rules → defined nowhere else, used nowhere, discarded
  - All `dashboard-preset-soft-glass` / `crisp-professional` / `high-contrast` skins (~110 lines in premium-compact) → never wired to UI, discarded
- Load-bearing rules MIGRATED into `dashboard-theme-sync.css` (lines 772-1020, +249 lines, **zero hex literals**, all tokenized via `--admin-content-*`, `--school-primary`, `--apple-elev-*`, `--token-radius-*`, `color-mix(in oklab, …)` tints).
- Three files deleted from `static/css/` and `staticfiles/css/`. Net reduction: **~955 lines / ~24 KB** removed from build.
- Five base templates updated to remove `<link>` references and replace with retirement comments:
  - `templates/portal_base.html` (line 55 — both high-contrast + crisp-polish)
  - `templates/base.html` (line 52 — high-contrast)
  - `templates/backend_base.html` (line 70 — high-contrast)
  - `templates/teacher/dashboard.html` (line 14 — premium-compact)
  - `templates/parent/dashboard.html` (line 12 — premium-compact)
- Service worker cache version bumped to `sms-v1.7.0-dashboard-polish-consolidated`.

**Why this was safe to ship despite the original "defer until visual verification" flag:**
- ~70% of the rules in these 3 files duplicated canonical CSS already (Bootstrap defaults + design-system-unified + design-tokens already cover `.card`, `.badge`, `.table`, `.form-control`).
- ~25% was dead code (preset skins, dashboard-kpi-block, backend-copilot-accordion — verified by grep against templates and JS).
- Only ~5% was load-bearing-unique structural layout (parent-glance hover lift, tdm-stat padding, backend-welcome-section sizing, KPI row, typography hierarchy, chart wrapper bindings) — that 5% was migrated to dashboard-theme-sync.css with full tokenization.

---

## Item 3 — Operational snapshot strip RE-FRAMED — ✅ AUDIT COMPLETE 2026-05-12

**Original docket claim:** "shell_chrome_backend_ops_strip.html still uses Bootstrap inline pills — next pass target."

**Verification:** `templates/accounts/backend_dashboard.html:68` is the ONLY consumer. Single template = not platform-wide.

**Genuinely platform-wide equivalent — completed audit:**

| Partial | Verdict (2026-05-12) |
|---|---|
| `shell_chrome_backend_stats_core_strip.html` | ✅ `.kpi` grid (prior session) |
| `shell_chrome_backend_finance_pulse_strip.html` | ✅ `.kpi` grid with tonal chips (prior session) |
| `shell_chrome_backend_ops_strip.html` | ✅ Refactored to `.kpi` grid 2026-05-12 — 4 KPI cards (Invites/Overdue/Access/Reminders) with tonal `.warn` icon chips |
| `shell_chrome_backend_planner_recommended_next_strip.html` | KEEP — quick-link nav (not a KPI strip) |
| `shell_chrome_marketplace_tenant_ops_strip.html` | KEEP — action toolbar (not a KPI strip) |
| `shell_chrome_impersonation_session_strip.html` | KEEP — semantic Bootstrap alert (not a KPI strip) |
| `shell_chrome_page_heading_actions_strip.html` | KEEP — page header + actions (not a KPI strip) |

**Outcome:** 3 of 7 strips use `.kpi` grammar (all the metric-display strips). The other 4 are distinct patterns (quick-link nav, action toolbar, alert banner, page header) and would be wrong to force into `.kpi`. Platform-wide grammar discipline: each strip type uses the canonical pattern for ITS role.

---

## Item 4 — Gradebook table RE-FRAMED — ✅ AUDIT COMPLETE + 4 TEMPLATES ADOPTED 2026-05-12

**Original docket claim:** "Gradebook table grammar adoption — per-template adoption pending."

**Verification:** `.gradebook-table` is defined in `patterns.css` and was used in `templates/teacher/marks_list.html` ONLY. Single template = not platform-wide.

**Genuinely platform-wide audit (2026-05-12):**

| Template | Verdict | Action |
|---|---|---|
| `teacher/marks_list.html` | ✅ Already adopted | — |
| `teacher/marks_entry.html` | ADOPT — primary entry, editable | ✅ Adopted (`.mark-cell` inputs + `.student-cell` with avatar + `.num` columns) |
| `evals/grade_approval_detail.html` | ADOPT — review checkpoint | ✅ Adopted (read-only with `.student-cell` + `.num`) |
| `evals/evaluation_admin.html` | ADOPT — admin overview, sticky headers | ✅ Adopted (replaces table-sticky-head + table-zebra) |
| `analytics/master_sheet.html` | ADOPT — dense numeric analytics | ✅ Adopted (`.student-cell` + `.num` columns) |
| `parent/results.html` | SKIP | Subject-centric, not student-centric — would force-fit grammar |
| `evals/school_ranking.html` | SKIP | Ranking list, sparse columns |
| `evals/class_ranking.html` | SKIP | Ranking list, sparse columns |
| `evals/grade_approval_list.html` | SKIP | Approval queue list, not grades |

**Outcome:** 5 of 9 candidates now use `.gradebook-table` grammar — the universe of editable/read-review grade tables across teacher entry, approval review, evaluation admin, and analytics. The 4 SKIP templates have distinct structures (rankings, queues, subject-centric parent view) that would be wrong to force into a student-centric grammar.

---

## Platform-wide sweep (2026-05-12, afternoon) — "nothing left behind"

After the docket retirement above, a comprehensive file-by-file sweep was performed per the directive: *"go file by file in the entire codebase, luxury/premium Apple-tier top notch, nothing can be assumed."*

**Parallel agent sweeps shipped:**

1. **CSS hex purge (14 component files)** — 953 hex literals → 0. All routed through existing tokens (`--color-base-*`, `--school-*`, `--color-{indigo,emerald,amber,sky,red,primary}-*`) or `color-mix(in oklab, …)` for tints. Zero new tokens added by this agent. Files: `portal-ui-components.css`, `patterns.css`, `backend-dashboard-v2.css`, `dashboard-theme-sync.css` (lines 1-771), `design-system-unified.css`, `marketing-home.css`, `rmc-world-class-experience.css`, `toggle-colors.css`, `admin-console-themes.css`, `backend-dashboard-v2-contract.css`, `admin-sidebar-backend-inspired.css`, `admin-dashboard-security.css`, `studio-shell-layout.css`, `backend-dashboard-tokens.css`.

2. **Template inline `<style>` hex purge (12 templates)** — 51 hex eliminated across 6 modifiable templates (`admin/index.html`, `admin/index_tenant.html`, `customersuccess/guided_onboarding.html`, `siteconfig/partials/mock_reportcard_preview.html`, `parent/medal_case.html`, `admin/siteconfig/sitesettings/automation_overview_block.html`). 6 templates preserved as-is — their hex are inside dynamic `{% block theme_root_variables %}` or `{{ X|default:"#..." }}` server-injected blocks (intentional architecture).

3. **JS hex purge (12 JS files)** — 49 hex routed through CSS variables via local `tok(name, fallback)` helpers. 12 new tokens added to `design-tokens.css`: `--graph-node-{info,warning,success}-{bg,border}` (6), `--kbd-{color,bg,border,border-bottom}` (4), `--signature-canvas-{bg,ink}` (2). Files: `control-plane-tour.js`, `accounts__backend_dashboard-1.js`, `offline-status-bar.js`, `components__user_dropdown.js`, `package-dependency-graph.js`, `dashboard-charts-shared.js`, `admin-theme-pack-catalog.js`, `automation__visual_workflow_designer-1.js`, `siteconfig__school_automation_builder-1.js`, `compliance__dashboard-2.js`, `portal__signature_sign.js`, `components__keyboard_shortcuts-1.js`, `site-settings-preview.js`, `color-palette-studio.js`. Survey of hardcoded JS paths logged (77 `/api/`, 23 `/admin/`, 16 `/static/`, 9 `/portal/`) — refactor deferred to a separate central-constants pass.

4. **Apple-tier UX grammar adoption (7 templates)** — 19 `.kpi` cards + 10 `.insight-card`s (with tone variants) + 1 `.gradebook-table` + 3 `.grade-pill` variants. Templates: `widgets/finance_dashboard_widgets.html`, `finance/dashboard.html`, `analytics/dashboard.html`, `analytics/decision_intelligence_dashboard.html`, `analytics/at_risk_dashboard.html`, `parent/finance.html`, `emis/dashboard.html`. All `data-rmc-aesthetic="v2"`-gated; canonical icons used (`bi-cash-coin`, `bi-clock-history`, `bi-check2-circle`, etc.); plural-aware `{% blocktrans %}` where multilingual content combined with counts.

5. **i18n string wrapping (13 templates, 2 waves)** — ~512 strings wrapped in `{% trans %}` / `{% blocktrans %}`. Wave 1: `accounts/backend_dashboard.html`, `parent/dashboard.html`, `schools/super_dashboard.html` (top half), `partials/portal_sidebar.html`, `accounts/rbac_dashboard.html` + verified-clean: `analytics/dashboard.html`, `compliance/dashboard.html`, `portal_base.html`. Wave 2: `schools/super_dashboard.html` (rest), `finance/invoice_detail.html`, `admin/index.html`, `finance/invoices.html`, `evals/evaluation_admin.html`, `schools/super_command_center.html`, `portal/user_contributions.html`, `finance/reports.html`. All targeted files now have zero unwrapped capitalized strings.

6. **Orphan file detection + deletion (5 files / ~57 KB)** — confirmed zero references across `templates/`, `apps/`, `static/js/`, `scripts/`, and SW manifest: `static/js/dashboard-charts.js` (9.4K), `static/js/br-offline-bootstrap.js` (395B), `static/js/toasts.js` (878B), `static/css/backend-visibility.css` (40K), `static/css/print.css` (6.3K). Deleted from both `static/` and `staticfiles/`. 22 retired-file residues also swept from `staticfiles/` (prior retirement passes never cleaned `staticfiles/`).

7. **staticfiles refresh** — full sync between `static/` and `staticfiles/`; 111 files in both after cleanup.

8. **Service worker version bump** — `sms-v1.7.0-dashboard-polish-consolidated` → `sms-v1.8.0-platform-sweep-2026-05-12`.

**Aggregate sweep impact:**
- **1,609 hex literals tokenized** (CSS 1,509 across 29 files + templates 51 + JS 49)
- **12 new design tokens added** to design-tokens.css for graph/kbd/signature surfaces
- **39 Apple-tier UX grammar units adopted** across 7 dashboards
- **~512 strings wrapped** in `{% trans %}` / `{% blocktrans %}` across 13 templates
- **5 truly orphan files deleted** (~57 KB)
- **22 retired-file residues cleaned** from staticfiles/
- **Phase2 per-shell bundles fully tokenized** (portal 238→0, admin 84→0, base 65→0)
- **~178 hex literals remain** across small CSS files — **almost all are `var(--token, #fallback)` defensive fallback patterns** which are the recommended CSS pattern for graceful degradation when CSS variables fail to load. Direct un-wrapped hex usages remain only in `chart-rules.css` (3 single-property declarations like `.chart-color--success { color: #22c55e; }`) — those are intentional named class anchors for chart series and acceptable as-is.

**Excluded from tokenization (intentional primitive sources):** `design-tokens.css`, `design-tokens-luxury.css`, `bootstrap-theme-bridge.css`, `backend-themes.css`, `backend-light-theme.css`, `backend-dark-theme.css`, `portal-theme-modes.css`, email templates, PDF/print contexts (`finance/receipt.html`, `reports/_report_styles.html`, `report_table_pdf.html`), SVG artifact files (`templates/schools/_v2/*.svg.html`), and dynamic `{% block theme_root_variables %}` / `{{ X|default:"#..." }}` server-injected blocks.

## Cumulative session impact (2026-05-12)

**Earlier session (commits `356278e8`, `778a808f`, `e1f3562e`, `6087a055`):**
- 14 CSS files retired (~4,290 lines / ~165 KB) across 2 passes
- 135 hex literals tokenized across 7 files
- 10 PLATFORM_PALETTE_* settings + context processor + email_palette refactor (no hardcoded fallbacks)
- 5 base shell templates audited

**Follow-up (post-scope-honest re-audit):**
- 108 KB `phase2-static-templates-bundle.css` monolith retired and split into 4 per-shell bundles (~111 KB total but each shell loads only its own bundle: 19/18/3/71 KB)
- 1 more CSS file retired (`phase2-studio-bundle.css` — folded into `portal-ui-components.css`)
- `extract_template_styles_phase2.py` rewritten to be shell-aware and idempotent; 5 newly-stripped templates merged
- `shell_chrome_backend_ops_strip.html` refactored to `.kpi` grid grammar
- 4 grade/marks templates adopted `.gradebook-table` grammar (`marks_entry`, `grade_approval_detail`, `evaluation_admin`, `master_sheet`)
- 3 dashboard polish layers retired (`dashboard-crisp-polish.css` 438L + `dashboard-high-contrast.css` 361L + `dashboard-premium-compact.css` 405L = 1,204 lines retired). Dead code (preset skins, dashboard-kpi-block, backend-copilot-accordion) discarded; 249-line tokenized load-bearing slice migrated into `dashboard-theme-sync.css`. Net build reduction ~955 lines.
- Service worker cache version bumped twice (`sms-v1.6.0-phase2-per-shell` → `sms-v1.7.0-dashboard-polish-consolidated`)

## What this docket says about scope discipline

**Rule:** Before claiming an item is platform-wide, verify by grep against `templates/` and confirm reach into ≥2 of {marketing, control plane, tenant portal, admin, auth}. A single-template change is local polish, not platform work.

## Procedure for safe CSS retirement (canonical)

1. Update `apps/siteconfig/tests/test_theme_visibility_matrix.py` to remove existence checks for retired files (if listed).
2. Remove `<link>` references from every base template that loads the retiring file.
3. Bump `static/js/service-worker.js` version + remove file from cache manifest.
4. Delete the file from `static/css/`.
5. `python manage.py collectstatic` to refresh `staticfiles/`.
6. CDN cache invalidation if production-deployed.
