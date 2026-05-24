SFDP Launch Checklist

Purpose: Short, actionable checklist for engineers and product to run the SFDP repo->operator handoff and verify launch readiness.

Pre-launch (Repo)
- Run scaffold and completion verifiers:
  - `python scripts/verify_sovereign_financial_delivery_scaffold.py`
  - `python scripts/verify_sovereign_financial_delivery_completion.py`
- Run Django checks and migrations dry-run:
  - `python manage.py check`
  - `python manage.py makemigrations --dry-run --check`
- Run critical tests (non-exhaustive):
  - `python manage.py test apps.finance.tests.test_payment_region_catalog_expansion apps.finance.tests.test_global_payment_profiles --noinput`
- Confirm `apps/billing/psp_adapter_registry.py` shows expected adapters and statuses.
- Confirm `apps/finance/data/regional_payment_profiles.json` drift tests pass.

Operator readiness (Lane 2)
- For each corridor/provider:
  1. Obtain merchant KYB and production keys (store in `Integration` via UI or operator secret tooling).
  2. Run health/metadata check:
     - `python manage.py check_payment_gateways --school=<slug> --provider=<psp> --mode=production_ping`
     - If provider uses metadata-only mode, use `--mode=metadata`.
  3. Run a supervised test charge and verify webhook delivery to `payment_provider_webhook`.
  4. Copy the evidence template to `var/evidence/geos-99/psp/<provider>/README.md` with redacted fields.
  5. Update `docs/external_dependencies_register.json` child row to `verified_live` only after evidence copy.

Post-launch monitoring
- Confirm idempotent ledger entries for test charges.
- Monitor payment success rate and settlement accuracy KPIs for 24–72 hours.
- Ensure bursar queue reconciliations are processed within SLA.

Rollback / mitigation
- If webhooks fail at scale: temporarily pause provider in `psp_adapter_registry` (set to `in_progress`), re-route charges to backup rail, and escalate.
- For settlement gaps: mark affected payouts in ledger as `reconciliation_pending` and open a `Finance Reconciliation` ticket.

Notes
- Lane 1 (repo) ≠ Lane 2 (live). This checklist enforces Lane 2 evidence truthfulness before marking providers `verified_live`.
- Keep evidence artifacts minimal and redacted; never commit secrets.
