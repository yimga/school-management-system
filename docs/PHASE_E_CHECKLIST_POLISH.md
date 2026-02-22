# Phase E Plan Checklist (optional / polish)

## Done

- **Plan Configurator API:** `GET /super/api/plans-configurator/?country_code=XX` — plans, addons, country_multiplier (see `docs/PLAN_CONFIGURATOR_API.md`).
- **Wizard Plan & billing:** Super create-school wizard Step 2 includes optional Plan dropdown, add-on checkboxes, estimated students, and real-time estimated price (PPP). Payload sends `plan_id` and `addons`; `api_create_school` sets `school.plan_id` and `school.addons`.
- **Waiver (Super Admin):** Admin action "Waive subscription" + form; `BillingWaiverAuditLog` records each change.
- **WaiverRequest model:** Exists in siteconfig (proof_file, reason, status, decided_by); managed in Django admin. Optional: school-facing "Request waiver" page that creates a WaiverRequest for Super Admin to approve/deny.

## Optional remaining (all done)

- **School-submitted waiver flow:** Implemented. `accounts:request_waiver` — Backend → Request subscription waiver (reason + optional proof); Super Admin approves/denies in admin (WaiverRequest actions).
- **UsageLimitMiddleware:** On by default; set `DISABLE_USAGE_LIMIT_MIDDLEWARE=1` to turn off.
- **Audit trail:** Already in place via `BillingWaiverAuditLog`; no further work required.
