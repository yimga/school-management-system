"""
Legacy include target (purchase-intent only).

Tenant ``marketplace`` namespace routes are registered from ``config.tenant_urls`` via
``apps.marketplace.urls_merged`` (purchase intent + semver rollback) so all names share one
``marketplace:`` namespace.
"""

from django.urls import path

from apps.marketplace import views
from apps.marketplace import views_monetization_dashboard
from apps.marketplace.views_publisher import publisher_app_detail, publisher_dashboard

app_name = "marketplace"

urlpatterns = [
    path(
        "monetization/",
        views_monetization_dashboard.monetization_dashboard,
        name="monetization_dashboard",
    ),
    path(
        "app/<int:app_id>/purchase-intent/",
        views.app_purchase_intent,
        name="app_purchase_intent",
    ),
    # Pass 14.D: publisher-facing dashboard. Mounted here (the file actually
    # wired into config.tenant_urls) so `marketplace:publisher_dashboard`
    # resolves.
    path("publisher/", publisher_dashboard, name="publisher_dashboard"),
    path("publisher/<slug:slug>/", publisher_app_detail, name="publisher_app_detail"),
]
