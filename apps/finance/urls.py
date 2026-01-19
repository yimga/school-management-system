from django.urls import path

from .views import (
    dashboard,
    generate_fees,
    invoice_detail,
    invoice_list,
    invoice_receipt,
    payment_list,
    payment_provider_webhook,
    trial_balance,
    finance_reports,
    notifications,
    submit_report_request,
)

app_name = "finance"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("invoices/", invoice_list, name="invoices"),
    path("invoices/<int:invoice_id>/", invoice_detail, name="invoice_detail"),
    path("invoices/<int:invoice_id>/receipt/", invoice_receipt, name="invoice_receipt"),
    path("payments/", payment_list, name="payments"),
    path("fees/generate/", generate_fees, name="generate_fees"),
    path("trial-balance/", trial_balance, name="trial_balance"),
    path("payments/webhook/<str:provider_slug>/", payment_provider_webhook, name="payment_webhook"),
    path("reports/", finance_reports, name="reports"),
    path("reports/request/", submit_report_request, name="report_request"),
    path("notifications/", notifications, name="notifications"),
]
