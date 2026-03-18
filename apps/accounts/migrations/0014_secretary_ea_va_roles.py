# Generated for Phase C: SECRETARY, EXECUTIVE_ASSISTANT, VIRTUAL_ASSISTANT AccessRoles

from django.db import migrations


ROLE_DEFINITIONS = {
    "SECRETARY": {
        "name": "Secretary",
        "description": "Front office, communications, and portal support.",
        "permissions": ["portal.manage", "communication.manage", "reports.manage"],
    },
    "EXECUTIVE_ASSISTANT": {
        "name": "Executive Assistant",
        "description": "Supports leadership with communications and portal access.",
        "permissions": ["portal.manage", "communication.manage", "reports.manage"],
    },
    "VIRTUAL_ASSISTANT": {
        "name": "Virtual Assistant",
        "description": "Remote support for communications and portal.",
        "permissions": ["portal.manage", "communication.manage", "reports.manage"],
    },
}


def create_roles(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")
    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, data in ROLE_DEFINITIONS.items():
        role, _ = AccessRole.objects.get_or_create(
            code=code,
            defaults={"name": data["name"], "description": data["description"]},
        )
        perms = [perm_map[p] for p in data["permissions"] if p in perm_map]
        if perms:
            role.permissions.set(perms)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_set_superusers_to_superadmin_role"),
    ]

    operations = [
        migrations.RunPython(create_roles, noop),
    ]
