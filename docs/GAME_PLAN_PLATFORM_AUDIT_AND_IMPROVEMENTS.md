# Game Plan: Platform Audit & Improvements

**Context:** School management platform for Cameroon, designed to be flexible for use anywhere. Goals: professional look, easy to use, right-sized data, no wasted space, accessible transitions.

---

## 1. What We’re Doing Well

- **Region-first design:** `RegionConfig`, grading scales, holidays, timezone, currency (XAF, USD, EUR, etc.) and “Cameroon Anglophone/Francophone” as defaults make it easy to add new regions. Reports and emails already use region/language.
- **Unified design system:** `design-system-unified.css` defines spacing, radius, shadows, and a clear color palette. Admin and portal can share the same tokens.
- **Role-based dashboards:** Separate flows for Teacher, Parent, Staff with workflow centers, KPIs, and quick actions. Dashboard view preference (Overview vs Workflow) is persisted.
- **Admin customization:** SiteSettings (primary color, favicon, logo), admin sidebar colors, backend console theme (dark/light), and ThemePack give schools control over look and feel.
- **Collapsible Recent Activity:** Sidebar activity block is collapsible with persisted state; no duplicate IDs when sidebar is included twice (desktop + mobile).
- **Static portal sidebar:** Single, predictable nav (no duplicate entries); sections by role are clear.
- **Documentation:** Many docs (theme plan, workflow, i18n, setup new school) support onboarding and future work.

---

## 2. Gaps

| Area | Gap | Impact |
|------|-----|--------|
| **Currency/locale in UI** | Hardcoded `$` in some parent dashboard copy (e.g. “${{ widget_data.finance.balance }}”); not all templates use `region.default_currency` or a format helper. | Cameroon (XAF) and other regions see wrong symbol and formatting. |
| **i18n** | Many strings are in English only; `{% load i18n %}` and `{% trans %}` are not used consistently. | Limits use in French-speaking Cameroon and other locales. |
| **Reduced motion** | No `prefers-reduced-motion` handling for transitions/animations. | Can hinder readers with vestibular or motion sensitivity. |
| **Card size standards** | Teacher/parent dashboards mix large hero cards, big KPI blocks, and dense tables without a shared “card size” system. | Inconsistent density and wasted space. |
| **Admin sidebar vs portal** | Admin uses Django’s #nav-sidebar + custom CSS; portal uses a different sidebar partial. No single “sidebar component” contract. | Theming and behavior can drift. |
| **Dashboard layout flexibility** | Backend has drag-and-drop; teacher/parent are fixed. “Different dashboard views” exist (Overview/Workflow) but not alternate layouts (e.g. compact vs spacious). | Less flexibility for different screen sizes and preferences. |
| **Single source for transitions** | Transitions and keyframes live in many CSS files (admin_sidebar_enhanced, admin-components, backend_dashboard, portal_theme, etc.). | Inconsistent timing; harder to tune or disable for accessibility. |

---

## 3. Redundancy & Closing the Loop

- **Duplicate CSS tokens:** `admin/base_site.html` injects `--admin-sidebar-*` from SiteSettings; `admin_sidebar_enhanced.css` defines its own `:root` defaults. **Close loop:** One source (e.g. design-system or a single “admin-vars” partial) that base_site and admin_sidebar_enhanced both use; avoid redefining the same variables in two places.
- **Card styles in multiple templates:** Teacher dashboard, parent dashboard, and backend dashboard each define their own `.card`, `.metric-card`, `.stat-card`, `.donut`, etc. **Close loop:** Move shared card/chart patterns into `design-system-unified.css` or a small `dashboard-cards.css` (e.g. `.kpi-card`, `.kpi-card--compact`, `.kpi-value`) and have all dashboards use them.
- **Hero / welcome block:** Teacher and parent dashboards each have a custom hero + “My Workflow” CTA. **Close loop:** Reuse `widgets/dashboard_hero.html` and one “primary CTA” pattern so copy and layout stay consistent.
- **Sidebar styling:** Portal sidebar has a large `<style>` block in `partials/portal_sidebar.html`; admin sidebar is in `admin_sidebar_enhanced.css`. **Close loop:** Portal sidebar could use design-system variables and a single “sidebar.css” (or shared partial) so colors and spacing stay aligned with the rest of the app.
- **Activity list rendering:** Backend fetches activities via API and injects into `.recent-activity-list`; server-side `recent_activities` is also used in the same partial. **Close loop:** Prefer one path (e.g. always API for backend, or always server-side with optional refresh) and one HTML structure so we don’t maintain two formats.

