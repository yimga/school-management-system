# Data Visualization Improvement Plan
## Dashboards Outside /admin and /backend

This plan outlines how to improve data visualization across Finance, Payroll, Analytics, EMIS, Compliance, Requests, Workflow, and other dashboards—using chart types that fit each feature, plus shared layout/coordination standards.

---

## 1. Current State Summary

| Dashboard | URL | Current Visualizations | Gaps |
|-----------|-----|------------------------|------|
| **Finance** | `/finance/` | KPI cards, status lists, trend list, tables | No charts; trend/list could be area/column |
| **Payroll** | `/payroll/` | Table only, KPI summary cards | No charts; runs-over-time, status distribution absent |
| **Analytics** | `/analytics/` | KPI cards, tables (rankings), filter form | No charts; distributions, trends, comparisons missing |
| **EMIS** | `/emis/` | Export form, Quick Stats (numbers), tables | No charts; entity distribution, export history absent |
| **Compliance** | `/compliance/dashboard/` | Metric cards, Activity Trend (Chart.js), Heatmap | Already has charts; can align styling and add types |
| **Requests** | `/requests/` | Table, filter form, badge counts | No charts; type/status distribution, flow absent |
| **Workflow** | `/authentication/workflow/` | Card links | Hub—light charts for pending counts possible |
| **Approval Hub** | `/authentication/workflow/approvals/` | Card links | Same as Workflow |
| **KB Home** | `/kb/` | Category grid, hero | Minimal—optional popularity sparklines |
| **RBAC** | `/authentication/rbac/` | Tables, forms | Optional role-distribution bar chart |
| **Entity Console** | `/authentication/backend/entities/` | Cards, tables | Entity-type distribution chart |
| **Import Hub** | `/authentication/backend/import-hub/` | Card links | Import-success trend sparkline possible |
| **Certification** | `/authentication/certification/` | Session list | Pass/fail distribution, session timeline |

---

## 2. Chart-Type Mapping (Per Guidelines)

### 2.1 Comparison & Distribution Charts

| Use Case | Best Chart | Example |
|----------|-----------|---------|
| Few categories (≤6) | Pie / Donut | Invoice status, payment method, request type |
| Many categories or long labels | Horizontal Bar | Subjects, classrooms, teachers |
| Magnitude comparison | Column Chart | Receivables vs payables, runs per month |
| Distribution shape | Histogram | Score distribution, payment amounts |
| Outlier detection | Box Plot | Grade outliers, failed access spikes |

### 2.2 Relationship & Flow Diagrams

| Use Case | Best Chart | Example |
|----------|-----------|---------|
| Request flow | Sankey | Access request: Pending → Approved/Denied |
| Role/permission links | Chord / Node-Link | RBAC role–permission mapping |
| Entity relationships | Node-Link | Student–guardian–class links |

### 2.3 Time-Series & Trend Visuals

| Use Case | Best Chart | Example |
|----------|-----------|---------|
| Volume over time | Area | Payments YTD, audit events |
| Composition over time | Stacked Area | Status mix (Draft/Issued/Paid) by month |
| Event context | Area + Annotations | Spike when “Grade deadline passed” |
| Inline trend | Sparkline | Recent activity in table cells |
| Financial summary | Candlestick | (If fee volatility tracked) |

### 2.4 Advanced Density & Geospatial

| Use Case | Best Chart | Example |
|----------|-----------|---------|
| Activity hotspots | Heat Map | Login by hour × day (Compliance already has) |
| Regional distribution | Choropleth | Students/payments by region (if geo data) |

---

## 3. Dashboard-Specific Plan

### 3.1 Finance Dashboard (`/finance/`)

**Data:** Receivables, payables, paid YTD, overdue; invoice status counts; recent invoice trend; recent invoices/payments tables.

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Summary KPIs | Cards | Keep + add **Sparklines** | Quick trend without leaving KPI |
| Invoice status | List | **Donut chart** | Clear distribution, few categories |
| Recent invoice trend | List | **Column chart** or **Area chart** | Time-series, magnitude |
| Payment method mix | (none) | **Horizontal bar** | Many methods, long labels |
| Receivables over time | (none) | **Area chart** | Volume emphasis |
| Overdue by age bucket | (none) | **Horizontal bar** | 0–30, 31–60, 61–90+ days |

