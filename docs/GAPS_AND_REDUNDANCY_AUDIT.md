# Gaps and Redundancy Audit

This document supplements **CODE_REVIEW_GAPS_REDUNDANCIES.md** with additional findings, with emphasis on **redundancy** (duplicate logic and overlapping implementations).

---

## 1. Redundancy: Multiple currency/date/number formatters

**Problem**: The same concern (format amount/date for display) is implemented in several places with different behavior. This makes region-aware display inconsistent and harder to maintain.

| Location | What it does | Used by | Region-aware? |
|----------|---------------|---------|----------------|
| **`apps/siteconfig/templatetags/region_format.py`** | Template filters: `format_date`, `format_currency`, `format_number` | All finance/report templates we updated | ✅ Yes (context) |
| **`apps/evals/grading.py`** | `format_currency(amount, currency_code, include_symbol)` | Not used by views; only CURRENCY_SYMBOLS is imported elsewhere | ❌ No (fixed comma/period) |
| **`apps/siteconfig/translations.py`** | `LocalizationService.format_date`, `format_currency`, `format_number` (take `region` object) | Tests (test_i18n.py) | ✅ Yes |
| **`apps/portal/templatetags/portal_filters.py`** | `format_currency(value)` → `f"{float(value):,.2f}"` (no symbol) | **No templates use it** | ❌ No |
| **`apps/reports/localization.py`** | Stub `CurrencyLocalization.format_currency_by_region(amount, region)` | test_i18n.py only | Stub only |
| **`apps/siteconfig/geoip_service.py`** | `RegionalDataLocalization.format_currency(amount, region)` | test_geoip_service.py only | Own symbol map |

**Recommendations**:
- **Canonical for templates**: Keep **`region_format`** as the single template API; ensure all date/currency/number display in templates goes through it (see template gaps below).
- **Python code**: Use **`LocalizationService`** in `translations.py` (or a single module that uses `RegionConfig` + same rules as `region_format`) when formatting in views/emails/PDFs. Deprecate or remove `grading.format_currency` for display; keep `CURRENCY_SYMBOLS` in grading only for symbol lookup if desired.
- **Dead code**: Remove or deprecate **`portal_filters.format_currency`** (no template references found). If something needs a “raw number, no region” filter, name it explicitly (e.g. `number_with_commas`) and document it.

---

## 2. Redundancy: Currency symbol maps in multiple places

**Problem**: Currency code → symbol mapping is duplicated; adding a currency requires editing several files.

| Location | Map |
|----------|-----|
| **`apps/evals/grading.py`** | `CURRENCY_SYMBOLS` (large dict, used by `region_settings` and `reports/services._region_display_context`) |
| **`apps/siteconfig/translations.py`** | Inline `symbol_map = {"NGN": "₦", "KES": "KSh", "USD": "$", "XAF": "FCFA", "EUR": "€"}` |
| **`apps/siteconfig/geoip_service.py`** | `RegionalDataLocalization.CURRENCY_SYMBOLS` (separate dict) |

**Recommendation**: Treat **`apps/evals/grading.CURRENCY_SYMBOLS`** as the single source of truth (already used by context processor and reports). Have `translations.py` and `geoip_service` import and use it, or move the dict to `siteconfig` (e.g. `siteconfig/currency.py`) and have grading import from there so evals doesn’t own “global” currency data.

---

## 3. Gaps: Templates still using raw `|date:` or `|floatformat:`

**Problem**: Many templates still use Django’s `|date:` or `|floatformat:` instead of region-aware `format_date` / `format_number` / `format_currency`. That leaves dates and numbers in a single locale (e.g. US-style) and ignores user/site region.

**Finance / backend**
- `templates/finance/reports.html` – `collection_rate|floatformat:2` (percentage; could stay or use `format_number:2`)
- `templates/accounts/backend_dashboard.html` – finance summary (receivables, paid, overdue) and notification dates: use `format_currency` and `format_date` + time
- `templates/components/dashboard_header.html` – `pending_amount` / `parent_balance` with hardcoded `$` and `|floatformat:0` → should use `format_currency`

**Evals / analytics**
- `templates/evals/evaluation_admin.html` – `e.total_score|floatformat:2` → `format_number:2`
- `templates/evals/class_ranking.html`, `school_ranking.html` – averages `|floatformat:2` → `format_number:2`
- `templates/analytics/dashboard.html` – many `|floatformat:2` and `|date:` → `format_number` / `format_date` where appropriate
- `templates/analytics/master_sheet.html` – `e.total_score|floatformat:2` → `format_number:2`

