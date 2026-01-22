"""
Backend Dashboard URLs
Separated from main accounts URLs for cleaner routing at /backend/
"""
from django.urls import path

from .views import backend_dashboard, rbac_dashboard

app_name = "backend"

urlpatterns = [
    path("", backend_dashboard, name="dashboard"),
    path("rbac/", rbac_dashboard, name="rbac"),
]
