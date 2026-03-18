from django.urls import path

from apps.marketplace import views


app_name = "marketplace"


urlpatterns = [
    path("governance/", views.governance_console, name="governance_console"),
    path(
        "reviews/<int:review_id>/action/",
        views.marketplace_review_action,
        name="review_action",
    ),
]
