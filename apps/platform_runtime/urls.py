from django.urls import path

from apps.platform_runtime.views_tenant_lifecycle import tenant_lifecycle_dashboard

urlpatterns = [
    path(
        "lifecycle/",
        tenant_lifecycle_dashboard,
        name="tenant_lifecycle_dashboard",
    ),
]
