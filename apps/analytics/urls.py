from django.urls import path

from .views import dashboard, master_sheet, grading_deadlines

app_name = "analytics"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("master-sheet/", master_sheet, name="master_sheet"),
    path("deadlines/", grading_deadlines, name="deadlines"),
]
