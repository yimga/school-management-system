# Second RBAC catalog repair (2026-08-21). Two more codes gated on but never
# seeded, both missed by the first pass because of HOW they are called:
#
#   discipline.refer     -> apps/academics/views_discipline_api.py::_teacher_may_refer
#   finance.view_invoice -> apps/dashboard/admin_context.py (finance inbox tile)
#
# Both use the defensive form
#
#     getattr(user, "has_feature_permission", lambda _: False)("some.code")
#
# where the method name is a STRING and so is never followed by "(". The 0058
# scanner keyed on `name(` and could not see it. The gate now reads that shape,
# the template filter shape, and the private `_has_feature_permission` wrapper.
#
# Effect of the gap, in both cases the same: the code branch was dead, so the
# capability collapsed to whatever hard-coded check sat beside it — `role ==
# "TEACHER"` for referrals, `is_superuser` for the finance inbox. A discipline
# master or a bursar could never be granted either, no matter what an owner
# ticked in the RBAC console.
#
# Additive throughout: get_or_create + .add(), and each grant is DERIVED from the
# role set that already holds the equivalent capability rather than hand-listed.

from django.db import migrations


NEW_PERMISSIONS = [
    (
        "discipline.refer",
        "Refer a discipline incident",
        "Raise a discipline referral for a student (distinct from resolving one).",
    ),
    (
        "finance.view_invoice",
        "Finance inbox",
        "See the finance inbox tile and its outstanding-invoice queue.",
    ),
]

# new code -> the code whose holders already imply it.
DERIVED_FROM = {
    # Referring is the lighter half of discipline: anyone who can MANAGE an
    # incident can certainly raise one.
    "discipline.refer": "discipline.manage",
    # The inbox is a read surface over invoices.
    "finance.view_invoice": "finance.view",
}

# `_teacher_may_refer` admits role == TEACHER directly, so the stored matrix
# should say so too — otherwise the RBAC console shows a teacher without a
# capability they demonstrably have.
EXTRA_ROLE_GRANTS = {
    "TEACHER": ["discipline.refer"],
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

    for new_code, source_code in DERIVED_FROM.items():
        new_perm = perm_map.get(new_code)
        source_perm = perm_map.get(source_code)
        if new_perm is None or source_perm is None:
            continue
        for role in AccessRole.objects.filter(permissions=source_perm).distinct():
            role.permissions.add(new_perm)

    for role_code, codes in EXTRA_ROLE_GRANTS.items():
        for role in AccessRole.objects.filter(code=role_code):
            for c in codes:
                perm = perm_map.get(c)
                if perm is not None:
                    role.permissions.add(perm)

    # The global SUPERADMIN role holds the entire catalog. The resolver already
    # grants this structurally (apps/accounts/superadmin.py); this keeps the
    # STORED grants agreeing, which is what the RBAC console and the profile
    # render. post_migrate does the same on every future deploy.
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


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0058_superadmin_full_permission_coverage"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
