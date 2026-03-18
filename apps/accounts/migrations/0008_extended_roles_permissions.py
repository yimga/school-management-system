from django.db import migrations


def create_extended_roles(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {p.code: p for p in Permission.objects.all()}
    all_codes = list(perm_map.keys())

    role_definitions = {
        "SUPERADMIN": {
            "name": "Super Administrator",
            "description": "Full control over all modules and settings.",
            "permissions": all_codes,
        },
        "DEPT_LEAD": {
            "name": "Department Lead",
            "description": "Oversees department academics and reporting.",
            "permissions": [
                "reports.manage",
                "attendance.manage",
                "portal.manage",
                "data.access",
            ],
        },
        "FINANCE_STAFF": {
            "name": "Finance Staff",
            "description": "Handles finance dashboards, invoices, and payments.",
            "permissions": [
                "finance.view",
                "finance.manage",
                "reports.manage",
                "data.access",
            ],
        },
        "ACADEMICS_STAFF": {
            "name": "Academics Staff",
            "description": "Supports academics, attendance, and reporting.",
            "permissions": [
                "reports.manage",
                "attendance.manage",
                "portal.manage",
                "data.access",
            ],
        },
        "COMMS_STAFF": {
            "name": "Communications Staff",
            "description": "Manages announcements and portal communications.",
            "permissions": ["communication.manage", "portal.manage"],
        },
    }

    for code, data in role_definitions.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_userpreference"),
    ]

    operations = [
        migrations.RunPython(create_extended_roles, migrations.RunPython.noop),
    ]
