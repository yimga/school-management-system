from django.db import migrations


def seed_widgets(apps, schema_editor):
    DashboardWidget = apps.get_model("siteconfig", "DashboardWidget")
    try:
        DashboardWidget._meta.get_field("slug")
    except Exception:
        # Model no longer has slug; skip seeding.
        return
    widgets = [
        # Finance
        (
            "finance-hero",
            "Finance Hero",
            "finance",
            "main",
            ["FINANCE_STAFF", "LEADERSHIP"],
            0,
        ),
        (
            "finance-summary-receivables",
            "Receivables",
            "finance",
            "main",
            ["FINANCE_STAFF", "LEADERSHIP"],
            1,
        ),
        (
            "finance-summary-payables",
            "Payables",
            "finance",
            "main",
            ["FINANCE_STAFF", "LEADERSHIP"],
            2,
        ),
        (
            "finance-summary-paid",
            "Paid YTD",
            "finance",
            "main",
            ["FINANCE_STAFF", "LEADERSHIP"],
            3,
        ),
        (
            "finance-summary-overdue",
            "Overdue",
            "finance",
            "main",
            ["FINANCE_STAFF", "LEADERSHIP"],
            4,
        ),
        (
            "finance-status-counts",
            "Invoice Status",
            "finance",
            "secondary",
            ["FINANCE_STAFF", "LEADERSHIP"],
            0,
        ),
        (
            "finance-invoice-trend",
            "Invoice Trend",
            "finance",
            "secondary",
            ["FINANCE_STAFF", "LEADERSHIP"],
            1,
        ),
        (
            "finance-recent-invoices",
            "Recent Invoices",
            "finance",
            "secondary",
            ["FINANCE_STAFF", "LEADERSHIP"],
            2,
        ),
        (
            "finance-recent-payments",
            "Recent Payments",
            "finance",
            "secondary",
            ["FINANCE_STAFF", "LEADERSHIP"],
            3,
        ),
        # Analytics
        (
            "analytics-operational-pulse",
            "Operational Pulse",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            0,
        ),
        (
            "analytics-ai-insight",
            "AI Insight",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            1,
        ),
        (
            "analytics-filters",
            "Analytics Filters",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            2,
        ),
        (
            "analytics-top-class-performers",
            "Top Class Performers",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            3,
        ),
        (
            "analytics-weak-subjects",
            "Weak Subjects",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            4,
        ),
        (
            "analytics-teacher-compliance",
            "Teacher Compliance",
            "analytics",
            "main",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            5,
        ),
        (
            "analytics-class-ranking",
            "Class Ranking",
            "analytics",
            "secondary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            0,
        ),
        (
            "analytics-top-class-term",
            "Top Class Term",
            "analytics",
            "secondary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            1,
        ),
        (
            "analytics-top-school-term",
            "Top School Term",
            "analytics",
            "secondary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            2,
        ),
        (
            "analytics-top-class-annual",
            "Top Class Annual",
            "analytics",
            "secondary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            3,
        ),
        (
            "analytics-top-school-annual",
            "Top School Annual",
            "analytics",
            "secondary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            4,
        ),
        (
            "analytics-weak-subject-focus",
            "Weak Subject Focus",
            "analytics",
            "tertiary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            0,
        ),
        (
            "analytics-improvement-list",
            "Improvement List",
            "analytics",
            "tertiary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            1,
        ),
        (
            "analytics-teacher-deadlines",
            "Teacher Deadlines",
            "analytics",
            "tertiary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            2,
        ),
        (
            "analytics-specialty-pass-rates",
            "Specialty Pass Rates",
            "analytics",
            "tertiary",
            ["ADMIN", "LEADERSHIP", "ACADEMICS_STAFF"],
            3,
        ),
        # Entity console
        (
            "entity-create-update",
            "Entity Create/Update",
            "entity-console",
            "main",
            ["ADMIN", "LEADERSHIP", "IT_ADMIN"],
            0,
        ),
        (
            "entity-student-table",
            "Entity Student Table",
            "entity-console",
            "main",
            ["ADMIN", "LEADERSHIP", "IT_ADMIN"],
            1,
        ),
        # Portal KB / landing
        (
            "kb-hero",
            "KB Hero",
            "portal-kb",
            "hero",
            ["PARENT", "TEACHER", "ADMIN", "STUDENT"],
            0,
        ),
        (
            "kb-search",
            "KB Search",
            "portal-kb",
            "main",
            ["PARENT", "TEACHER", "ADMIN", "STUDENT"],
            1,
        ),
        (
            "kb-featured",
            "KB Featured",
            "portal-kb",
            "main",
            ["PARENT", "TEACHER", "ADMIN", "STUDENT"],
            2,
        ),
        (
            "kb-categories",
            "KB Categories",
            "portal-kb",
            "secondary",
            ["PARENT", "TEACHER", "ADMIN", "STUDENT"],
            0,
        ),
        (
            "kb-recent",
            "KB Recent",
            "portal-kb",
            "secondary",
            ["PARENT", "TEACHER", "ADMIN", "STUDENT"],
            1,
        ),
    ]
    for slug, title, page, column, roles, order in widgets:
        DashboardWidget.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "page": page,
                "allowed_roles": roles,
                "default_column": column,
                "default_order": order,
            },
        )


def remove_widgets(apps, schema_editor):
    DashboardWidget = apps.get_model("siteconfig", "DashboardWidget")
    try:
        DashboardWidget._meta.get_field("slug")
    except Exception:
        return
    slugs = [
        "finance-hero",
        "finance-summary-receivables",
        "finance-summary-payables",
        "finance-summary-paid",
        "finance-summary-overdue",
        "finance-status-counts",
        "finance-invoice-trend",
        "finance-recent-invoices",
        "finance-recent-payments",
        "analytics-operational-pulse",
        "analytics-ai-insight",
        "analytics-filters",
        "analytics-top-class-performers",
        "analytics-weak-subjects",
        "analytics-teacher-compliance",
        "analytics-class-ranking",
        "analytics-top-class-term",
        "analytics-top-school-term",
        "analytics-top-class-annual",
        "analytics-top-school-annual",
        "analytics-weak-subject-focus",
        "analytics-improvement-list",
        "analytics-teacher-deadlines",
        "analytics-specialty-pass-rates",
        "entity-create-update",
        "entity-student-table",
        "kb-hero",
        "kb-search",
        "kb-featured",
        "kb-categories",
        "kb-recent",
    ]
    DashboardWidget.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0030_backend_feature_roles"),
    ]

    operations = [
        migrations.RunPython(seed_widgets, reverse_code=remove_widgets),
    ]
