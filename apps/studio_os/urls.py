from django.urls import path
from .views import studio_rollback, studio_shell

app_name = "studio_os"

urlpatterns = [
    path("", studio_shell, name="shell"),
    path("experience/", studio_shell, {"mode": "experience"}, name="experience"),
    path("automation/", studio_shell, {"mode": "automation"}, name="automation"),
    path("output/", studio_shell, {"mode": "output"}, name="output"),
    path("launch/", studio_shell, {"mode": "launch"}, name="launch"),
    path("control/", studio_shell, {"mode": "control"}, name="control"),
    path("rollback/", studio_rollback, name="rollback"),
]
