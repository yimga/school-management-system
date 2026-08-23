# apps/payroll

> Staff payroll and leave: employees, pay scales, contracts, time entries, the
> payroll run approval FSM, payslips, and bank disbursement export.

**Tenancy:** TENANT (django-tenants; every table lives in the school's own Postgres schema)
**Scale:** 11 models · 8 migrations · 10 test modules · ~3.9k LOC

## What this app owns

Payroll owns the path from "this person works here" to "this person has been
paid": `PayrollEmployee` and their `EmploymentContract`, the `PayScale` that
standardizes what a grade earns, the `TimeEntry` and `SalaryAdjustment` and
`LeaveRequest` rows that move a given period's figures, the `PayrollRun` that
calculates a period, the `Payslip` (and its `PayslipLine` breakdown) it produces,
and the CSV bank file that actually sends the money.

The decision that governs everything here is that **money-out is a one-way door
guarded by a four-step FSM**. A run goes `DRAFT → PROCESSED → REVIEWED → APPROVED
→ PAID`, each step has exactly one producer in `services.py`, each producer is
idempotent, and each refuses to skip a step. `mark_payroll_run_paid` raises unless
the run is `APPROVED`. Marking a run PAID freezes it — and freezing is the whole
point: `generate_payslips` refuses any run past `PROCESSED`, so the figures cannot
change after they have been signed off on or after the money has left the
building. The guard is in the producer, not in `generate_run`: the view is not the
only door — `manage.py run_payroll_cycle` calls `generate_payslips` directly.

This is worth stating plainly because it was recently untrue. `REVIEWED` and
`APPROVED` were **dead enum values** — declared on the model, rendered in the UI,
and set by nothing — and `PayrollRunApproval` was a table that nothing ever wrote,
meaning no record existed of *who* signed off on a payroll. `PAID` had no writer
either, which left the "already paid" guard dead and payslips silently
overwritable after disbursement. The producers documented below now exist and
close that loop.

Note the tenancy consequence: because this app is in `TENANT_APPS`, its tables live
in the tenant's own schema and most models carry **no `school` FK at all** — the
schema *is* the boundary.

## Key models

All 11 models:

| Model | Table | Purpose |
| --- | --- | --- |
| `PayrollEmployee` | `payroll_payrollemployee` | The payroll-side employee record; pay type (monthly/hourly) and payment method (incl. mobile money) |
| `PayScale` | `payroll_payscale` | A named pay scale/grade with salary ranges, applied to staff for standardized structures |
| `EmploymentContract` | `payroll_employmentcontract` | Fixed-term or indefinite contract for a `PayrollEmployee` |
| `SalaryAdjustment` | `payroll_salaryadjustment` | Dated amount adjustment against an employee |
| `TimeEntry` | `payroll_timeentry` | Hours worked on a date; feeds hourly and overtime calculation |
| `LeaveRequest` | `payroll_leaverequest` | Annual / sick / maternity / unpaid / other leave |
| `PayrollRun` | `payroll_payrollrun` | One period (`period_start` → `period_end`) against a compliance profile. Holds the FSM `status` and `processed_at` / `paid_at` |
| `PayrollRunApproval` | `payroll_payrollrunapproval` | The audit record of **who** approved a run, with notes. Written only by `approve_payroll_run` |
| `Payslip` | `payroll_payslip` | Per-employee result of a run: gross, net, tax, employee/employer contributions, overtime. Status draft → issued → paid |
| `PayslipLine` | `payroll_payslipline` | Earning/deduction breakdown lines under a payslip |
| `PayrollOfflineCaptureRecord` | `payroll_payrollofflinecapturerecord` | Idempotent offline HR/payroll workflow capture. **The one model here with a `school` FK** |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | Calculation plus the four FSM producers; the only supported way to move a run's status |
| Module | `disbursement_export` | `build_disbursement_csv()` — ISO-20022-style flat CSV for operator upload to local banks |
| Module | `hr_wizard_kernel` | HR setup wizard logic |
| Module | `models_offline_capture` / `offline_workflow_handlers` | Offline capture + replay handlers |
| URL | `dashboard`, `create_run`, `generate_run`, `run_detail` | Run creation and calculation |
| URL | `review_run`, `approve_run`, `mark_run_paid` | The FSM transitions, one view per producer |
| URL | `payslip_pdf`, `employee_payslips`, `employee_leave` | Employee-facing surfaces (`payslip_pdf` is own-or-manage gated) |
| URL | `export_disbursement` | Bank CSV download |
| Command | `run_payroll_cycle` | Scripted payroll cycle |

This app declares **no Celery tasks** — payroll runs are driven by the views or the
management command, not by a beat schedule.

## Before you change this

- **Do not add a status writer outside `services.py`.** There is exactly one
  producer per FSM state — `review_payroll_run`, `approve_payroll_run`,
  `mark_payroll_run_paid` — each `@transaction.atomic`, each idempotent (a no-op if
  the run is already at or past that state), and each rejecting an out-of-order
  transition with a `ValueError`. `review` refuses anything but `PROCESSED`;
  `approve` refuses anything but `REVIEWED`; `mark_paid` refuses anything but
  `APPROVED`. A view that sets `run.status = "PAID"` directly bypasses the gate and
  the `PayrollRunApproval` audit row. That whole class of bug — an enum value with
  no producer — is what this FSM was built to fix; do not reopen it from the other
  side by writing status without a producer.
- **`approve_payroll_run` is the only writer of `PayrollRunApproval`,** and it is
  idempotent specifically so it never double-writes the approval row on a repeated
  call. That row is the accountability record for a payroll — if it is missing, no
  one signed off. Keep the create inside the same atomic block as the status
  change.
- **PAID is a freeze, not a label — and so is APPROVED.** `generate_payslips` only
  accepts a `DRAFT` or `PROCESSED` run. Regenerating past that point rewrites every
  payslip and rewinds `status` to `PROCESSED` while the `PayrollRunApproval` row
  survives, so the audit trail would attest to figures that no longer exist. If you
  need regeneration after sign-off, add an explicit reopen producer that supersedes
  the approval rows — do not loosen this check.
- **`PayrollRun` has no `paid_by` column.** `mark_payroll_run_paid` accepts an
  `actor` argument that it deliberately does not persist — it is there for a future
  audit trail. Do not read it back expecting a value; the signed-off identity lives
  on `PayrollRunApproval.approver`.
- **The bulk payslip stamp in `mark_payroll_run_paid` is a deliberate
  `.update()`,** with a comment explaining why it is safe: `Payslip` has no custom
  `save()` and no denormalized recompute, so a scoped `.update()` is correct and
  cheaper than per-row saves. **This reasoning is model-specific.** If you ever add
  a `save()` override or a denormalized field to `Payslip`, this `.update()` starts
  silently skipping it — that exact bug has bitten other apps in this repo.
- **Tenancy: the schema is the boundary, and most models have no `school` FK.**
  Because payroll is a `TENANT_APPS` member, a bare-pk `get_object_or_404` is *not*
  an IDOR here — the connection is already pinned to one tenant's schema. Do not
  "fix" that by inventing a `school` filter on a model with no such column; you will
  get a `FieldError`. The one exception is
  `PayrollOfflineCaptureRecord`, which does carry a `school` FK — scope that one
  explicitly.
- **Money is `Decimal`, everywhere, always.** Amounts are `DecimalField(max_digits=12,
  decimal_places=2)` and defaults are `Decimal("0.00")`, not `0.0`. There is a
  dedicated `test_payroll_decimal_integrity` module guarding this. A float entering
  a payroll calculation is a rounding bug you will find in a bank file.
- **Live mobile-money salary APIs are out of scope.** `disbursement_export.py` says
  so directly: they "remain Lane 2", and what ships is a bank-transfer CSV for an
  operator to upload. `PayrollEmployee.PaymentMethod` offers `MTN_MOMO`, but that is
  a recorded preference on the employee and a column in the export — not an
  automated payout integration. Do not describe payroll as having mobile-money
  disbursement.
- `PayrollRun.profile` is `on_delete=PROTECT` against `ComplianceProfile` — a
  profile with runs against it cannot be deleted. That is intentional: the run's
  figures are only interpretable against the compliance rules that produced them.
