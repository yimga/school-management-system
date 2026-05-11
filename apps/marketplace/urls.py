from django.urls import path

from apps.marketplace import views
from apps.marketplace.views_publisher import publisher_app_detail, publisher_dashboard


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
]
