from django.urls import path
from . import views

app_name = "orchestration"
urlpatterns = [
    path("workbench/", views.operator_workbench, name="operator_workbench"),
    path("runs/<int:run_id>/retry/", views.retry_run, name="retry_run"),
]
