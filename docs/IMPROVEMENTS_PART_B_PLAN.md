# Part B: Execute when data exists – Plan and dependencies

This document details **Part B** of the improvement plan. Part B items are either (1) **do not do** by design, (2) **deferred until data/usage justifies them**, or (3) **implemented now so that when data exists it populates automatically** (scaffolding, filters, docs).

Reference: `IMPROVEMENTS_EXECUTABLE_PLAN.md` (Part B table), `IMPROVEMENTS_DATA_AGNOSTIC.md`.

---

## Dependency overview

```
B.2 (do not do) ──┐
B.3 (do not do) ──┼── No code dependency; document only.
                  │
B.1 (after launch)┘   Revisit only if user feedback/analytics show empty states are confusing.

B.4 (list UX) ─────── Depends on: list pages exist (invoices, payments, etc.). Part A already added table tokens and structure.
                      When data exists: verify readability, sorting, row actions; no empty-state-only redesign.

B.5 (caching) ─────── Depends on: report/analytics views that run heavy queries. No dependency on data volume for *adding* the hook.
                      When usage/data justify: add cache decorator or background job at documented hook points.

B.6 (filters/sorting) ─ Depends on: list views and templates. Can be implemented now (data-agnostic).
                      When data exists: filters already work; optionally add more (e.g. sort order) if needed.
```

---

## B.1 – Fancy empty-state illustrations or long copy

| Field | Value |
|-------|--------|
| **When to execute** | After launch, only if user feedback or analytics show empty states are confusing or high-traffic. |
| **Dependencies** | None. |
| **What “done” looks like** | Decision: either keep minimal empty states (current) or add one illustration/copy per key empty view, based on evidence. |
| **Do now** | Nothing. Document in this plan; revisit in backlog when feedback exists. |

**Checklist (when revisiting):**
- [ ] Review analytics or feedback for empty-state pages (finance, portal dashboards, lists).
- [ ] If justified: add a single illustration or short copy to `components/dashboard_empty_state.html` or per-page overrides.
- [ ] Keep empty states minimal; no long paragraphs.

---

## B.2 – Dashboard fill / placeholder content

| Field | Value |
|-------|--------|
| **When to execute** | **Do not do.** |
| **Dependencies** | None. |
| **What “done” looks like** | No fake widgets or placeholder content. Dashboards show real data when it exists; when there is no data, existing empty states are sufficient. |
| **Do now** | Confirm no placeholder/fake content is added. Document here. |

**Checklist:**
- [x] **Do not add** placeholder widgets or fake data to dashboards.
- [x] When data exists, existing views and widgets that read from the same data will populate automatically (no extra “fill” work).

---

## B.3 – Layouts only for 0–3 items

| Field | Value |
|-------|--------|
| **When to execute** | **Do not do.** |
| **Dependencies** | None. |
| **What “done” looks like** | We build for 0, 10, and 100+ items. No layout or component that only makes sense for 0–3 items (e.g. a special “tiny list” layout). |
| **Do now** | Document; ensure list/dashboard templates do not branch layout on “few items” in a way that would look wrong at scale. |

**Checklist:**
- [x] **Do not add** layouts that only target 0–3 items.
- [x] Current list pages use the same table/card layout for any number of rows; pagination and empty state handle 0 and many.
- [x] **Audit:** No template branches layout on "few items" (e.g. no 0–3-only UI); uses of length/count are for display or conditional content only.

---

## B.4 – List UX when data exists (readability, sorting, actions)

| Field | Value |
|-------|--------|
| **When to execute** | When data exists and lists are in active use. |
| **Dependencies** | Part A: table design tokens, pagination, empty states. List views: invoices, payments, portal parent finance. |
| **What “done” looks like** | Lists with many rows are readable (tokens, density), and optionally sortable/filterable; row actions clear. No heavy redesign only for the empty state. |
| **Do now** | Verify list pages use design tokens and consistent structure; document where to add sort/filter/actions when needed. |

