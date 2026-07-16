from django.urls import path

from .views import (
    approve_run,
    create_run,
    dashboard,
    employee_leave,
    employee_payslips,
    export_disbursement,
    generate_run,
    mark_run_paid,
    payslip_pdf,
    review_run,
    run_detail,
)

app_name = "payroll"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("runs/create/", create_run, name="create_run"),
    path("runs/<int:run_id>/", run_detail, name="run_detail"),
    path("runs/<int:run_id>/generate/", generate_run, name="generate_run"),
    path("runs/<int:run_id>/review/", review_run, name="review_run"),
    path("runs/<int:run_id>/approve/", approve_run, name="approve_run"),
    path("runs/<int:run_id>/mark-paid/", mark_run_paid, name="mark_run_paid"),
    path(
        "runs/<int:run_id>/disbursement.csv",
        export_disbursement,
        name="export_disbursement",
    ),
    path("employee/payslips/", employee_payslips, name="employee_payslips"),
    path(
        "payslips/<int:payslip_id>/pdf/", payslip_pdf, name="payslip_pdf"
    ),
    path("employee/leave/", employee_leave, name="employee_leave"),
]
