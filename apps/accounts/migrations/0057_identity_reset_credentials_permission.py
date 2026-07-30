# Tenant-admin credential recovery (2026-07-30): a school delegate can reset another
# member's password (temp password + forced change) and reset their MFA (clear devices
# so they re-enroll). Add a narrow `identity.reset_credentials` code so the capability
# is grantable to a custom "IT support / help desk" role WITHOUT widening any broader
# admin surface. Additive (get_or_create + .add()); mirrors 0049.
#
# The require_permission gate on the reset views also admits the ADMIN-like owner tier
# by default (allow_admin=True), so these grants exist to make the code assignable to
# the leadership/IT roles that are not ADMIN-like AND to surface it in the RBAC
# dashboard picker.

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "identity.reset_credentials",
        "Reset member credentials",
        "Reset another member's password (temp password) and reset their MFA.",
    ),
]

# The tenant-admin / IT tier. Owners always pass via the ownership guard; these grants
# make the code grantable to the admin-adjacent roles and to custom support roles.
ROLE_GRANTS = {
    "ADMIN": ["identity.reset_credentials"],
    "SUPERADMIN": ["identity.reset_credentials"],
    "PROPRIETOR": ["identity.reset_credentials"],
    "PRINCIPAL": ["identity.reset_credentials"],
    "VICE_PRINCIPAL": ["identity.reset_credentials"],
    "LEADERSHIP": ["identity.reset_credentials"],
    "IT_ADMIN": ["identity.reset_credentials"],
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
        ("accounts", "0056_user_mfa_setup_deferred_until"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
