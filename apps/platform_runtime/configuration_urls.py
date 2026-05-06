from django.urls import path

from apps.platform_runtime.views_administration import (
    configuration_center,
    configuration_module_detail,
)

app_name = "configuration"

urlpatterns = [
    path("", configuration_center, name="center"),
    path("<slug:module_key>/", configuration_module_detail, name="module_detail"),
]
