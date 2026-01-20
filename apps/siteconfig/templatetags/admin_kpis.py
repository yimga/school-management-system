from __future__ import annotations

from django import template
from django.apps import apps as django_apps

register = template.Library()


@register.simple_tag
def admin_kpis():
    """
    Lightweight KPI snapshot for admin dashboard cards.
    Keeps queries shallow to avoid slowing the index page.
    """
    Student = django_apps.get_model("people", "StudentProfile")
    Subject = django_apps.get_model("academics", "Subject")
    Report = django_apps.get_model("reports", "ReportCard") if django_apps.is_installed("reports") else None
    Invoice = django_apps.get_model("finance", "Invoice")

    students = Student.objects.count()
    subjects = Subject.objects.count()
    report_count = Report.objects.count() if Report else 0

    invoices = Invoice.objects.all()
    overdue = invoices.filter(status="OVERDUE").count() if hasattr(Invoice, "Status") else 0
    due_today = invoices.filter(status="ISSUED").count() if hasattr(Invoice, "Status") else 0

    return {
        "students": students,
        "subjects": subjects,
        "report_cards": report_count,
        "invoices_overdue": overdue,
        "invoices_due_today": due_today,
    }
