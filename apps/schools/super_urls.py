from django.urls import path
from . import super_views
from .parent_tenant_views import parent_tenant_dashboard

app_name = "super"

urlpatterns = [
    path("", super_views.super_dashboard, name="dashboard"),
    path("create/", super_views.create_school_wizard, name="create_school_wizard"),
    path("api/create-school/", super_views.api_create_school, name="api_create_school"),
    path("parent-tenant/", parent_tenant_dashboard, name="parent_tenant_dashboard"),
]
