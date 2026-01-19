# Phase 7 QA Guide

## Objective
Embed QA into every Phase 7 milestone: dashboards, integrations, and automations must stay reliable and accessible.

### Regression Focus
- **Teacher → Publish → Parent report**: run `python manage.py test apps.evals.tests.TeacherWorkflowTests` (add a targeted test file when available) or use Playwright/pytest to simulate mark entry and parent visibility.
- **Finance reminders**: execute `python manage.py run_payment_reminders` and verify `PaymentReminderLog` entries; confirm webhook signatures through `apps.finance.services.verify_payment_signature`.
- **Communication health**: validate WhatsApp/SMS integrations by pinging `Integration` entries (see `apps.siteconfig.models.Integration`)—the `run_phase7_checks` management command covers this.

### Security & Accessibility
- MFA/OTP toggles: manually test `django-otp` flows when enabled; document steps in the admin QA checklist.
- Penetration/Interoperability: periodically run static analyzers (`bandit`, `brakeman` equivalent) and ensure APIs respond to expected SMS/WhatsApp payloads; capture logs for every audit run.
- Accessibility: use `axe-core` or `pa11y` against key templates (`templates/portal/*`, `templates/teacher/*`, `templates/finance/*`) and store the reports in `docs/qa-reports/`.

### Metrics to track
- Weekly regression pass/fail summary.
- Outstanding vulnerabilities (OWASP top 10).
- Accessibility score per template.
