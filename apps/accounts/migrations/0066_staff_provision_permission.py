"""The permission that gates approving an identity.

Separate from every other staff permission on purpose. ``people.change_teacherprofile``
means "may edit staff records"; this means "may bring a new person into existence
with an account". The identity hold exists precisely because those are different
decisions, so they must not share a gate -- otherwise the handshake the hold
requires is reachable by anyone who can fix a phone number.

Granted to the roles that already own who-may-sign-in: ADMIN, PRINCIPAL,
LEADERSHIP, PROPRIETOR and IT_ADMIN. Not to SECRETARY or HOD, who administer
staff data without deciding who gets an account.
"""

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "staff.provision",
        "Approve identity provisioning",
        "Approve or decline a box's request to create a staff member or guardian "
        "who needs a login. This is an authentication decision, not a data edit.",
    ),
]

ROLES_GRANTED = ["ADMIN", "PRINCIPAL", "LEADERSHIP", "PROPRIETOR", "IT_ADMIN"]


def seed(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    perms = []
    for code, name, description in NEW_PERMISSIONS:
        perm = Permission.objects.filter(code=code).first()
        if perm is None:
            perm = Permission.objects.create(
                code=code, name=name, description=description
            )
        perms.append(perm)

    if not perms:
        return
    for role_code in ROLES_GRANTED:
        # Global template rows only (school IS NULL): a tenant-minted catalog row
        # sharing a code must not be granted a platform-level capability.
        role = AccessRole.objects.filter(code=role_code, school__isnull=True).first()
        if role is None:
            continue
        role.permissions.add(*perms)


def noop(apps, schema_editor):
    """Additive; nothing to unwind."""


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0065_support_staff_roles"),
    ]

    operations = [
        migrations.RunPython(seed, noop),
    ]
