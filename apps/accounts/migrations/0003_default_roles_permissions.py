from django.db import migrations


PERMISSION_DEFINITIONS = [
    ("attendance.view", "Attendance dashboards", "View attendance dashboards and logs."),
    ("finance.view", "Finance access", "View finance dashboards and invoices."),
    ("reports.manage", "Reports & exports", "Generate reports and exports (PDF/CSV)."),
    ("data.access", "Data exports", "Access student and staff data exports."),
    ("settings.manage", "Backend configuration", "Manage site-wide settings and configuration."),
]

ROLE_DEFINITIONS = {
    "ADMIN": {
        "name": "Administrator",
        "description": "Full access to analytics, settings, finance, and reports.",
        "permissions": [code for code, _, _ in PERMISSION_DEFINITIONS],
    },
    "LEADERSHIP": {
        "name": "Leadership",
        "description": "Access attendance, finance, reports, and key data exports.",
        "permissions": ["attendance.view", "finance.view", "reports.manage", "data.access"],
    },
    "TEACHER": {
        "name": "Teacher",
        "description": "Attendance and reports for classroom duties.",
        "permissions": ["attendance.view", "reports.manage"],
    },
    "PARENT": {
        "name": "Parent",
        "description": "Finance and report access tied to linked students.",
        "permissions": ["finance.view", "reports.manage"],
    },
}


def _create_defaults(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {}
    for code, name, description in PERMISSION_DEFINITIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        perm_map[code] = perm

    for code, data in ROLE_DEFINITIONS.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[perm_code] for perm_code in data["permissions"] if perm_code in perm_map]
        role.permissions.set(perms)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_accessrole_permission_user_profile_photo_user_roles_and_more"),
    ]

    operations = [
        migrations.RunPython(_create_defaults, migrations.RunPython.noop),
    ]
