# The Data Protection Officer role gives up bulk export (2026-08-21).
#
# 0058 created the DPO role holding compliance.view, compliance.manage,
# athletics.medical.manage, athletics.view -- and data.access. The first four
# are that role's named job. data.access is not: its own seed wording (0004)
# is "Export student/staff data across portals", and it gates the governed
# bulk-query surface in apps/analytics/views_governed.py.
#
# Two reasons it comes out, and the second is the one that decides it:
#
# 1. WRONG SHAPE. The case for granting it was subject-access requests
#    (GDPR Art. 15). An SAR concerns ONE data subject. data.access is every
#    student and every staff member in the school. That is not a slightly
#    oversized tool for the job, it is a different tool. Should DPOs turn out
#    to need SAR fulfilment, the right code is a narrow, audited,
#    single-subject export -- not this one, and not built on speculation.
#
# 2. CONFLICT OF INTEREST. Art. 38(6) requires that the DPO hold no role
#    placing them in a position to oversee their own processing, and the CJEU
#    applied that test directly in C-453/21 (X-FAB Dresden). A DPO is an
#    oversight role; bulk export is an operational one. The role that audits
#    whether an export was lawful must not also be the role that performs it.
#
# This is the one place in the RBAC repair series that REMOVES a capability
# rather than restoring intended access, so its scope is deliberately narrow:
#
#   * The GLOBAL template row only (school IS NULL). A tenant that has minted
#     its own school-scoped DPO row keeps whatever it deliberately put on it;
#     narrowing that from here would be exactly the destructive behaviour this
#     release exists to fix.
#   * The ROLE only. A user who holds data.access directly, or through some
#     other role, still holds it -- this migration has no opinion about them.
#
# Idempotent by construction: .remove() of a code the role does not hold is a
# no-op, so it lands correctly whether or not 0058 has been applied on a given
# box, and re-running it changes nothing. Reversible: migrating backwards
# restores 0058's state exactly.

from django.db import migrations

ROLE_CODE = "DPO"
PERMISSION_CODE = "data.access"


def _global_dpo_and_permission(apps):
    """Return (role, permission), either of which may be None on a fresh DB."""
    AccessRole = apps.get_model("accounts", "AccessRole")
    Permission = apps.get_model("accounts", "Permission")
    role = AccessRole.objects.filter(code=ROLE_CODE, school__isnull=True).first()
    permission = Permission.objects.filter(code=PERMISSION_CODE).first()
    return role, permission


def forwards(apps, schema_editor):
    role, permission = _global_dpo_and_permission(apps)
    if role is None or permission is None:
        return
    role.permissions.remove(permission)


def backwards(apps, schema_editor):
    role, permission = _global_dpo_and_permission(apps)
    if role is None or permission is None:
        return
    role.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0059_discipline_refer_and_finance_view_invoice"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
