from django.urls import path

from .views import request_detail, request_module_access, requests_dashboard

app_name = "requests"

urlpatterns = [
    path("", requests_dashboard, name="dashboard"),
    path("module-access/", request_module_access, name="module_access"),
    path("<uuid:request_id>/", request_detail, name="detail"),
]
