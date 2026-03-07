# Report Card Builder Execution Checklist

## Scope

This checklist executes the approved report card and theme-experience improvements in a safe, phased rollout with one commit per phase and testing after each phase.

## Phase-by-phase file map

1. **Phase 0 - Baseline audit and lock decisions**
- `docs/reportcard/PHASE_0_REPORTCARD_GAP_MATRIX.md`
- `docs/reportcard/EXECUTION_CHECKLIST.md`
- Validation: `python manage.py check`

2. **Phase 1 - Builder IA refactor (shorter page, larger preview)**
- `templates/siteconfig/reportcard_builder.html`
- `templates/siteconfig/partials/mock_reportcard_preview.html`
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: `python manage.py test apps.siteconfig.tests.test_reportcard_builder -v 2`

3. **Phase 2 - Active state and unsaved workflow guard**
- `templates/siteconfig/reportcard_builder.html`
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: `python manage.py test apps.siteconfig.tests.test_reportcard_builder -v 2`

4. **Phase 3 - Live preview resiliency (iframe fallback + retry/open-tab)**
- `templates/siteconfig/partials/mock_reportcard_preview.html`
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: `python manage.py test apps.siteconfig.tests.test_reportcard_builder -v 2`

5. **Phase 4 - Watermark model and config plumbing**
- `apps/siteconfig/models.py`
- `apps/siteconfig/forms.py`
- `apps/siteconfig/views.py`
- `apps/siteconfig/migrations/0077_reportcardstyle_watermark_fields.py`
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: `python manage.py makemigrations --check`, `python manage.py migrate`, targeted tests

6. **Phase 5 - Watermark rendering in report templates and preview**
- `templates/reports/_report_styles.html`
- `templates/reports/term_report_cameroon.html`
- `templates/reports/annual_report_cameroon.html`
- `templates/reports/term_report_cameroon_modern.html`
- `templates/reports/annual_report_cameroon_modern.html`
- `templates/siteconfig/reportcard_style_preview.html`
- Validation: reportcard builder tests + report PDF preview tests

7. **Phase 6 - Parity improvements (teacher column, subject rank, configurable labels)**
- `apps/reports/services.py`
- `templates/reports/term_report_cameroon.html`
- `templates/reports/annual_report_cameroon.html`
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: report + siteconfig targeted tests

8. **Phase 7 - Regression coverage and full gate**
- `apps/reports/tests/test_services.py` (or new focused test module)
- `apps/siteconfig/tests/test_reportcard_builder.py`
- Validation: targeted suites then full `python manage.py test`

9. **Phase 8 - Final cleanup and release-ready checks**
- No product behavior changes; docs and cleanup only.
- Validation: `python manage.py check`, `python manage.py test`, `git status`

## Non-functional acceptance criteria

- Builder page remains compact and scannable on laptop widths.
- Live preview is always reachable via fallback action even when iframe fails.
- Active style/default mapping is visible without opening forms.
- Watermark logo/text behavior is fully configurable and non-hardcoded.
- Term/annual templates preserve bilingual labels and Cameroon workflow fields.
