from django.db import migrations


def seed_widgets(apps, schema_editor):
    DashboardWidget = apps.get_model("siteconfig", "DashboardWidget")
    try:
        DashboardWidget._meta.get_field("slug")
    except Exception:
        # Model no longer has slug; skip seeding.
        return

    role_admin = [
        "SUPERADMIN",
        "ADMIN",
        "IT_ADMIN",
        "LEADERSHIP",
        "PRINCIPAL",
        "VICE_PRINCIPAL",
    ]

    widgets = [
        ("admin-total-users", "Total Users", "admin-security", "main", role_admin, 0),
        ("admin-db-app-stats", "Database & App Stats", "admin-security", "main", role_admin, 1),
        ("admin-system-health", "System Health", "admin-security", "main", role_admin, 2),
        ("admin-active-users-security", "Active Users / Security", "admin-security", "main", role_admin, 3),
        ("admin-calendar-widget", "Calendar", "admin-security", "side", role_admin, 0),
        ("admin-controls", "Admin Controls", "admin-security", "lower", role_admin, 0),
        ("admin-system-information", "System Information", "admin-security", "lower", role_admin, 1),
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
        "admin-total-users",
        "admin-db-app-stats",
        "admin-system-health",
        "admin-active-users-security",
        "admin-calendar-widget",
        "admin-controls",
        "admin-system-information",
    ]
    DashboardWidget.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0031_seed_more_dashboard_widgets"),
    ]

    operations = [
        migrations.RunPython(seed_widgets, reverse_code=remove_widgets),
    ]

