from django.urls import path

from . import views

app_name = "apicenter"

urlpatterns = [
    path("", views.api_center_dashboard, name="dashboard"),
    path("toggle/<slug:slug>/", views.api_center_toggle, name="toggle"),
    path("docs/", views.api_portal_docs, name="api_portal_docs"),
    path("webhooks/", views.webhook_docs, name="webhook_docs"),
    path("keys/", views.api_keys, name="api_keys"),
    path("keys/create/", views.api_key_create, name="api_key_create"),
    path("keys/<int:key_id>/revoke/", views.api_key_revoke, name="api_key_revoke"),
    path(
        "webhooks/create/",
        views.webhook_subscription_create,
        name="webhook_subscription_create",
    ),
    path(
        "webhooks/<int:pk>/edit/",
        views.webhook_subscription_edit,
        name="webhook_subscription_edit",
    ),
    path(
        "webhooks/<int:pk>/delete/",
        views.webhook_subscription_delete,
        name="webhook_subscription_delete",
    ),
    path("sdk/", views.sdk_docs, name="sdk_docs"),
    path("certification/", views.app_certification, name="app_certification"),
    path("sandbox/", views.partner_sandbox, name="partner_sandbox"),
]
