# Analytics-admin console code (2026-07-06 follow-up): the analytics admin consoles
# (dashboard / master_sheet) were the last coarse @tenant_admin_required operational
# surfaces. Add a narrow `analytics.manage` code so they gate on a granular permission a
# leadership/analytics-admin custom role can be granted — WITHOUT widening them to the broad
# `analytics.view` teacher seed. Additive (get_or_create + .add()); mirrors 0048.

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "analytics.manage",
        "Analytics management",
        "Manage analytics consoles, master sheet, and analytics configuration.",
    ),
]

# The analytics-admin / leadership tier (NOT teachers — analytics.manage is deliberately
# narrower than analytics.view). allow_admin=True on the decorator already admits the
# ADMIN-like owner tier; these grants make the code grantable to the academic-leadership
# roles (HOD is not ADMIN-like) and to custom analytics-admin roles.
ROLE_GRANTS = {
    "ADMIN": ["analytics.manage"],
    "SUPERADMIN": ["analytics.manage"],
    "LEADERSHIP": ["analytics.manage"],
    "PROPRIETOR": ["analytics.manage"],
    "PRINCIPAL": ["analytics.manage"],
    "VICE_PRINCIPAL": ["analytics.manage"],
    "DEAN": ["analytics.manage"],
    "IT_ADMIN": ["analytics.manage"],
    "HOD": ["analytics.manage"],
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm_map[code] = Permission.objects.create(
                code=code, name=name, description=description
            )

    for role_code, codes in ROLE_GRANTS.items():
        for role in AccessRole.objects.filter(code=role_code):
            for c in codes:
                perm = perm_map.get(c)
                if perm is not None:
                    role.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0048_rbac_completion_codes"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
