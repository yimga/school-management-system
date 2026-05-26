from django.urls import path

from .views import (
    create_run,
    dashboard,
    employee_leave,
    employee_payslips,
    export_disbursement,
    generate_run,
    run_detail,
)

app_name = "payroll"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("runs/create/", create_run, name="create_run"),
    path("runs/<int:run_id>/", run_detail, name="run_detail"),
    path("runs/<int:run_id>/generate/", generate_run, name="generate_run"),
    path(
        "runs/<int:run_id>/disbursement.csv",
        export_disbursement,
        name="export_disbursement",
    ),
    path("employee/payslips/", employee_payslips, name="employee_payslips"),
    path("employee/leave/", employee_leave, name="employee_leave"),
]
