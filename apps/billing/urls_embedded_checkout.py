"""Wave P-C (v3.95.1 — 2026-05-26) — Embedded checkout URL patterns.

Mounted at ``/billing/embedded-checkout/`` in ``config/urls.py``.
"""

from django.urls import path

from . import views_embedded_checkout


app_name = "billing_embedded_checkout"

urlpatterns = [
    path(
        "session/",
        views_embedded_checkout.create_embedded_checkout_session,
        name="create_session",
    ),
]
