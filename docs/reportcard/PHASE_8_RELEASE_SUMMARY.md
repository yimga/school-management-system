# Phase 8 Release Summary

## Completed phase commits

1. `phase0: add reportcard gap matrix and execution checklist`
2. `phase1: move builder workflow under catalog and assignments tabs`
3. `phase2: add active style status strip and unsaved workflow guard`
4. `phase3: harden live preview iframe with timeout fallback and retry`
5. `phase4: add configurable watermark fields and builder form wiring`
6. `phase5: render configurable text or logo watermarks in report previews`
7. `phase6: add subject rank and teacher parity across cameroon report templates`
8. `phase7: strengthen test fixtures and record report-card validation gate`

## Final validation run

```bash
python manage.py check
python manage.py test apps.siteconfig.tests.test_reportcard_builder apps.reports.tests.test_cameroon_report_context apps.reports.tests.test_publish_term -v 1
```

Result: all checks passed (`OK`, 12 tests).

## Merge readiness

- Report card builder IA is compact and workflow is integrated under the left catalog section.
- Live preview has timeout/error fallback plus retry/open-tab controls.
- Watermark is fully configurable per report style (text/site logo/style logo, opacity, scale, position).
- Cameroon report templates now include subject rank + teacher column parity and richer KPI summary values.
