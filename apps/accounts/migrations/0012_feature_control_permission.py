# Add Feature Control as an assignable RBAC permission

from django.db import migrations


FEATURE_CONTROL_PERMISSION = (
    "settings.feature_control",
    "Feature Control Panel",
    "Toggle modules and features system-wide (portals, reports, grade approval, etc.).",
)

# Roles that get Feature Control by default (admin can assign to other roles/users)
ROLES_WITH_FEATURE_CONTROL = ["ADMIN", "IT_ADMIN"]


def add_feature_control_permission(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm, _ = Permission.objects.get_or_create(
        code=FEATURE_CONTROL_PERMISSION[0],
        defaults={
            "name": FEATURE_CONTROL_PERMISSION[1],
            "description": FEATURE_CONTROL_PERMISSION[2],
        },
    )

    for role_code in ROLES_WITH_FEATURE_CONTROL:
        role = AccessRole.objects.filter(code=role_code).first()
        if (
            role
            and not role.permissions.filter(code=FEATURE_CONTROL_PERMISSION[0]).exists()
        ):
            role.permissions.add(perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0011_portal_tools_permissions"),
    ]

    operations = [
        migrations.RunPython(add_feature_control_permission, noop),
    ]
