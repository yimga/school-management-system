from django.urls import path

from apps.marketplace import views
from apps.marketplace.views_publisher import publisher_app_detail, publisher_dashboard
from apps.marketplace.views_monetization_inspector import MonetizationManifestInspectorView


app_name = "marketplace"


urlpatterns = [
    path("governance/", views.governance_console, name="governance_console"),
    path(
        "reviews/<int:review_id>/action/",
        views.marketplace_review_action,
        name="review_action",
    ),
    # Pass 14.D: publisher-facing dashboard on top of the submission endpoint.
    path("publisher/", publisher_dashboard, name="publisher_dashboard"),
    path("publisher/<slug:slug>/", publisher_app_detail, name="publisher_app_detail"),
    # v4.00.13: monetization manifest inspector (staff-only).
    path(
        "monetization-inspector/",
        MonetizationManifestInspectorView.as_view(),
        name="monetization_inspector",
    ),
]
