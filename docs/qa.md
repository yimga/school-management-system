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

### Marketing site: Lighthouse & pa11y (public URLs)
- **Purpose:** Catch performance and a11y regressions on the marketing landing and key pages before deploy.
- **URLs to test:** `/` (home), `/pricing/`, `/product/`, `/book-demo/`, optionally `/solutions/`, `/why-switch/`.
- **Lighthouse:** Run in CI or pre_deploy (e.g. `npx lighthouse https://<staging>/ --output=json --output-path=./docs/qa-reports/lighthouse-home.json --chrome-flags="--headless"`). Fail or warn if Performance score &lt; threshold or Accessibility score &lt; 90.
- **pa11y:** `npx pa11y https://<staging>/` (and other URLs); store results in `docs/qa-reports/` and fail on critical a11y violations. See [MARKETING_PAGE_AUDIT.md](MARKETING_PAGE_AUDIT.md) for WCAG/i18n gap logging.
- **CI step (optional):** Add a job that starts the app (or uses a staging URL), runs Lighthouse/pa11y on the list above, and uploads artifacts. Runner is environment-specific; document the exact command in this file or in your CI config.
- **GitHub Actions — Pa11y:** Workflow `.github/workflows/pa11y-ci.yml` runs when **`PA11Y_BASE_URL`** is set under **Repository → Settings → Secrets and variables → Actions → Variables** (same idea as Lighthouse’s `LHCI_URL`). Default URL list: `{BASE}/marketing/`, `{BASE}/`. Optional comma-separated **`PA11Y_URLS_EXTRA`**: absolute URLs, or paths such as `/book-demo/` (appended to `PA11Y_BASE_URL`). If `PA11Y_BASE_URL` is empty, the job is skipped.

### MFA checklist (full)
1. **Enable MFA**: Admin → User → MFA setup (or `accounts:mfa_setup`); verify TOTP device registration.
2. **Login with MFA**: After login, prompt for OTP; verify rejection of invalid OTP.
3. **Passkey (WebAuthn)**: `apps/accounts/views_passkey.py`; register passkey, login with passkey; fallback to password.
4. **Bypass**: Superuser/staff can have MFA optional per policy; document in admin QA.

### Pen-test checklist (full)
1. **Static analysis**: `bandit -r apps/ config/`; fix high/medium; document suppressions.
2. **Dependency scan**: `pip audit` or `safety check`; update vulnerable deps.
3. **Auth**: No unauthenticated access to tenant data; verify `login_required` / RBAC on all sensitive views.
4. **APIs**: SMS/WhatsApp webhooks validate signature; no PII in logs; rate limits on public endpoints.
5. **OWASP Top 10**: Document mitigation for injection, XSS, broken auth, sensitive data exposure, XML external entities, misconfig, XSS, insecure deserialization, known vulns, logging/monitoring.
6. **Run**: Quarterly pen-test run; store results in `docs/qa-reports/pen-test-YYYY-MM.md`.

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