**Portal / parent / teacher**
- `templates/requests/dashboard.html` – `req.requested_at|date:"M j, H:i"` → `format_date` + time
- `templates/teacher/dashboard.html` – notification and announcement dates
- `templates/parent/dashboard.html` – notification, announcement, thread dates
- `templates/people/backend_student_list.html` – `student.date_of_birth|date:"M d, Y"` → `format_date`
- `templates/parent/results.html` – `summary.average|floatformat:2` → `format_number:2`

**Other**
- `templates/siteconfig/reportcard_style_preview.html` – totals/averages and `generated_at|date` → `format_number` / `format_date`
- `templates/portal/document_library_manage.html`, `syllabus.html`, `kb_article.html`, `kb_home.html`, `feature_page.html`, `user_contributions.html`, `signature_*.html`, `stats.html`
- `templates/compliance/dashboard.html` – timestamps and score display
- `templates/communication/group_detail.html`, `accounts/direct_thread.html`, `accounts/certification_*.html`
- `templates/staff/contact_requests_list.html`, `requests/detail.html`
- `templates/teacher/marks_entry.html` – request dates and confidence percentages (percentages can stay `floatformat` or use `format_number:0`)

**Recommendation**: Where the value is a **date/datetime**, use `format_date` (and `time:"H:i"` if needed). Where it’s a **currency amount**, use `format_currency`. Where it’s a **grade/score or other number**, use `format_number` (with appropriate decimals). Add `{% load region_format %}` in any template that doesn’t have it. Leave `|date:"c"` for ISO in JS and pure percentages (e.g. 95%) as-is or use `format_number` if you want region separators.

---

## 4. Redundancy: Repeated dashboard context (already partly fixed)

**CODE_REVIEW_GAPS_REDUNDANCIES.md** already notes that dashboard context was consolidated with `get_dashboard_context(user, page)`. If any view still builds the same 4–5 keys by hand, it should be switched to that helper for a single place to maintain.

---

## 5. Redundancy: Duplicate dashboard JS (from existing doc)

**CODE_REVIEW_GAPS_REDUNDANCIES.md** describes duplicate drag-and-drop / layout logic in `dashboard-layout.js` vs `dashboard-customizer.js`. Recommendation there: keep one source for layout (e.g. Sortable.js) and use the other only for non-layout settings, or merge.

---

## 6. Other gaps (from existing code review)

- **GradingDeadline**: Doc says this was fixed (use `SubjectAssignment.grading_deadline_at` etc.); worth a quick grep to ensure no remaining references to a deleted model.
- **Unused imports / dead code**: Running a linter (e.g. ruff, pyflakes) will catch unused imports and obviously dead branches.
- **Placeholder TODOs**: e.g. `apps/academics/scheduling.py` – either implement or remove.

---

## Summary: what to do first

1. **Reduce formatter redundancy**
   - Keep **region_format** as the only template formatting API for date/currency/number.
   - Use **LocalizationService** (or one backend that shares logic with region_format) in Python when you need formatted strings outside templates.
   - Remove or clearly deprecate **portal_filters.format_currency**; consider folding **grading.format_currency** into the single formatter or keeping only symbol lookup in grading.

2. **Single currency symbol map**
   - Use one dict (e.g. `grading.CURRENCY_SYMBOLS`) everywhere, or move it to `siteconfig` and import from there.

3. **Templates**
   - Systematically replace remaining `|date:` / `|floatformat:` for user-visible dates and amounts with **format_date** / **format_currency** / **format_number** and add **{% load region_format %}** where missing (see list in §3).

4. **Dashboard and JS**
   - Rely on **get_dashboard_context** everywhere; merge or clearly split **dashboard-layout.js** and **dashboard-customizer.js** as in the existing code review.

After that, run a linter and clean unused imports and dead code, and resolve or remove TODOs. This audit focuses on redundancy and display/locale gaps; **CODE_REVIEW_GAPS_REDUNDANCIES.md** remains the main reference for structural and feature-level issues.

---

## Implementation status (post-cleanup)

- **Single currency source**: `apps/siteconfig/currency.py` added with `CURRENCY_SYMBOLS` and `get_currency_symbol()`. `evals.grading` re-exports them; `context_processors`, `reports/services`, `translations`, `geoip_service` use the canonical module.
- **Redundant formatter removed**: `portal_filters.format_currency` removed; templates use `region_format` only.
- **Templates**: All listed templates now use `format_date` / `format_currency` / `format_number` and `{% load region_format %}` where applicable.
- **Security**: Request detail template does not use `|safe` on `req.details`; Django auto-escapes. Ensure any JSON displayed from user/submitted data is never marked safe.
