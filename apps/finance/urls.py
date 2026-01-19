from django.urls import path

from .views import dashboard, generate_fees, invoice_list, payment_list, trial_balance

app_name = "finance"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("invoices/", invoice_list, name="invoices"),
    path("payments/", payment_list, name="payments"),
    path("fees/generate/", generate_fees, name="generate_fees"),
    path("trial-balance/", trial_balance, name="trial_balance"),
]