**Placement:** Hero KPIs top; Donut + Area side-by-side main; Tables secondary.

---

### 3.2 Payroll Dashboard (`/payroll/`)

**Data:** Runs (period, status, payslip count); latest run summary.

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Latest run | Card | Keep | Primary action |
| Runs table | Table | Add **Sparklines** per run (e.g. approval time) if data exists | Inline trend |
| Run status distribution | (none) | **Pie/Donut** | Draft / Processing / Completed |
| Payroll volume over time | (none) | **Column chart** | Total payslips or amount by month |
| Compliance snapshot | (none) | **Horizontal bar** | Leave requests, overtime by dept (if available) |

**Placement:** Latest run hero; Status donut + Volume column main; Runs table below.

---

### 3.3 Analytics Dashboard (`/analytics/`)

**Data:** Top N, weak subjects, teacher compliance, improvement count; class/school rankings; specialty rates.

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Operational pulse | KPI cards | Keep + **Box plots** for grade distribution | Outlier detection |
| Weak subjects | List | **Horizontal bar** | Many subjects, clear order |
| Teacher compliance | List | **Donut** (On-time / Late / Overdue) | Few categories |
| Class ranking | Table | **Bar chart** top 10 + table | Visual comparison |
| Subject performance distribution | (none) | **Histogram** | Score shape per subject |
| Improvement trend | (none) | **Stacked area** (Improved / Stable / Declined) | Composition over time |
| Specialty popularity | List | **Pie** | Distribution across specializations |

**Placement:** Filters top; Pulse + Weak subjects + Compliance main; Rankings + Histogram secondary; Specialty pie tertiary.

---

### 3.4 EMIS Dashboard (`/emis/`)

**Data:** Export form; Quick Stats (students, teachers, subjects, classes); export history (if available).

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Export form | Form | Keep | Primary action |
| Quick Stats | Numbers | Keep + **Sparklines** (e.g. growth) if history exists | Context |
| Entity distribution | (none) | **Donut** (Students / Teachers / Classes) | Composition |
| Export history | (none) | **Column chart** by type/country over time | Usage trend |
| Country compliance readiness | (none) | **Horizontal bar** | Per-country readiness score |

**Placement:** Form + Info panel; Stats + Donut + Export history below.

---

### 3.5 Compliance Dashboard (`/compliance/dashboard/`)

**Data:** Active users, logins, audits, failed accesses, suspicious sessions, integrity score; Activity Trend; Login Heatmap; Model changes table.

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Metric cards | Cards | Keep | Critical metrics |
| Activity Trend | Line/Area (Chart.js) | **Stacked area + annotations** for incidents | Event context |
| Login Heatmap | Heatmap (Chart.js) | Keep; align colors with design system | Already good |
| Failed access by hour | (none) | **Column chart** | Peak times |
| Model changes | Table | Add **Sparklines** per model if change frequency tracked | Inline trend |
| Integrity over time | (none) | **Line chart** | Trend |

**Placement:** Metrics top; Activity + Heatmap main; Failed access + Integrity secondary; Model changes below.

---

### 3.6 Requests Dashboard (`/requests/`)

**Data:** Requests table; type/status filters with counts.

| Widget | Current | Proposed | Rationale |
|--------|---------|----------|-----------|
| Type distribution | Filter dropdown | **Horizontal bar** or **Pie** | Request type breakdown |
| Status distribution | Filter dropdown | **Donut** | Pending / Approved / Denied |
| Request flow | (none) | **Sankey** (optional) | Pending → Approved/Denied/Clarification |
| Requests over time | (none) | **Area chart** | Volume trend |
| Table | Table | Add **Sparkline** for resolution time (if tracked) | Inline trend |

**Placement:** Distributions top; Flow (if added) main; Table below.

---

### 3.7 Hub Pages (Workflow, Approval, Import, Entity, RBAC, KB, Certification)

| Page | Proposed Additions |
|------|--------------------|
| Workflow Center | **Donut** of pending by workflow type (grades, access, etc.) |
| Approval Hub | **Horizontal bar** of pending count per workflow |
| Import Hub | **Sparkline** or **Column** of import success/fail over time |
| Entity Console | **Donut** of entity counts (Student / Teacher / Guardian / etc.) |
| RBAC | **Horizontal bar** of users per role |
| KB Home | Optional **Sparkline** of popular categories (if analytics) |
| Certification | **Donut** (Pass/Fail/Absent) per session; **Column** of sessions per month |

