"""
Finance app views — thin re-export hub (§6.15 full split).

All view functions are implemented in subdomain modules; this module
re-exports them so urlconf and any existing imports continue to work
unchanged. Do not add new view logic here.

Submodules:
- views_common: shared helpers and constants
- views_dashboard: dashboard
- views_accounting: trial balance, bursar entries, expense vs budget, suspense
- views_requests: notifications, finance_requests
- views_invoicing: invoice list/detail/receipt, generate_fees, notify guardians, upload receipt, resend_reminder
- views_payments: payment list, cash_office_closure, split_allocation, scan_teller_placeholder, payment_provider_webhook
- views_access: request_finance_access, finance_access_bulk
- views_reports: finance_reports, submit_report_request
"""
from __future__ import annotations

from .views_dashboard import dashboard
from .views_accounting import (
    trial_balance,
    bursar_entries_report,
    expense_vs_budget,
    suspense_queue,
    claim_suspense_payment,
)
from .views_requests import notifications, finance_requests
from .views_invoicing import (
    invoice_list,
    invoice_detail,
    invoice_receipt,
    generate_fees,
    notify_guardians_new_invoices,
    upload_payment_receipt,
    resend_reminder,
)
from .views_payments import (
    payment_list,
    cash_office_closure,
    split_allocation,
    scan_teller_placeholder,
    payment_provider_webhook,
)
from .views_access import request_finance_access, finance_access_bulk
from .views_reports import finance_reports, submit_report_request

__all__ = [
    "dashboard",
    "trial_balance",
    "bursar_entries_report",
    "expense_vs_budget",
    "suspense_queue",
    "claim_suspense_payment",
    "notifications",
    "finance_requests",
    "invoice_list",
    "invoice_detail",
    "invoice_receipt",
    "generate_fees",
    "notify_guardians_new_invoices",
    "upload_payment_receipt",
    "resend_reminder",
    "payment_list",
    "cash_office_closure",
    "split_allocation",
    "scan_teller_placeholder",
    "payment_provider_webhook",
    "request_finance_access",
    "finance_access_bulk",
    "finance_reports",
    "submit_report_request",
]