---

## 4. Admin Sidebar & Theme Improvements

- **Single source for admin theme:** Drive all admin sidebar and header colors from SiteSettings (or a single “admin theme” object) and inject once (e.g. in base_site) so `admin_sidebar_enhanced.css` only uses variables and doesn’t override with new `:root` blocks.
- **Collapsible groups:** Admin sidebar already has accordions per app; ensure section headers are clearly clickable and that collapsed state is obvious (icon + aria-expanded).
- **Admin light theme contrast:** `:root[data-theme="light"]` in admin_sidebar_enhanced uses dark surfaces (#111827, #1f2937); name or adjust so “light” doesn’t feel dark. Consider a true light variant (e.g. #f8fafc background, dark text).
- **Admin “Jump to model” search:** Keep it; consider moving it into a small, persistent toolbar so it’s visible even when the sidebar is collapsed.
- **Consistency with portal:** If the portal uses “Backend Console” and “Workflow Center,” admin branding (site name, logo) should match so users don’t feel they’re in a different product. Reuse the same favicon and primary color from SiteSettings in both.

---

## 5. Fade Effects & Transitions — Visible vs Hindering

- **Current usage:** Transitions and keyframes are used for: card hover (`translateY(-2px)` / `-4px`), sidebar collapse, command palette (fadeIn, slideDown), modals, and some list animations. Many are short (0.2s–0.3s).
- **Risks:** Hover lift on every card can feel busy on dense dashboards; repeated motion can distract or hinder readers. Opacity fades (e.g. 0.5 for disabled) can reduce legibility if overused.
- **Recommendations:**
  - **Respect `prefers-reduced-motion`:** In a single “motion” or “design-system” CSS file, add `@media (prefers-reduced-motion: reduce) { * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }` (or target only interactive elements) so motion is minimal when the user requests it.
  - **Keep transitions subtle:** Prefer 0.15s–0.25s for hover; avoid large `translateY` on heavy content. Use transitions for state change (expand/collapse, open/close) rather than decoration.
  - **Avoid fading body/main content:** Don’t add full-page fades for normal navigation; they slow comprehension. Use fades only for overlays (modals, command palette, dropdowns).
  - **Document:** In ACCESSIBILITY.md or ux.md, note that motion is optional and reduced-motion is supported.

---

## 6. Teacher & Parent Dashboards — KPIs, Card Size, Layout

- **Teacher dashboard:** Uses `hero_stats`, three KPI cards (Attendance, Completion, At a glance), then “class at a glance” + schedule. Cards are `col-md-4` with donuts and text. Some cards are tall (e.g. “Teaching assignments” table). 
  - **Improve:** (1) Define a compact KPI card size (e.g. one line: label + value + optional sparkline) and use it for secondary metrics so the first row doesn’t dominate. (2) Cap “At a glance” to 3–4 chips or a single line. (3) Use a consistent grid (e.g. 2–4 columns for KPIs, then one main + one side column) so the fold fits “glance + next actions” without excess scroll. (4) Allow “compact” density (smaller padding, smaller donuts) from user preference or tile_variant.
- **Parent dashboard:** Large hero, multiple sections (children cards, family overview, activity, finance, announcements). Summary tiles and metric cards use different min widths (180px, 260px) and font sizes (1.1rem–2rem). 
  - **Improve:** (1) Standardize KPI value size: e.g. one “primary” value size (1.25rem–1.5rem) and one “secondary” (0.9rem). (2) Use a single “summary tile” component with optional compact variant so “Children / Attendance / Avg grade / Outstanding” sit in one row without oversized boxes. (3) Make “Family Overview” and “child cards” use the same card component and spacing so the layout feels like one dashboard, not several stacked pages. (4) Ensure currency is formatted via region (symbol + decimals) everywhere.
- **Both:** (1) Ensure “Dashboard” vs “Workflow” view is clear (tab or toggle) and that default view is respected. (2) On small screens, stack KPI cards in one or two columns; avoid horizontal scroll. (3) Remove or shrink redundant “Welcome back” + big CTA if the same CTA exists in the sidebar; one primary entry point is enough.

---

## 7. Flexibility — Cameroon to Anywhere

- **Already flexible:** RegionConfig (name, code, timezone, currency, grading scale, terms, holidays, portals), multi-language support in reports/emails, and “default region” with fallback. Adding a new country is largely “new RegionConfig + optional locale.”
- **To strengthen:** (1) **Currency everywhere:** Template filter or context variable, e.g. `{{ value|currency:region }}`, used for all money (parent fees, payroll, invoices). (2) **Date/time format:** Use `region.date_format` and `region.timezone` in templates and APIs so lists and reports show local time. (3) **Wording:** Move “Cameroon” references in UI (e.g. workflow tip “Fits Cameroon general and technical education”) into a configurable string or admin copy so another school sees “Fits your education system” or similar. (4) **Grading:** Grading scale is already per-region; ensure report cards and transcripts always use the selected region’s scale. (5) **Docs:** Keep SETUP_NEW_SCHOOL_WORLDWIDE.md and region admin docs up to date so deployers know how to add a region and switch defaults.

---

## 8. Dashboard Observations & Critiques (Detailed)

### 8.1 Teacher dashboard

- **Triple “My Workflow” entry:** Header (Welcome + “My Workflow” button), then a full-width bordered card (“My Workflow — Open workflow”), then “Use Workflow as default view.” Same CTA in three places; one clear primary entry (e.g. one prominent button or card) is enough.
- **Customization UI when disabled:** When `allow_custom_layout` is False, the whole drag-and-drop / shortcuts / tile density block is hidden, but the `#dashboard-layout` div and data attributes are still present. No issue functionally, but the template has two code paths (with/without customizer) that duplicate the rest of the dashboard.
- **Donut vs chip sizing:** Donuts are 86px in teacher CSS; parent uses 78px/90px in different sections. Inconsistent visual weight across roles.
- **“At a glance” density:** Four stat-chips (classes, students, pending evals, pending payments) can wrap to two lines and take more vertical space than the donut cards beside them. Could be one row of compact pills or a single line.
- **Finance inbox + finance_access_banner:** Both can show; if the user has no finance access, the banner explains it and the “Finance inbox” card can still appear for pending requests. Order and messaging could be clearer (e.g. one combined “Finance access” block).
- **Empty states:** “No teaching assignments found yet” vs “No data available” in attendance/completion; “No peers listed yet”; “No active threads.” Wording and tone are inconsistent; some sections have no empty state.
- **No loading state:** `widget_data` and assignments are server-rendered; there’s no skeleton or loading indicator. On slow networks the page can sit blank until full render.
- **Tile density:** `tileVariantSelect` (default/compact/flat) exists and is passed to the layout API, but teacher template doesn’t visibly apply compact/flat to the first KPI row (e.g. smaller padding/donuts). Backend uses `#dashboard-layout.tile-variant-compact` in CSS; teacher may not.

### 8.2 Parent dashboard

- **Repeated metrics in three places:** Summary tiles (Children, Attendance, Balance, Notifications) → then a row of donut cards (Attendance, Fees paid, At a glance) → then “Family Overview” card (Children, Attendance, Avg. Grade, Outstanding Fees). Same numbers in summary tiles and family overview; donuts add another layer. Consolidate to one “above the fold” summary and one detail area (e.g. donuts or family overview, not both).
- **Hardcoded currency:** `${{ widget_data.finance.balance }}`, `${{ finance_paid }}`, etc. in multiple spots. Must use region currency everywhere.
- **Conditional logic:** Many `{% if can_view_results and not widgets or can_view_results and "attendance" in widgets %}` (and similar for finance). Hard to read and easy to break when adding a new widget; consider a single “show_attendance”, “show_finance” (and optionally “widgets” filter) set in the view.
- **Child card CTAs:** Each child card has “Make Payment,” “History,” “View Details,” and sometimes certification/registration links. Many actions per card; consider one primary (“View” or “Details”) and secondary in a menu or smaller links.
- **“Performance” disabled:** “Performance” button is `btn-outline-success disabled` with `title="Performance view unavailable"`. No explanation in UI for why it’s disabled or when it will be available. Either add short copy or hide until available.
- **Empty states:** “No children linked to your account yet” vs “No linked students yet. Link a child to…” vs onboarding “Get Started” when `not links`. Multiple entry points and wordings; unify “no children” messaging and one primary onboarding path.
- **Hero actions:** `hero.actions` can duplicate “My Workflow” / “Manage notifications” that already sit in the header. Risk of duplicate links if hero is populated from the same source.

### 8.3 Backend dashboard (/authentication/backend/)

- **Long inline styles:** Large `<style>` block in the template (cards, trend-pills, modular-card, hero panels, log panel, tile variants). Hard to maintain and reuse; should move to a shared CSS file (e.g. backend-dashboard.css or design-system).
- **Welcome + recommended_next_steps + finance alerts:** Order is fixed; priority (e.g. “finance requests” vs “recommended next steps”) is not configurable. Some users may want alerts always first.
- **Floating log panel:** “Floating Admin Log Panel” is debug-style (fixed bottom-right). Useful for support but not core dashboard; consider making it optional or behind a toggle.
- **Header link overload:** Workflow Center, “Use Workflow as default,” Messages, Report Card Builder, plus optional hero actions. Many equal-weight links; one primary (e.g. Workflow) and the rest secondary or in a menu would clarify hierarchy.
- **Tile variants:** `.tile-variant-compact` and `.tile-variant-flat` only change padding and shadow on `#dashboard-layout .card`. Backend cards (trend-pills, modular-card) may not shrink; visual effect of “compact” can be weak.
- **No empty state for widget grid:** When there are no widgets or no data, the grid can look sparse; no “Add widgets” or “No data yet” message.

### 8.4 Admin dashboard (Django /admin/ index)

- **Different product from backend:** Django admin index (admin_dashboard.html / index.html) is a different UI (stats, app grid, theme toggle) than the portal “Backend dashboard.” Users can have two “home” experiences: /admin/ and /authentication/backend/. Naming and navigation (e.g. “Django Admin” vs “Backend Console”) help but the split is a source of confusion.
- **Stats grid:** `minmax(320px, 1fr)` creates few large cards on wide screens; cards can feel oversized. Consider a max width per stat card or more columns.
- **Hover lift:** `stat-card:hover` and `app-card:hover` use `translateY(-3px)` / `translateY(-4px)`. Same as elsewhere: consider reducing or respecting reduced-motion.
- **Theme toggle position:** Fixed `top: 80px; right: 20px` can overlap content on small screens or when the header is tall.
- **Inline styles in admin index:** Inline `:root` and body background from `SITE_ADMIN_THEME` / `SITE_ADMIN_BACKGROUND_URL`. Good for theming but duplicates the “admin theme variables” story; should align with base_site + design-system.

### 8.5 Cross-dashboard

- **Empty state component underused:** `components/dashboard_empty_state.html` exists (icon, title, message, action) but many dashboards use ad hoc “No … yet” or “No data available” instead. Standardize on the component for consistency and one place to tweak copy/design.
- **Skeleton loaders:** `components/dashboard_skeleton.html` defines student-list, cards, and table skeletons but dashboards don’t use them during load. Adding a short skeleton phase would improve perceived performance.
- **Heading hierarchy:** Multiple `<h2>` or section titles per page; order of `<h1>` (if any), `<h2>`, `<h3>` is not audited. Risk of skipping levels or multiple “main” titles; affects accessibility and SEO.
- **Custom links modal duplicated:** Teacher, parent, backend, analytics, finance each have a similar “Custom quick links” modal (label, URL, add, list). Could be one include or small component to avoid drift (e.g. placeholder “Ex: Finance” vs “Ex: Attendance”).
- **Widget visibility logic:** Parent (and partly teacher) use both `display_widgets` and `can_view_results` / `can_view_finance`. Conditions like “if can_view_results and not widgets or can_view_results and 'attendance' in widgets” are easy to misread. Centralize in the view: e.g. `show_attendance = can_view_results and (not display_widgets or 'attendance' in display_widgets)` and pass booleans to the template.

---

## 9. Consolidated Findings (Master List)

Everything above (Gaps §2, Redundancy §3, Admin/Sidebar §4, Transitions §5, KPIs §6, Flexibility §7, Dashboard critiques §8) in one checklist. Use this to track progress and decide what to tackle next.

| # | Category | Item | Section |
|---|----------|------|---------|
| 1 | Gaps | Currency/locale: hardcoded `$`; need region-based formatting everywhere | §2, §8.2 |
| 2 | Gaps | i18n: many strings not under `{% trans %}` | §2 |
| 3 | Gaps | No `prefers-reduced-motion` for animations/transitions | §2, §5 |
| 4 | Gaps | No shared card/KPI size system across dashboards | §2, §6, §8 |
| 5 | Gaps | Admin sidebar vs portal: two implementations, no single contract | §2, §4 |
| 6 | Gaps | Dashboard layout: backend has drag-and-drop; teacher/parent fixed; no compact/spacious option | §2, §8 |
| 7 | Gaps | Transitions scattered across many CSS files; no single source | §2, §5 |
| 8 | Redundancy | Admin theme variables in base_site and admin_sidebar_enhanced | §3, §4, §8.4 |
| 9 | Redundancy | Card/donut/stat styles duplicated in teacher, parent, backend templates | §3, §8 |
| 10 | Redundancy | Hero + “My Workflow” CTA duplicated (teacher, parent); triple entry on teacher | §3, §8.1, §8.2 |
| 11 | Redundancy | Portal sidebar `<style>` block vs admin_sidebar_enhanced.css | §3 |
| 12 | Redundancy | Activity list: API + server-side both used; two code paths | §3 |
| 13 | Dashboard | Teacher: triple Workflow CTA; donut/chip sizing; at-a-glance density; finance inbox + banner; inconsistent empty states; no loading | §8.1 |
| 14 | Dashboard | Parent: metrics in summary tiles + donuts + family overview; complex conditionals; child card CTAs; disabled Performance; multiple “no children” messages | §8.2 |
| 15 | Dashboard | Backend: long inline styles; fixed alert order; floating log panel; header link overload; weak tile variants; no widget empty state | §8.3 |
| 16 | Dashboard | Admin index: two “home” experiences (admin vs backend); stats grid sizing; hover lift; theme toggle overlap; inline theme vars | §8.4 |
| 17 | Dashboard | Cross-dashboard: empty state component underused; skeletons not used; heading hierarchy; custom links modal duplicated; widget visibility logic in templates | §8.5 |
| 18 | Flexibility | Currency filter/context; date format from region; configurable “Cameroon” copy; grading per region; docs | §7 |

---

## 10. Go Plan & How to Approach

### 10.1 How to approach things

- **One theme at a time.** Don’t refactor all dashboards in one go. Pick one surface (e.g. “parent dashboard” or “all KPI cards”) and finish it: tokens, layout, empty states, copy. Then move to the next.
- **Fix data and logic before layout.** Currency and widget visibility (view booleans) affect every parent/teacher screen. Add a `currency` filter and `show_attendance` / `show_finance` (and optional widget list) in the view first; then templates get simpler and layout changes are safer.
- **Shared components before one-off fixes.** Introduce one “KPI card” and one “empty state” include and use them everywhere you can. Reduces drift and gives one place to tune accessibility (e.g. reduced motion, contrast).
- **Test after each change.** Especially after: adding a CSS file used in multiple places, changing conditionals in parent/teacher views, and any change to admin/portal sidebar. Quick smoke test: load each dashboard (admin index, backend, teacher, parent) and one list/detail view.
- **Document as you go.** When you add `prefers-reduced-motion`, note it in ACCESSIBILITY.md. When you add a currency filter, add a line to the game plan or a “formatting” doc. Makes it easier for the next person and for you later.
- **Priorities can shift.** If a school needs i18n or compact layout first, swap phases. The master list (§9) is the full backlog; the phases below are a suggested order, not a lock.

### 10.2 Go plan — suggested sequence

**Step 0 — Foundation (before layout work)**  
- Add a `currency` template filter (or context helper) that takes amount + region and returns formatted string (e.g. `XAF 1,500` or `$1,500.00`). Use it in one place (e.g. parent finance card), then roll out to all parent/teacher/backend money.  
- In parent (and teacher if needed) views: compute `show_attendance`, `show_finance`, `show_performance` (and optionally which widgets to show) once; pass as booleans. Simplify templates so they don’t repeat long `can_view_* and not widgets or ...` conditionals.  
- Add `prefers-reduced-motion` in one central CSS file (e.g. design-system-unified.css or a new `accessibility.css`); document in ACCESSIBILITY.md.

**Step 1 — Quick wins (1–2 sprints)**  
- Replace all hardcoded `$` in parent (and anywhere else) with the new currency filter/helper.  
- Reduce hover lift on dense cards: in shared CSS or per-dashboard, change `translateY(-2px)` / `-4px` to `-1px` or none where it’s noisy; optionally scope under `prefers-reduced-motion: no-preference`.  
- Pick one “primary” Workflow entry per role: e.g. one prominent button in the header for teacher and parent; remove or shrink the extra “My Workflow” card and keep “Use as default” as a small link.  
- Unify “no children” / “no linked students” copy on parent dashboard and use `dashboard_empty_state.html` for the main empty state.

**Step 2 — Shared dashboard UI (2–3 sprints)**  
- Add a small “dashboard cards” layer: e.g. `.kpi-card`, `.kpi-card--compact`, `.kpi-value`, `.summary-tile` (and one donut size) in design-system-unified.css or dashboard-cards.css. Use it on teacher and parent for the first row of KPIs and summary tiles.  
- Use `dashboard_empty_state.html` everywhere a dashboard section can be empty (teacher assignments, parent children, backend widget grid, etc.). Standardize copy (“No … yet” + one action if relevant).  
- Extract backend dashboard inline styles into a static CSS file (e.g. backend-dashboard.css) and keep only layout-specific overrides in the template if needed.  
- Single source for admin theme: inject all admin sidebar/header variables once (e.g. in base_site) and make admin_sidebar_enhanced.css (and admin index) consume them only; remove duplicate `:root` blocks.

**Step 3 — Dashboard content & hierarchy (2–3 sprints)**  
- Parent: Consolidate metrics into one “above the fold” summary row (children, attendance, grade, fees) and one detail area (either donuts or family overview, not both). Use same card component for family overview and child cards. Simplify child card CTAs to one primary (“View” or “Details”) + secondary in a dropdown or smaller links.  
- Teacher: One row of compact KPIs (same card component); “At a glance” as one line of pills or 3–4 chips max; ensure tile-variant (compact/flat) applies to teacher KPI row if the API is already sending it.  
- Backend: One primary action in the header (e.g. Workflow Center); rest as secondary links or in a “More” menu. Add an empty state for the widget grid (“No widgets yet” or “Add widgets”). Optionally make the floating log panel a toggle so it’s not always on.  
- Admin index: Align theme variables with base_site; consider capping stat card width or adding columns so cards don’t get oversized; reduce or respect reduced-motion for hover.

**Step 4 — Cross-cutting & polish (ongoing)**  
- One “custom quick links” include (or component) for teacher, parent, backend, analytics, finance; same markup, one placeholder or config.  
- Optional: skeleton loaders — show `dashboard_skeleton.html` (or a thin variant) while dashboard data is loading, then swap in content.  
- Audit heading hierarchy (h1 → h2 → h3) on each dashboard and fix skips or multiple h1s.  
- Clarify “Django Admin” vs “Backend Console” in nav and docs so users know which is which.  
- i18n pass for critical strings; date/time from region in lists and reports; configurable “Cameroon” / country copy where it’s currently hardcoded.

### 10.3 Dependency order (what blocks what)

- **Currency filter** → unblocks parent (and any) dashboard cleanup and flexibility for other regions.  
- **View booleans (show_attendance, etc.)** → unblocks simplifying parent/teacher templates and widget logic.  
- **Shared KPI/summary card CSS** → unblocks consistent teacher/parent/backend layout and tile variants.  
- **Single admin theme source** → unblocks admin index and sidebar consistency without fighting duplicate variables.  
- **Empty state component** → unblocks consistent copy and one place to fix a11y/design.

You can do Steps 0 and 1 in parallel with one person on “data/formatting” (currency, view booleans, reduced-motion) and another on “UI quick wins” (hover, Workflow CTA, empty state copy). Step 2 is the right time to introduce shared dashboard cards and move backend styles; Step 3 then uses those pieces to tidy each dashboard. Step 4 is ongoing and can be picked up as needed.

---

## 11. Success Criteria (How to Know It’s Working)

- **Professional:** Same design tokens and card patterns across admin, backend, teacher, parent; no obvious “patchwork” of styles.  
- **Easy to use:** Primary action per screen is obvious; sidebar and workflow entry points are clear; no duplicate or conflicting CTAs.  
- **Right-sized:** KPIs fit in one or two rows on desktop; no unnecessarily tall cards for a single number; tables and lists are scannable.  
- **No wasted space:** Dashboard views (Overview, Workflow, compact) use space well; gaps are intentional (e.g. between sections), not leftover from inconsistent grids.  
- **Accessible:** Reduced motion supported; contrast and focus visible; currency and dates match the user’s region.  
- **Flexible:** A new school in another country can set a new region, currency, and timezone and see consistent formatting and wording without code changes.

---

*This game plan is a living document. Priorities can shift (e.g. i18n or compact layout first) depending on real usage and feedback from Cameroon and other schools.*