**Checklist (now):**
- [x] Finance invoices: filter form (search, status, year), table with tokens, pagination, export – already in place.
- [x] Finance payments: table with tokens, pagination, export; filters added in Part B implementation (method, date range).
- [x] **Sort order:** Invoices and payments lists have "Sort by" dropdown (order param); export and pagination preserve order. Implemented in Plan B.
- [x] Portal parent finance: status filter and sort order (date, due date, amount) added; same table tokens and structure.
- [x] **When data exists:** Sort/filter in place; add more row actions at hook points if needed.

**Hook points (code):**
- `templates/finance/invoices.html` – table, thead, pagination_extra_query.
- `templates/finance/payments.html` – table, thead, pagination_extra_query.
- `static/css/design-tokens.css` – `.table thead th`, `.table td` use `--admin-content-*`.

---

## B.5 – Analytics/reports caching or background jobs

| Field | Value |
|-------|--------|
| **When to execute** | When report usage and data volume make slow pages or timeouts likely. |
| **Dependencies** | Analytics/report views that run heavy queries (e.g. analytics dashboard, BI reports, large exports). |
| **What “done” looks like** | Caching or background generation added only where justified; documented so future devs know where to add it. |
| **Do now** | Document hook points and a one-line pattern; optionally add a single cache placeholder (e.g. in analytics dashboard or reports) so the pattern is clear. |

**Checklist (now):**
- [x] Document views that are candidates for caching (see below).
- [x] **Optional cache implemented:** Analytics dashboard checks `backend_feature_flags["analytics_dashboard_cache_seconds"]`. If > 0, response is cached with key from request path; TTL in seconds. Off by default. Enable in Site Settings → Backend feature flags.

**Hook points (candidates for caching when justified):**
- `apps/analytics/views.py` – `dashboard()` (year/term/classroom/specialty filters; heavy aggregations).
- `apps/reports/views.py` – any view that builds large BI or PDF reports.
- `apps/compliance/` – reporting/analytics views if they aggregate over many records.
- Pattern: `from django.views.decorators.cache import cache_page` with `cache_page(60 * 15)` (15 min) and a cache key that includes request GET params, or use Django’s cache framework with a custom key (e.g. `f"analytics_dash:{year_id}:{term_id}:{classroom_id}"`).

---

## B.6 – Extra filters and sorting UI

| Field | Value |
|-------|--------|
| **When to execute** | Can be implemented now (data-agnostic). When users have long lists, filters/sort already available. |
| **Dependencies** | List views (invoice_list, payment_list) and templates. Invoices already have status, year, search. |
| **What “done” looks like** | Payment list: filter by method and date range (from/to). Export and pagination preserve filter params. Optionally: sort order (e.g. paid_at asc/desc) if needed later. |
| **Do now** | Add method and date-range filters to payment_list view and payments template; preserve params in export links and pagination_extra_query. |

**Checklist:**
- [x] Invoice list: already has status, year, search (Part A / existing); sort order added (issued_date, due_date, total_amount asc/desc).
- [x] Payment list: `method` and `date_from`/`date_to` filters; sort order (paid_at, amount asc/desc). Export and pagination preserve all params.

---

## Summary – Part B completion

| # | Task | Do now | When data/usage |
|---|------|--------|-------------------|
| B.1 | Fancy empty states | Document only | Revisit if feedback justifies |
| B.2 | Dashboard placeholders | Do not do; document | — |
| B.3 | Layouts for 0–3 items | Do not do; document | — |
| B.4 | List UX | Verify tokens/structure; document hooks | Add sort/actions if needed |
| B.5 | Caching | Optional analytics dashboard cache (off by default; enable via backend_feature_flags) | Add cache to other views if needed |
| B.6 | Filters/sorting | Payment list: method, date range, sort. Invoice list: sort order. Both: export/pagination preserve params. | Add more columns/sort if needed |

When data becomes available:
- **Lists** (invoices, payments, parent finance) will already show real data; filters and pagination work with 0 or many rows.
- **Dashboards** will show real widgets/data from existing queries; no placeholder fill.
- **Caching** can be added at the documented hook points when response times or load justify it.
- **Empty states** stay minimal unless B.1 is revisited with evidence.
