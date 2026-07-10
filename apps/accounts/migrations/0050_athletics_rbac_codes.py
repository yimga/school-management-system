# Athletics RBAC (2026-07-09): seed the granular athletics.* Permission codes and the
# COACH AccessRole so every athletics operational surface gates on a code (additive gate)
# instead of a coarse admin-tier check. Grants reproduce the access MODULE_ACCESS_DEFAULTS
# ["athletics"] already implies AND let an owner grant a code to a custom role (a dedicated
# coach/games-master) who is not an ADMIN. Idempotent: get_or_create + additive .add()
# (never .set(), so existing role grants are preserved). Mirrors the 0048 pattern.

from django.db import migrations


NEW_PERMISSIONS = [
    ("athletics.view", "Athletics access", "View teams, fixtures, rosters, and results."),
    ("athletics.manage", "Athletics management", "Manage teams/fixtures/rosters, book venues, record results."),
    ("athletics.eligibility.override", "Athletics eligibility override", "Override a computed athlete ineligibility."),
    ("athletics.medical.manage", "Athletics medical clearance", "Record/revoke athlete fitness-to-play clearance (PII)."),
]

# role_code -> codes to ADD (additive). Reproduces MODULE_ACCESS_DEFAULTS["athletics"].
ROLE_GRANTS = {
    "COACH": ["athletics.view", "athletics.manage"],
    "HOD": ["athletics.view", "athletics.manage"],
    "DEAN": ["athletics.view", "athletics.manage"],
    "IT_ADMIN": ["athletics.view"],
    "VICE_PRINCIPAL": ["athletics.view", "athletics.manage", "athletics.eligibility.override"],
    "PRINCIPAL": ["athletics.view", "athletics.manage", "athletics.eligibility.override"],
    "LEADERSHIP": ["athletics.view", "athletics.manage", "athletics.eligibility.override"],
    "PROPRIETOR": ["athletics.view"],
    # Nurse/DPO own the fitness-to-play (medical) clearance surface.
    "DPO": ["athletics.view", "athletics.medical.manage"],
    # Administrators / super get every new code.
    "ADMIN": [c for c, _, _ in NEW_PERMISSIONS],
    "SUPERADMIN": [c for c, _, _ in NEW_PERMISSIONS],
}


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    AccessRole = apps.get_model("accounts", "AccessRole")

    # Ensure a global COACH AccessRole template row exists so grants below can attach.
    AccessRole.objects.get_or_create(
        code="COACH",
        school=None,
        defaults={"name": "Coach", "description": "Athletics coach / games master."},
    )

    perm_map = {p.code: p for p in Permission.objects.all()}
    for code, name, description in NEW_PERMISSIONS:
        if code not in perm_map:
            perm_map[code] = Permission.objects.create(
                code=code, name=name, description=description
            )

    for role_code, codes in ROLE_GRANTS.items():
        # There may be BOTH a global template row (school__isnull=True) and per-school
        # catalog rows for a role code; grant to all of them.
        for role in AccessRole.objects.filter(code=role_code):
            for c in codes:
                perm = perm_map.get(c)
                if perm is not None:
                    role.permissions.add(perm)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0049_analytics_manage_code"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