---

## 4. Coordination & Alignment (Design System)

### 4.1 Shared Chart Library

- **Primary:** Chart.js (already in use for Compliance and Admin).
- **Add:** A reusable wrapper `DashboardChart` with:
  - Responsive container (min-height, aspect ratio)
  - Empty-state handling (“No data” message, neutral styling)
  - Shared color palette (primary, success, warning, danger, muted)
  - Shared font sizes and axis formatting

### 4.2 Grid & Layout

- Use 12-column Bootstrap grid consistently.
- Standard chart container: `col-12 col-md-6 col-lg-4` (or `col-lg-6` for larger charts).
- Standard padding: `p-3` or `p-4`; margin: `mb-3` or `mb-4`.
- Chart cards: `card shadow-sm` with `card-body`; min-height ~200px for consistency.

### 4.3 Responsive Behavior

- Charts scale within containers (Chart.js `maintainAspectRatio`).
- On mobile: stack vertically; reduce chart density (e.g. show top 5–7 bars).
- Tables: horizontal scroll; consider hide non-essential columns on small screens.

### 4.4 Empty & Missing Data

- Empty: show “No data” message and neutral icon.
- Gaps in time-series: interpolate or show zero (document choice).
- Sparse data: show available points; avoid misleading extrapolation.

### 4.5 Visual Consistency

- **Colors:** Map status to semantic colors (success, warning, danger, secondary).
- **Fonts:** Use site font; axis labels 11–12px; titles 14–16px.
- **Legends:** Consistent position (top-right or bottom); avoid overlapping data.

---

## 5. Implementation Phases

### Phase 1: Foundation (1–2 days)

- Create shared `DashboardChart` component / partial.
- Define design tokens (colors, spacing) for charts.
- Add Chart.js to Finance, Payroll, Analytics, EMIS if not already loaded.

### Phase 2: Finance & Payroll (2–3 days)

- Finance: Donut (invoice status), Area (receivables trend), Column (recent trend).
- Payroll: Donut (run status), Column (runs over time).

### Phase 3: Analytics (2–3 days)

- Horizontal bar (weak subjects), Donut (compliance), Bar (top 10 rankings).
- Histogram (score distribution) if data supports it.

### Phase 4: EMIS, Requests, Compliance (2 days)

- EMIS: Donut (entity mix), Column (export history).
- Requests: Donut (status), Area (requests over time).
- Compliance: Align existing charts; add annotations to activity trend.

### Phase 5: Hubs & Polish (1–2 days)

- Add light charts to Workflow, Approval, Entity, RBAC, Certification.
- Final responsive and empty-state passes.
- Visual audit across all dashboards.

---

## 6. Reference Image Alignment

The provided reference shows:

- **Semi-circle / Donut** → Use for Finance status, Payroll status, Requests status, Analytics compliance.
- **Pie** → Use for Analytics specialty, EMIS entity mix, Certification pass/fail.
- **Area** → Use for Finance receivables, Compliance activity, Requests volume.
- **Stacked area + annotations** → Use for Compliance activity (incidents) and Analytics improvement composition.
- **Horizontal bar** → Use for weak subjects, payment methods, request types, RBAC roles.

Ensure:

- Legends outside or in non-overlapping areas.
- Small categories (<5%): consider “Other” or horizontal bar instead of pie.
- Annotations only when they add context (deadlines, incidents, policy changes).

---

## 7. Files to Create/Modify

| File | Purpose |
|------|---------|
| `templates/components/dashboard_chart.html` | Reusable chart partial |
| `static/js/dashboard-charts-shared.js` | Shared Chart.js config, colors, empty-state |
| `templates/finance/dashboard.html` | Add chart containers + data attributes |
| `templates/finance/widgets/` | Finance-specific chart widgets |
| `templates/payroll/dashboard.html` | Add chart containers |
| `templates/analytics/dashboard.html` | Add chart containers + chart types |
| `templates/emis/dashboard.html` | Add chart containers |
| `templates/requests/dashboard.html` | Add chart containers |
| `templates/compliance/dashboard.html` | Align styling; add annotations |
| `apps/finance/views.py` | Add chart data to context |
| `apps/payroll/views.py` | Add chart data |
| `apps/analytics/views.py` | Add chart data |
| `emis/views.py` | Add chart data |
| `apps/requests/views.py` | Add chart data |

