from django.urls import path

from apps.platform_runtime.views_administration import (
    blueprint_apply_view,
    blueprint_detail,
    blueprint_impact_view,
    blueprint_installation_detail,
    blueprint_installations,
    blueprint_marketplace,
    blueprint_preview_view,
    blueprint_rollback_view,
    configuration_center,
    configuration_module_detail,
)

app_name = "configuration"

urlpatterns = [
    path("", configuration_center, name="center"),
    path("blueprints/", blueprint_marketplace, name="blueprint_marketplace"),
    path("blueprints/installations/", blueprint_installations, name="blueprint_installations"),
    path(
        "blueprints/installations/<int:installation_id>/",
        blueprint_installation_detail,
        name="blueprint_installation_detail",
    ),
    path(
        "blueprints/installations/<int:installation_id>/rollback/",
        blueprint_rollback_view,
        name="blueprint_rollback",
    ),
    path("blueprints/<slug:key>/", blueprint_detail, name="blueprint_detail"),
    path("blueprints/<slug:key>/preview/", blueprint_preview_view, name="blueprint_preview"),
    path("blueprints/<slug:key>/impact/", blueprint_impact_view, name="blueprint_impact"),
    path("blueprints/<slug:key>/apply/", blueprint_apply_view, name="blueprint_apply"),
    path("<slug:module_key>/", configuration_module_detail, name="module_detail"),
]
