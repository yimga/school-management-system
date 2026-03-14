"""Automation app URLs. Step 41: outcomes console (bounded console for outcomes, not raw settings)."""
from django.urls import path

from . import views

app_name = "automation"

urlpatterns = [
    path("outcomes/", views.outcomes_console, name="outcomes_console"),
]