---

## 8. Additional Improvements & Suggestions

### 8.1 Accessibility
- **Screen readers:** Add `aria-label` on all charts; provide short text summaries for key insights.
- **Keyboard:** Ensure chart containers and legends are focusable and navigable.
- **Color:** Avoid color-only meaning; use patterns or labels (e.g. "Paid", "Overdue") for status.
- **Reduced motion:** Respect `prefers-reduced-motion`; disable or simplify animations.

### 8.2 Loading & Error States
- **Loading:** Skeleton loaders or spinners while chart data is fetched.
- **Error:** Clear message + "Retry" button if the API fails.
- **Partial failure:** If some charts load and others fail, show the ones that worked.

### 8.3 Performance
- **Lazy load Chart.js:** Load only on dashboards that use charts.
- **Intersection Observer:** Render charts when they scroll into view (for dashboards with many charts).
- **Data limits:** Cap time-series points (e.g. last 90 days) to avoid heavy rendering.

### 8.4 Export & Print
- **Export:** "Download as PNG" for individual charts (Chart.js `.toBase64Image()`).
- **Print:** `@media print` CSS to hide non-essential UI; ensure charts print cleanly for reports.

### 8.5 Theme Support
- If dark/light mode exists, ensure chart colors adapt.
- Store chart colors in CSS variables so they follow the theme.

### 8.6 Comparison Mode
- Add "vs previous period" for Finance and Analytics (e.g. "This month vs last month").
- Use grouped bars or dual lines where appropriate.

### 8.7 Role-Based Chart Visibility
- Hide sensitive charts (e.g. finance details) based on RBAC.
- Reuse existing permission checks.

### 8.8 Threshold / Target Lines
- Add optional reference lines (e.g. "Target: 95% compliance", "Pass mark: 50").
- Helps users quickly see if they're above or below targets.

### 8.9 Drill-Down / Cross-Filtering (Phase 6+)
- Click pie slice to filter table below (e.g. "Show only Paid invoices").
- Enhances discovery without adding new pages.

### 8.10 Documentation
- Add a short "How to add a chart" guide for future developers.
- Include a decision matrix for when to use which chart type.

### 8.11 Priority Order

| Priority | Item | Effort |
|----------|------|--------|
| High | Loading & error states | Low |
| High | Accessibility (ARIA, color) | Medium |
| High | Lazy-load Chart.js | Low |
| Medium | Export to PNG | Low |
| Medium | Print-friendly CSS | Low |
| Medium | Theme support | Medium |
| Medium | Comparison mode | Medium |
| Low | Role-based visibility | Low |
| Low | Threshold lines | Low |
| Later | Drill-down / cross-filtering | High |
| Later | "How to add a chart" doc | Low |

---

## 9. Coordination & Alignment Guidelines (Gap-Free Layouts)

To avoid gaps and ensure consistent, aligned dashboards:

- **Standardized Layout:** 12-column grid; define standard padding (`p-3`/`p-4`), margins (`mb-3`/`mb-4`), and border styles for all chart containers.
- **Responsive Visuals:** Flexbox/Grid; charts scale; stack vertically on mobile; side-by-side on desktop.
- **Consistent Styling:** Uniform colors, fonts, axis formats across all charts.
- **Data Preprocessing:** Fill gaps in time-series with zero or interpolation; avoid misleading empty spaces.
- **Optimize Placement:** Most critical visuals top-left; limit visuals per view to prevent clutter.
- **Shared Library:** Chart.js; reusable components for style consistency.
- **Container Alignment:** CSS flexbox/grid; identical padding even if data differs.
- **Visual Audit:** Regularly audit pages for chart/label/axis alignment across screens.
- **Handle Empty Data:** "No data" labels; never break layout.

---

## 10. Success Criteria

1. Each dashboard has ≥1 chart appropriate to its data (except minimal hubs).
2. Chart styling is consistent (colors, fonts, spacing).
3. Layout uses a 12-column grid with standard padding.
4. Empty states show “No data” instead of broken charts.
5. Charts are responsive and usable on mobile.
6. No overlap or clutter; critical visuals prioritized top-left.
7. Loading and error states implemented.
8. Basic accessibility (ARIA, reduced motion) in place.
9. Export to PNG available for key charts.
