# Phase 7 Test Notes

## Validated commands (Git Bash)

```bash
python manage.py check
python manage.py test apps.siteconfig.tests.test_reportcard_builder apps.reports.tests.test_cameroon_report_context apps.reports.tests.test_publish_term -v 1
```

Result: `OK` (12 tests).

## Full-suite baseline status

`python manage.py test -v 1` currently fails in multiple unrelated legacy test modules outside report-card/theme scope (pre-existing):

- `apps/academics/test_scheduling.py` (fixtures incompatible with current `Classroom.department` constraints)
- `apps/analytics/test_advanced_analytics.py` (references removed `analytics_performancemetrics` table)
- `apps/communication/test_video_conferencing.py` (missing models/settings and external provider config)
- `apps/compliance/tests.py` (uses swapped `auth.User` manager directly)
- `apps/finance/test_advanced_finance.py` (expects validator/security APIs not present in current implementation)
- `apps/observability/test_monitoring.py` (hard dependency on `psutil` not installed)
- root-level script-style tests with non-ASCII console output that crash on Windows codepage

These full-suite failures are not introduced by this report-card phase; they are historical debt in unrelated modules.
