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

---

## Phase 7 Task 1: Regression Tests & API Health Checks

### New Test Suite

#### Test File
- **Location**: `apps/siteconfig/tests/test_phase7_regression.py`
- **Command**: `python manage.py test_core_workflows`

#### Test Coverage
1. **Teacher → Parent Workflow** (`TeacherPublishWorkflowTest`)
   - Teacher can enter grades
   - Published grades visible to parents
   - Unpublished grades hidden from parents

2. **Fee Reminder Workflow** (`FeeReminderWorkflowTest`)
   - Reminders created for unpaid invoices
   - No reminders for paid invoices
   - Overdue invoice flagging

3. **Automation Cycle Health** (`AutomationCycleHealthTest`)
   - Attendance cycle command exists
   - Payroll cycle command exists

#### Running Tests
```bash
# Basic run
python manage.py test_core_workflows

# Verbose output
python manage.py test_core_workflows --verbose

# Stop on first failure
python manage.py test_core_workflows --failfast
```

### API Health Check Command

#### Usage
```bash
# Basic check
python manage.py check_api_health

# With custom timeout
python manage.py check_api_health --timeout 15
```

#### Monitored APIs
- **SMS API**: `GET {SMS_API_URL}/health` with Bearer token
- **WhatsApp API**: `GET {WHATSAPP_API_URL}/health` with Bearer token
- **Slack Webhook**: `POST {SLACK_WEBHOOK_URL}` with test payload

#### Status Codes
- **HEALTHY**: HTTP 200
- **UNHEALTHY**: Non-200 status
- **ERROR**: Connection error/timeout
- **NOT_CONFIGURED**: Missing credentials

### Automation Schedule

#### Linux/Mac (crontab)
```bash
# Health check every hour
0 * * * * cd /path/to/project && python manage.py check_api_health >> logs/api_health.log 2>&1

# Regression tests daily at 3 AM
0 3 * * * cd /path/to/project && python manage.py test_core_workflows >> logs/regression_tests.log 2>&1
```

#### Windows Task Scheduler
1. Hourly task: `python manage.py check_api_health`
2. Daily task: `python manage.py test_core_workflows`
3. Log to `logs/` directory

### CI/CD Integration
```yaml
name: Phase 7 Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run regression tests
        run: python manage.py test_core_workflows
      - name: Check API health
        run: python manage.py check_api_health
```

### Dependencies
```txt
requests>=2.31.0  # For API health checks
```

Install: `pip install requests`

---
**Phase 7 Task 1 Status**: Implemented  
**Last Updated**: 2025-01-19
