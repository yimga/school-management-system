from django.urls import path
from . import super_views
from .parent_tenant_views import parent_tenant_dashboard

app_name = "super"

urlpatterns = [
    path("", super_views.super_dashboard, name="dashboard"),
    path("create/", super_views.create_school_wizard, name="create_school_wizard"),
    path("api/create-school/", super_views.api_create_school, name="api_create_school"),
    path("api/schools/<uuid:school_id>/timeline/", super_views.api_school_timeline, name="api_school_timeline"),
    path("api/schools/<uuid:school_id>/approve/", super_views.api_approve_school, name="api_approve_school"),
    path("api/geo/cities/", super_views.api_geo_cities, name="api_geo_cities"),
    path("api/geo/timezones/", super_views.api_geo_timezones, name="api_geo_timezones"),
    path("api/provinces/", super_views.api_provinces, name="api_provinces"),
    path("api/education-profiles/", super_views.api_education_profiles, name="api_education_profiles"),
    path("api/system-blueprint/", super_views.api_system_blueprint, name="api_system_blueprint"),
    path("api/plans-configurator/", super_views.api_plans_configurator, name="api_plans_configurator"),
    path("parent-tenant/", parent_tenant_dashboard, name="parent_tenant_dashboard"),
    path("usage/", super_views.super_usage, name="usage"),
    path("pulse/", super_views.super_pulse, name="pulse"),
    path("tenant-health/", super_views.super_tenant_health, name="tenant_health"),
    path("billing/", super_views.billing_dashboard, name="billing_dashboard"),
    path("support/", super_views.super_support_dashboard, name="support_dashboard"),
    path("support/queue/", super_views.support_queue_fragment, name="support_queue_fragment"),
    path("switch-to-tenant/", super_views.switch_to_tenant, name="switch_to_tenant"),
    path("sync-repair/<uuid:school_id>/", super_views.sync_repair, name="sync_repair"),
]
