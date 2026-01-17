from django.urls import path

from .views import maintenance_view, customizer, clear_preview

app_name = "siteconfig"

urlpatterns = [
    path("maintenance/", maintenance_view, name="maintenance"),
    path("customizer/", customizer, name="customizer"),
    path("customizer/clear-preview/", clear_preview, name="clear_preview"),
]
