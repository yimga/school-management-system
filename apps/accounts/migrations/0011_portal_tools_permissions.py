# Generated for per-feature RBAC: Portal Tools (Community, Video, Documents)

from django.db import migrations


PORTAL_TOOL_PERMISSIONS = [
    ("portal.forums", "Portal: Community / Forums", "Access to community and forums in the portal."),
    ("portal.video", "Portal: Video Hub", "Access to the video hub in the portal."),
    ("portal.documents", "Portal: Documents", "Access to the document library in the portal."),
]

# Roles that get all three portal tool permissions by default (admin can remove later).
ROLES_WITH_PORTAL_TOOLS = ["PARENT", "TEACHER", "ADMIN", "LEADERSHIP", "IT_ADMIN"]


def add_portal_tool_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {}
    for code, name, description in PORTAL_TOOL_PERMISSIONS:
        perm, _ = Permission.objects.get_or_create(
            code=code,
            defaults={"name": name, "description": description},
        )
        perm_map[code] = perm

    new_codes = [p[0] for p in PORTAL_TOOL_PERMISSIONS]
    for role_code in ROLES_WITH_PORTAL_TOOLS:
        role = AccessRole.objects.filter(code=role_code).first()
        if not role:
            continue
        existing = set(role.permissions.values_list("code", flat=True))
        to_add = [perm_map[c] for c in new_codes if c not in existing]
        if to_add:
            role.permissions.add(*to_add)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_alter_user_role"),
    ]

    operations = [
        migrations.RunPython(add_portal_tool_permissions, noop),
    ]
