# Dashboard Data Capping Policy

To keep dashboards fast and charts readable as data grows, all chart and aggregate data used on dashboards MUST follow these limits.

**Constants:** Use `apps.dashboard.context.DASHBOARD_CHART_TOP_N` (default 12) and `DASHBOARD_TIME_WINDOW_DAYS` (default 30) in code so limits can be changed in one place.

## Policy

- **Time series:** Use the last **30 days** or the last **12 months** (or a fixed small window, e.g. last 5–7 days or last 4–6 months). Do not send unbounded date ranges to the client.
- **Categories / top-N:** Limit to the **top 10 or 12** items (e.g. top 10 subjects, top 12 roles, top 6 classrooms). Aggregate the rest as "Other" only if the UI supports it; otherwise just cap the list.

## Where It Is Applied

| Location | What is capped | Limit |
|----------|----------------|--------|
| `apps/observability/views.py` – `api_dashboard_charts` | Classrooms (enrollment), subjects (performance), attendance window | 6 classrooms, 6 subjects, 7-day window |
| `apps/accounts/views.py` – backend dashboard | Enrollment trend, RBAC roles chart, recent admissions | 6 months, top 12 roles, 6 admissions |
| `apps/finance/services.py` – `finance_dashboard_data` | Trend months, status counts | 4 months; status is enum-bounded |
| `apps/finance/views.py` – finance dashboard | Uses `finance_dashboard_data` | Same as above |
| `apps/evals/views.py` – teacher dashboard | Completion bar (assignments) | 8 assignments |
| `apps/analytics/views.py` – analytics dashboard | Weak subjects, specialty donut | 10 subjects, 12 specialties |
| `apps/payroll/views.py` – payroll dashboard | Volume by month, run status | 6 months; status enum-bounded |
| `apps/requests/views.py` – requests dashboard | Status donut | Enum-bounded (fixed choices) |
| `apps/portal/views.py` – parent dashboard | Attendance trend | 5 days (from `_attendance_trend`) |
| `apps/portal/services.py` – `_attendance_trend` | Trend points | 5 days |
| `emis/views.py` – EMIS dashboard | Entity donut | 4 fixed entities |

When adding new dashboard charts or APIs, apply the same rules: time series = last 30 days or 12 months (or small fixed window); categories = top 10–12.

**Usage:** Use explicit slices in views (e.g. `queryset[:12]`, `trend[-30:]`) or date filters; avoid unbounded `.values().annotate()` for chart data without a cap.
