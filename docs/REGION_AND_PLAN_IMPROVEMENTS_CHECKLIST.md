# Region & Plan Implementation: What’s Done and What’s Missing

This checklist covers the code added for the critical review plan (Phases 1–7) and suggests follow-ups.

---

## Migration

- **Siteconfig 0069** (UserPreference `preferred_language`, `preferred_region`): run `python manage.py migrate siteconfig` if not already applied.
- **Admin fix**: `TimeSlotAdmin` now has `search_fields = ("slot_name",)` so ScheduleEntry autocomplete works; `UserPreferenceAdmin` lists `preferred_language` and `preferred_region`.

---

## Done

| Area | What was added |
|------|----------------|
| **Phase 1** | Single `except DatabaseError` in `region_settings`; Français fix; REGION_CODE/TIME_ZONE in .env.example and Buea guide; ENABLE_MULTI_REGION documented and in context. |
| **Phase 2** | UserPreference preferred_language/preferred_region; template filters `format_date`, `format_currency`, `format_number`; LocalizationService accepts `region`; filters used in finance, parent finance, receipt, report (Cameroon); LANGUAGES extended. |
| **Phase 3** | AssessmentWeights → grading scale mapping; report context gets `_region_display_context()` (date_format, currency_symbol, etc.). |
| **Phase 4** | Finance dashboard/widgets use format_currency; model help_text for thresholds. |
| **Phase 5** | MULTI_SCHOOL_ADD_NEW_SCHOOL.md updated (region seeding note). _Archived 2026-05-15 (NS-13); see `docs/archive/legacy_2026_05_14/MULTI_SCHOOL_ADD_NEW_SCHOOL.md`._ |
| **Phase 6** | Teacher timetable view and template; “My Timetable” in portal sidebar. |
| **Phase 7** | PHASE7_NICE_TO_HAVE_ROADMAP.md. |

---

## Missing or Optional Improvements

### 1. Tests (recommended)

- **Template filters**  
  Unit tests for `region_format.format_date`, `format_currency`, `format_number` with mock context (e.g. CMR vs USA patterns).

- **Context processors**  
  Tests that `region_settings` returns `enable_multi_region` and uses `preferred_region` when user has preferences; `language_context` uses `preferred_language` when set.

- **Reports**  
  Test that `term_report_context` and `annual_report_context` include keys from `_region_display_context()` (e.g. `date_format`, `currency_symbol`).

- **Grading**  
  Test `scale_for_assessment_weights()` and `ASSESSMENT_WEIGHTS_SCALE_MAP` for each AssessmentWeights grading_scale.

- **Teacher timetable**  
  Integration test: create Schedule + ScheduleEntry for a teacher, GET `portal:teacher_timetable`, assert entries in response.

### 2. Templates still using raw dates/amounts

These still use `|date:...` or raw amounts; optional to switch to region-aware formatting:

- **Dates**: `invoice_detail.html` (reminder/log dates), `evals/grade_approval_detail.html`, `evals/evidence_upload.html`, `teacher/marks_entry.html`, `reports/annual_report_cameroon.html`, `siteconfig/reportcard_style_preview.html`, `portal/document_library_manage.html`, `portal/syllabus.html`, various dashboard badges (`created_at|date:"M j, H:i"`).
- **Amounts**: Any payroll or analytics templates that show money (if they exist and should be region-aware).

Using `{% load region_format %}` and `|format_date` / `|format_currency` in high-traffic or user-facing pages will make behaviour consistent with region.

### 3. Receipt / PDF context

- Receipt and report PDFs rendered with `render()` get RequestContext, so `region_settings` runs and filters work.
- If any report or receipt is ever rendered with a minimal context (e.g. for a background PDF worker), that view should pass `date_format`, `currency_symbol`, etc. into the context so `format_date`/`format_currency` still work.

### 4. UserPreference form save

- `preferred_language` and `preferred_region` are in `UserPreferenceForm.Meta.fields`; ensure the view that saves user preferences (e.g. siteconfig user_preferences) includes these in the POST and that they are written to the model (no extra `clean_*` or `save()` that drops them).

### 5. Region format filter robustness

- `region_format` filters use `context.get("date_format")` etc.; if a template is ever rendered without the region context processor, they fall back to defaults (e.g. DD/MM/YYYY, empty symbol). Optional: add a one-line comment in the templatetag module that “Requires region_settings context processor.”

### 6. Analytics / BI

- Plan Phase 7: “Use region timezone and number/date format in analytics views.” Not done; consider passing region display options into analytics templates and using `format_date` / `format_number` where appropriate.

### 7. Documentation

- **Developers**: Short note in a central doc (e.g. THEME_SYSTEM.md or a new REGION_AND_LOCALIZATION.md) that:
  - Region comes from `region_settings` context; user can override via `UserPreference.preferred_region` / `preferred_language`.
  - Templates should use `{% load region_format %}` and `format_date` / `format_currency` / `format_number` for region-aware display.
- **.env.example**: Already documents REGION_CODE, TIME_ZONE, ENABLE_MULTI_REGION.

### 8. Linting / type hints

- Optional: add type hints to `region_format` filters (e.g. `context: dict`, `value: Any`) and to `scale_for_assessment_weights(weights: Optional[Any]) -> str` for clarity.

---

## Summary

- **Migration**: Run `python manage.py migrate siteconfig`; admin fixes for TimeSlot and UserPreference are in place.
- **Must-fix**: None; current code is consistent and usable.
- **Recommended**: Add tests for filters, context processors, report context, grading mapping, and teacher timetable.
- **Optional**: Extend region formatting to more templates (dates in evals, reports, dashboards); document region/locale usage for developers; add analytics region formatting per Phase 7 roadmap.
