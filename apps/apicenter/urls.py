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
]
