from django.urls import path

from .views import (
    dashboard,
    generate_fees,
    notify_guardians_new_invoices,
    invoice_detail,
    invoice_list,
    invoice_receipt,
    payment_list,
    payment_provider_webhook,
    request_finance_access,
    finance_access_bulk,
    trial_balance,
    finance_reports,
    notifications,
    submit_report_request,
    finance_requests,
    upload_payment_receipt,
    resend_reminder,
)

app_name = "finance"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("invoices/", invoice_list, name="invoices"),
    path("invoices/<int:invoice_id>/", invoice_detail, name="invoice_detail"),
    path("invoices/<int:invoice_id>/request-access/", request_finance_access, name="invoice_request_access"),
    path("invoices/<int:invoice_id>/receipt/", invoice_receipt, name="invoice_receipt"),
    path("invoices/<int:invoice_id>/upload-receipt/", upload_payment_receipt, name="upload_payment_receipt"),
    path("invoices/<int:invoice_id>/resend-reminder/", resend_reminder, name="resend_reminder"),
    path("access/request/", request_finance_access, name="finance_request_access"),
    path("access/bulk/", finance_access_bulk, name="finance_access_bulk"),
    path("payments/", payment_list, name="payments"),
    path("payments/receipts/", payment_list, name="payment_receipts"),
    path("fees/generate/", generate_fees, name="generate_fees"),
    path("fees/notify-guardians/", notify_guardians_new_invoices, name="notify_guardians_new_invoices"),
    path("trial-balance/", trial_balance, name="trial_balance"),
    path("payments/webhook/<str:provider_slug>/", payment_provider_webhook, name="payment_webhook"),
    path("reports/", finance_reports, name="reports"),
    path("reports/request/", submit_report_request, name="report_request"),
    path("notifications/", notifications, name="notifications"),
    path("requests/", finance_requests, name="requests"),
]
