## Payroll Automation (Cameroon-first, globally flexible)

The payroll automation stack keeps your Cameroon CNPS/minimum wage rules (via the Cameroon compliance profile) but exposes the same hooks for other countries. Key behaviors:

1. **Compliance profile drives payroll math.** `ComplianceProfile` includes `min_wage`, `default_hours_per_week`, and seeded `ContributionRule` entries (CNPS 4.2% employee / 12.95% employer plus tax brackets). Swap profiles or add new ones to target a different jurisdiction without touching the code.

2. **Monthly payroll runs.** Use `python manage.py run_payroll_cycle` to generate a `PayrollRun` for the current calendar month (or pass `--year`/`--month` to specify another period). The command:
   - Picks the active compliance profile (Cameroon in production).
   - Creates or reuses the `PayrollRun` for that period.
   - Runs the `generate_payslips` service which calculates gross/net pay, applies overtime, enforces salary caps/minimum wage, and posts CNPS/tax contributions into payslip lines.
   - Marks the run as `PROCESSED` once payslips are created.

3. **Payslips & approvals.** Use the payroll dashboard (`/payroll/`) to review each run, download payslips (list each employee/pay totals), and fire off new runs as needed. Employee portal pages (`/payroll/employee/payslips/`) show issued payslips, and `PayrollRun&apos;s` status fields track DRAFT → PROCESSED → PAID.

4. **Notifications (future-ready).** The command can later hook into `Integration` entries (provider=`email`/`sms`) to notify staff once a run processes. The same `Integration` model already backs finance reminders, so you can plug the notification provider you already use.

### Commands
- `python manage.py run_payroll_cycle` — generate the current month’s payroll (Cameroon) and issue payslips.
- `python manage.py run_payroll_cycle --year 2025 --month 12` — build a past run (e.g., for audits).
- `python manage.py send_payment_reminders` — still relevant for fee collections tied to payroll-based fees (optional).

### Rendering & Reporting
- Payslip views re-use WeasyPrint (falling back gracefully if not installed) so employees can download PDFs.
- The payroll dashboard summarizes gross/net totals per run, leaving space to extend into exportable OHADA-compliant reports later.

Keep your Render environment variables aligned (`DATABASE_URL`, `SECRET_KEY`, `SITE_URL`, optional SMTP/payment secrets) so automation and reminders work seamlessly.
