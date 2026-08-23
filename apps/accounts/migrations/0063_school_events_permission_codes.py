# Grantable permission codes for the school-events console (2026-08-23).
#
# apps/school_events/views.py gated its console on @login_required alone, so any
# authenticated tenant member -- a student, a parent -- could open the events hub
# and see every DRAFT event plus event_operations_snapshot, and open any event's
# detail page and read every sponsor's name, tier and PLEDGED AMOUNT. That is
# advancement/donor financial data on a page with no role check at all.
#
# Unlike 0048, these grants are NOT "the roles that already reach the surface" --
# today that is EVERYONE, which is the defect. This deliberately NARROWS the
# console to staff. Parents and students keep what they should have had all along:
# the public events feed (portal, via upcoming_public_events_for_school), the
# PUBLISHED event page, and ticket purchase, none of which are gated on these codes.
#
# Idempotent: get_or_create + additive .add() (never .set(), so existing role
# grants are preserved). Mirrors the 0048 pattern.

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "events.view",
        "School events console",
        "View the school-events console: all events including drafts, ticket "
        "tiers, sponsor commitments and the operations snapshot.",
    ),
    (
        "events.manage",
        "School events management",
        "Create and configure school events, ticket tiers and sponsor "
        "commitments.",
    ),
]

_VIEW = "events.view"
_MANAGE = "events.manage"

# role_code -> codes to ADD. Staff who run, staff, fund or account for school
# events. PARENT / STUDENT / EMPLOYER deliberately absent -- that is the fix.
ROLE_GRANTS = {
    # Runs the events programme.
    "COMMS_STAFF": [_VIEW, _MANAGE],
    "SECRETARY": [_VIEW, _MANAGE],
    "EXECUTIVE_ASSISTANT": [_VIEW, _MANAGE],
    # Leadership tier.
    "PRINCIPAL": [_VIEW, _MANAGE],
    "VICE_PRINCIPAL": [_VIEW, _MANAGE],
    "LEADERSHIP": [_VIEW, _MANAGE],
    "PROPRIETOR": [_VIEW, _MANAGE],
    "DEAN": [_VIEW],
    # Sponsor pledges and ticket revenue land in the ledger.
    "BURSAR": [_VIEW],
    "FINANCE_STAFF": [_VIEW],
    "ACCOUNTANT": [_VIEW],
    # Academic staff attend and steward events; read-only.
    "TEACHER": [_VIEW],
    "HOD": [_VIEW],
    "DEPT_LEAD": [_VIEW],
    "ACADEMICS_STAFF": [_VIEW],
    "IT_ADMIN": [_VIEW],
    # Administrators / super get every new code.
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "SUPERADMIN": [c for c, _, _ in NEW_PERMISSIONS],
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
        # There may be BOTH a global template row (school__isnull=True) and
        # per-school catalog rows for a role code; grant to all of them.
        for role in AccessRole.objects.filter(code=role_code):
            for c in codes:
                perm = perm_map.get(c)
                if perm is not None:
                    role.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0062_rls_feature_permission_scope"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
