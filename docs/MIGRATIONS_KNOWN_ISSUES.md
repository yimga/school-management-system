# Migrations – Known Issues

## Finance app: duplicate migration numbers

The `finance` app has duplicate migration numbers from branch merges:

- **0019:** `0019_add_finance_request_audit.py` (empty, depends on `0019_finance_request_audit`) and `0019_finance_request_audit.py` (creates `FinanceRequestAudit`).
- **0020:** `0020_payment_reconciliation_and_more.py` and `0020_paymentreconciliation_refundrequest_transaction_and_more.py`.

Merge migrations **0022** and **0023** reconcile the graph, but depending on migration order and DB state, you may see **"table already exists"** (or similar) when running `python manage.py migrate` or the full test suite.

**Workarounds:**

- Run tests with `--keepdb` and an existing DB that already has finance migrations applied.
- Or run only the app tests you need, e.g. `python manage.py test apps.evals`.
- To fix properly: add a new merge migration that depends on both 0020s (and any other heads), then ensure all later migrations depend on that merge; or squash the finance migrations (Django’s `squashmigrations`) and re-apply on a clean DB.
