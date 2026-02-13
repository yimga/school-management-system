from django.urls import path

from . import views

app_name = "apicenter"

urlpatterns = [
    path("", views.api_center_dashboard, name="dashboard"),
    path("toggle/<slug:slug>/", views.api_center_toggle, name="toggle"),
]
