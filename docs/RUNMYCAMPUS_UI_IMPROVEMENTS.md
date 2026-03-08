# RunMyCampus UI & Visual Improvements Backlog

Backlog of improvements and visual upgrades for the RunMyCampus platform (manager/super-admin) and tenant surfaces, including optional "powerhouse" upgrades.

**Status:** All previously backlog items in this doc are **Done**. Command palette (Ctrl+K), PDF export, and per-user saved layout (DB) are implemented. **High-end admin experience and platform-wide premium styling are in place:** Configuration Engine login matches /super (dark, gold, superadmin-only copy); `platform-high-end.css` is loaded on portal_base, control_plane_skeleton, admin base_site, and base.html so every sidebar, dashboard, card, and chart has consistent premium elevation and polish. See `docs/architecture/phase10_superadmin_vs_tenant_ui.md` § 8.6. Use the sections below as design guidance for future polish.

---

## 1. Layout & Information Architecture

- **F-pattern / North Star**: Place the single most important KPI in the **top-left** (e.g. Total MRR or total schools). Super dashboard uses this for the hero metric.
- **Above-the-fold**: Primary status and main actions visible without scrolling.
- **Progressive disclosure**: Expandable sections or "Show more" for dense blocks (e.g. revenue by country, long school lists).
- **Consistent grid**: 12-column grid and 8px (or 4px) spacing scale for cards and sections.

---

## 2. Visual Design (Navy/Gold "Powerhouse")

- **Navy + gold**: Navy as base (sidebar, header); gold/warm accents for primary CTAs, key numbers, and critical status.
- **Hierarchy**: One clear North Star number (size + color); secondary metrics smaller and more neutral.
- **Cards**: Clear label, prominent number, small context (e.g. "vs last month"); subtle shadows and consistent padding.
- **Typography**: 2–3 font styles; size/weight for primary metric, section titles, labels, captions.

---

## 3. From "Information" to "Action"

- **Next best action**: "Tasks" or "To-do" strip (e.g. pending approvals, trials ending soon) with links.
- **Empty states**: Where there's no data, show explanation + single CTA (e.g. "Create your first school").
- **Context on metrics**: Targets or comparison (e.g. "+12% vs last month") where possible.

---

## 4. Navigation & Wayfinding

- **Sidebar**: Collapsible left sidebar with labels + icons (not icons only).
- **Breadcrumbs**: On deep flows (e.g. school → domain → DNS).
- **Global search / Command palette**: Top-right search or Ctrl/Cmd+K for power users (future).

---

## 5. Charts & Data

- **Clarity over fancy**: Prefer line (trends), bar (comparisons), donut (few segments).
- **Sparklines**: Small inline trend lines in summary cards.
- **Labels**: Every chart has title, labeled axes, legend if needed; tooltips for exact values.

---

## 6. Performance & Polish

- **Load time**: Target <3s; skeleton loaders for dashboard sections.
- **Responsiveness**: Primary actions and key metrics work on tablet/phone.

---

## 7. Accessibility & Comfort

- **Dark mode**: Toggle + respect system preference; navy/gold in both themes on platform.
- **Contrast**: WCAG AA (e.g. 4.5:1) in both themes.
- **Keyboard**: Main actions reachable and focusable; visible focus styles.

---

## 8. RunMyCampus-Specific

- **Platform hero**: When `PUBLIC_BRAND_MODE` (manager), show RunMyCampus hero: logo, tagline ("The Powerhouse of School Management"), North Star metric.
- **Theme on manager**: Force navy/gold on manager/super-admin (override `--school-primary` / `--school-accent`).
- **Consistency**: Same navy/gold tokens in login hero, base navbar, backend sidebar, super dashboard.
- **"Powered by RunMyCampus"**: Only on tenant portals; never on manager.

---

## 9. Optional "Powerhouse" Upgrades

Implemented or planned on the super dashboard:

### 9.1 Modular dashboard (widget visibility & order)

- **Goal**: Let super-admins choose which sections appear and optionally reorder them.
- **Implementation**: 
  - **Phase 1 (current)**: localStorage toggles to show/hide sections (Financial Mission Control, Operational command center, Health, Pending approval, All schools). Optional "Customize" control toggles section visibility; preference key e.g. `runmycampus_super_dashboard_sections`.
  - **Phase 2 (future)**: Per-user saved layout in DB (e.g. `UserPreference` or `SuperAdminDashboardLayout`), drag-and-drop reorder.

### 9.2 Global date/scope filter

- **Goal**: One date range or scope filter that updates all relevant widgets.
- **Implementation**: 
  - Month picker on super dashboard for **Financial Mission Control** (revenue snapshot). Query param `?month=YYYY-MM`; default current month. All financial bento data (MRR, waived, revenue by country, billing model breakdown) use selected month.
  - Optional future: same filter drives command-center time window or export date range.

### 9.3 Export (CSV / PDF)

- **Goal**: Export key tables so insights can leave the dashboard (reports, spreadsheets).
- **Implementation**: 
  - **Schools list**: Export as CSV (name, slug, subdomain, template/systems, domain, status, provisioning, students, teachers, members, last activity). URL e.g. `GET /super/export/schools.csv?month=YYYY-MM` (month optional for future use).
  - **Revenue by country**: Export as CSV for the selected month (country_code, actual, waived). URL e.g. `GET /super/export/revenue.csv?month=YYYY-MM`.
  - **Done**: PDF summary report at `GET /super/export/summary.pdf?month=YYYY-MM` (North Star + financial + operational snapshot).

---

## Implementation status

| Item | Status |
|------|--------|
| North Star + hero on super dashboard (PUBLIC_BRAND_MODE) | Done |
| Global month filter (financial snapshot) | Done |
| Export CSV (schools, revenue) | Done |
| Next-best-action strip (pending, trials) | Done |
| Empty state CTA (no schools) | Done |
| Modular sections (localStorage toggles) | Done |
| Platform navy/gold in backend when PUBLIC_BRAND_MODE | Done |
| Command palette / global search | Done (Ctrl+K in control plane; manager search API returns nav + schools + incidents + subscriptions; empty query shows shortcuts) |
| PDF export | Done (`/super/export/summary.pdf`; reportlab one-page summary) |
| Per-user saved layout (DB) | Done (SuperAdminDashboardPreference; GET/POST `/super/api/dashboard-layout/`; section order persisted per user) |
