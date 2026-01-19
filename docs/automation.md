# Phase 7 Automation Playbook

## Commands to run regularly
- `python manage.py check` & `python manage.py test` — baseline verification for every push.
- `python manage.py run_attendance_cycle` — refresh attendance/alert datasets before dashboard snapshots.
- `python manage.py run_payroll_cycle` — enforce payroll automation and keep dashboards aligned with the latest payslips.
- `python manage.py run_payment_reminders` — send fee reminders; review logs via `PaymentReminderLog`.
- `python manage.py collectstatic --noinput` — rebuild static assets before deployments.

## Custom Phase 7 command
We added `python manage.py run_phase7_checks` (see `apps/siteconfig/management/commands/run_phase7_checks.py`) to group together:
1. `check`
2. `test`
3. `run_payment_reminders`
4. `run_attendance_cycle`
4. `python manage.py send_payment_reminders` (if needed)
5. `check_integrations` (verifies required keys for enabled providers)
6. `check_roles` (reports empty roles, unused permissions, and users without roles)

Use `--require-automation` to fail if optional automation commands are missing:
```
python manage.py run_phase7_checks --require-automation
```

## Scheduled workflows
- Set Render cron to execute `python manage.py run_phase7_checks` nightly.
- Hook accessibility audits (axe/pa11y) into CI, writing results to `docs/qa-reports/`.
