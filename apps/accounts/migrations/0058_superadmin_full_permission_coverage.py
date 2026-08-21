# RBAC coverage repair (2026-08-20). Three defects, one migration:
#
# 1. FOUR codes are gated on in live code but were never catalog rows, so NO role
#    could hold them and the surfaces behind them were unreachable for everyone
#    except a Django superuser:
#       finance.access, finance.view_dashboard, reports.view, marketplace.view
#            -> apps/platform_runtime/action_engine.py
#       grade.submit, attendance.mark
#            -> apps/api/mobile_api.py (offline sync)
#    The mobile pair is the worst of them. ``enforce_permission_token`` requires
#    BOTH halves to pass — RBAC first, then the ReBAC tuple. ``rebac_sync`` duly
#    writes a ``can`` tuple on ``permission:grade.submit`` for every teacher
#    assignment, but the RBAC half short-circuits to False on a code that is not
#    in the catalog, so it never reaches the ReBAC check. Every non-superadmin
#    teacher syncing offline marks or attendance from mobile got
#    ``rebac_permission_denied:grade.submit`` — the per-classroom ReBAC scoping
#    the tuples exist for was unreachable.
#    They are seeded here and granted by DERIVING from the matrix that already
#    exists (a role that holds finance.view gets the finance read codes, etc.)
#    rather than by hand-listing role codes that would drift again.
#
# 2. DPO and EMPLOYER are declared User.Role choices with no AccessRole row and
#    no ROLE_TEMPLATES entry, so those accounts carried an EMPTY roles M2M and
#    resolved every granular check to False. (Migration 0050 tried to grant DPO
#    the athletics medical codes; the grant was a no-op because the row it
#    filtered for did not exist.)
#
# 3. The global SUPERADMIN role held whatever the last migration remembered to
#    grant it. Every code in the catalog is granted here, and post_migrate keeps
#    it that way for codes added in the future — see apps/accounts/superadmin_sync.py.
#
# Additive throughout: get_or_create + .add(), never .set() or .remove(), so a
# deliberately widened role is never narrowed by this repair.

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "finance.access",
        "Finance surface access",
        "Reach the finance workbench and its operator action strip.",
    ),
    (
        "finance.view_dashboard",
        "Finance dashboard",
        "View the finance dashboard summary and its revenue widgets.",
    ),
    (
        "reports.view",
        "Reports access",
        "Open generated reports without the authority to publish or export them.",
    ),
    (
        "marketplace.view",
        "Marketplace access",
        "Browse the app marketplace and installed-app catalog.",
    ),
    (
        "grade.submit",
        "Submit marks (offline sync)",
        "Push evaluation and mark entries from the mobile offline queue.",
    ),
    (
        "attendance.mark",
        "Mark attendance (offline sync)",
        "Push attendance records from the mobile offline queue.",
    ),
]

# new code -> the code whose holders already imply it (derivation, not a guess list).
DERIVED_FROM = {
    "finance.access": "finance.view",
    "finance.view_dashboard": "finance.view",
    "reports.view": "reports.manage",
    "marketplace.view": "settings.manage",
    # The offline codes mirror their web equivalents exactly, so this grants the
    # same people who can already do the same thing in the browser — no widening.
    # Under ReBAC enforcement the per-classroom `can` tuple still has to agree.
    "grade.submit": "grades.enter",
    "attendance.mark": "attendance.manage",
}

# Roles that exist as User.Role choices but had no AccessRole row.
NEW_ROLES = [
    (
        "DPO",
        "Data Protection Officer",
        "Owns data-protection posture, compliance evidence and medical-clearance PII.",
        ["compliance.view", "compliance.manage", "data.access", "athletics.medical.manage", "athletics.view"],
    ),
    (
        "EMPLOYER",
        "Employer (apprentice portal)",
        (
            "External apprenticeship employer. Deliberately holds NO capability code — "
            "an employer's reach is decided by the apprentice-portal object rules that "
            "bind them to their own apprentices, not by a platform-wide permission."
        ),
        [],
    ),
]


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")
    User = apps.get_model("accounts", "User")

    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm_map[code] = Permission.objects.create(
                code=code, name=name, description=description
            )

    # (1) Derive the grants for the newly seeded codes from the live matrix.
    for new_code, source_code in DERIVED_FROM.items():
        new_perm = perm_map.get(new_code)
        source_perm = perm_map.get(source_code)
        if new_perm is None or source_perm is None:
            continue
        for role in AccessRole.objects.filter(permissions=source_perm).distinct():
            role.permissions.add(new_perm)

    # (2) Seed the access roles that had no row at all.
    for code, name, description, codes in NEW_ROLES:
        role, _created = AccessRole.objects.get_or_create(
            code=code,
            school=None,
            defaults={"name": name, "description": description},
        )
        for c in codes:
            perm = perm_map.get(c)
            if perm is not None:
                role.permissions.add(perm)

    # (3) The global SUPERADMIN role holds the ENTIRE catalog.
    superadmin, _created = AccessRole.objects.get_or_create(
        code="SUPERADMIN",
        school=None,
        defaults={
            "name": "Super Administrator",
            "description": (
                "Platform top role — holds every permission in the catalog, "
                "including codes added in the future."
            ),
        },
    )
    superadmin.permissions.add(*Permission.objects.all())

    # (4) Repair accounts the old ROLE_TEMPLATES mapping materialised wrongly.
    #     role=SUPERADMIN used to attach the ADMIN access role; add the role they
    #     actually own. ADMIN is left in place — removing a held role here would
    #     be exactly the destructive behaviour this release is fixing.
    role_rows = {
        code: AccessRole.objects.filter(code=code, school__isnull=True).first()
        for code in ("SUPERADMIN", "DPO", "EMPLOYER")
    }
    for user_role, row in role_rows.items():
        if row is None:
            continue
        for user in User.objects.filter(role=user_role).exclude(roles=row):
            user.roles.add(row)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0057_identity_reset_credentials_permission"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
