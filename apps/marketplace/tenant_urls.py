"""Tenant-scoped marketplace routes (namespaced ``marketplace``)."""

from django.urls import path

from apps.marketplace import views

app_name = "marketplace"

urlpatterns = [
    path(
        "app/<int:app_id>/purchase-intent/",
        views.app_purchase_intent,
        name="app_purchase_intent",
    ),
]
