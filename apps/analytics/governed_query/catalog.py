"""
Allowlisted datasets, fields, filters, and aggregations for governed queries.

NO raw SQL — executor maps these definitions to Django ORM only.
"""

from __future__ import annotations

from typing import Any

# Any of these feature permissions grants access to the dataset (see accounts.Permission).
_DEFAULT_REPORT_PERMS: tuple[str, ...] = ("reports.manage", "data.access")

MAX_EXPORT_ROWS = 5000

# aggregation_name -> allowed metric fields (numeric) or "*" for count-only
AGGREGATIONS: tuple[str, ...] = ("count", "sum", "avg", "min", "max")

DATASETS: dict[str, dict[str, Any]] = {
    "students": {
        "label": "Students",
        "permissions": _DEFAULT_REPORT_PERMS,
        "tenant_field": "school_id",
        "model": "people.StudentProfile",
        "fields": (
            "id",
            "first_name",
            "last_name",
            "student_code",
            "is_active",
            "classroom_id",
            "academic_year_id",
            "school_id",
            "created_at",
            "classroom__name",
            "classroom__code",
        ),
        "filters": frozenset(
            {"classroom_id", "is_active", "academic_year_id", "student_code"}
        ),
        "group_by": frozenset({"classroom_id", "academic_year_id", "is_active"}),
        "aggregate_fields": frozenset({"id"}),  # count(id)
    },
    "attendance": {
        "label": "Attendance",
        "permissions": ("reports.manage", "data.access", "attendance.view"),
        "tenant_field": "school_id",
        "model": "academics.Attendance",
        "fields": (
            "id",
            "date",
            "status",
            "student_id",
            "classroom_id",
            "school_id",
            "notes",
            "student__first_name",
            "student__last_name",
            "classroom__name",
        ),
        "filters": frozenset({"classroom_id", "status", "date__gte", "date__lte"}),
        "group_by": frozenset({"classroom_id", "status", "date"}),
        "aggregate_fields": frozenset({"id"}),
        "date_fields": ("date",),
    },
    "marks": {
        "label": "Marks / evaluations",
        "permissions": _DEFAULT_REPORT_PERMS,
        "tenant_field": "school_id",
        "model": "evals.Evaluation",
        "fields": (
            "id",
            "final_score",
            "letter_grade",
            "student_id",
            "term_id",
            "academic_year_id",
            "school_id",
            "subject_assignment_id",
            "student__first_name",
            "student__last_name",
        ),
        "filters": frozenset(
            {"term_id", "academic_year_id", "student_id", "subject_assignment_id"}
        ),
        "group_by": frozenset({"term_id", "letter_grade", "subject_assignment_id"}),
        "aggregate_fields": frozenset({"final_score", "id"}),
    },
    "invoices": {
        "label": "Invoices",
        "permissions": ("finance.view", "finance.manage", "reports.manage"),
        "tenant_field": "school_id",
        "model": "finance.Invoice",
        "fields": (
            "id",
            "status",
            "total_amount",
            "balance_amount",
            "student_id",
            "school_id",
            "created_at",
            "due_date",
        ),
        "filters": frozenset({"status", "student_id", "created_at__gte", "created_at__lte"}),
        "group_by": frozenset({"status"}),
        "aggregate_fields": frozenset({"total_amount", "balance_amount", "id"}),
    },
    "payments": {
        "label": "Payments",
        "permissions": ("finance.view", "finance.manage", "reports.manage"),
        "tenant_field": "school_id",
        "model": "finance.Payment",
        "fields": (
            "id",
            "amount",
            "status",
            "student_id",
            "school_id",
            "created_at",
            "purpose",
            "method",
            "payment_method_id",
        ),
        "filters": frozenset({"status", "student_id", "created_at__gte", "created_at__lte"}),
        "group_by": frozenset({"status", "purpose", "payment_method_id"}),
        "aggregate_fields": frozenset({"amount", "id"}),
    },
    "report_cards": {
        "label": "Generated report cards",
        "permissions": _DEFAULT_REPORT_PERMS,
        "tenant_field": "school_id",
        "model": "reports.ReportCard",
        "fields": (
            "id",
            "type",
            "student_id",
            "academic_year_id",
            "term_id",
            "school_id",
            "generated_at",
            "language",
        ),
        "filters": frozenset({"type", "term_id", "academic_year_id", "student_id"}),
        "group_by": frozenset({"type", "term_id"}),
        "aggregate_fields": frozenset({"id"}),
    },
    "teachers_classes": {
        "label": "Teachers & classes",
        "permissions": _DEFAULT_REPORT_PERMS,
        "tenant_field": "school_id",
        "model": "people.TeacherProfile",
        "fields": (
            "id",
            "user_id",
            "school_id",
            "staff_id",
            "is_active",
            "user__first_name",
            "user__last_name",
            "user__email",
        ),
        "filters": frozenset({"staff_id", "is_active"}),
        "group_by": frozenset({"is_active"}),
        "aggregate_fields": frozenset({"id"}),
        "notes": "Teacher roster; pair with students dataset for class rolls.",
    },
    "marketplace_installs": {
        "label": "Marketplace app installations",
        "permissions": ("reports.manage", "settings.manage", "portal.manage"),
        "tenant_field": "school_id",
        "model": "marketplace.AppInstallation",
        "fields": (
            "id",
            "school_id",
            "status",
            "install_phase",
            "installed_at",
            "installed_version",
            "health_status",
            "app_id",
            "app__slug",
            "app__name",
        ),
        "filters": frozenset({"status", "install_phase", "app_id"}),
        "group_by": frozenset({"status", "install_phase"}),
        "aggregate_fields": frozenset({"id"}),
    },
    "funnel_events": {
        "label": "Growth funnel events",
        "permissions": ("reports.manage", "settings.manage"),
        "tenant_field": "school_id",
        "model": "schools.MarketingFunnelEvent",
        "fields": (
            "id",
            "event_type",
            "school_id",
            "utm_source",
            "utm_medium",
            "created_at",
            "session_key",
        ),
        "filters": frozenset(
            {"event_type", "utm_source", "created_at__gte", "created_at__lte"}
        ),
        "group_by": frozenset({"event_type", "utm_source"}),
        "aggregate_fields": frozenset({"id"}),
    },
}


def list_dataset_ids() -> list[str]:
    return sorted(DATASETS.keys())


def max_export_rows() -> int:
    return MAX_EXPORT_ROWS
