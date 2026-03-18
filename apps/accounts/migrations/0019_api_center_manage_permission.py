# Add api_center.manage permission and assign to ADMIN, IT_ADMIN, SUPERADMIN

from django.db import migrations


def add_api_center_manage(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")
    perm, _ = Permission.objects.get_or_create(
        code="api_center.manage",
        defaults={
            "name": "API Center management",
            "description": "Toggle and manage APIs in the API Center; view audit log.",
        },
    )
    for role_code in ("ADMIN", "IT_ADMIN", "SUPERADMIN"):
        role = AccessRole.objects.filter(code=role_code).first()
        if role and perm not in role.permissions.all():
            role.permissions.add(perm)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0018_cahier_verify_permission"),
    ]

    operations = [
        migrations.RunPython(add_api_center_manage, noop),
    ]
