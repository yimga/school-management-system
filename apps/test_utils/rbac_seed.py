"""Seed the RBAC catalog a test depends on, instead of inheriting it.

Migrations seed ``Permission`` and ``AccessRole``. A ``--keepdb`` database does
NOT reliably still have those rows: a ``TransactionTestCase`` anywhere in the run
truncates the tables it touched and the emptied catalog is then PERSISTED into
the next run. Measured 2026-09-04 on this repo's shared test database --
``accounts_permission`` held 0 rows and ``accounts_accessrole`` held 1, several
hundred migrations after both were seeded.

Two different failures come out of that, and the second is worse:

* a test asserting a role HOLDS a capability fails, which is loud and gets fixed;
* a test asserting a role does NOT hold one PASSES -- because nothing holds
  anything -- and goes on passing after the guard it describes is deleted.

So a test that makes a claim about capabilities seeds the rows it is claiming
about, and pairs every negative with a positive control on the same data.
"""

from __future__ import annotations


def grant(role_code: str, *permission_codes: str):
    """Ensure a global AccessRole exists holding exactly these permissions."""
    from apps.accounts.models import AccessRole, Permission

    role, _ = AccessRole.objects.get_or_create(
        code=role_code,
        school=None,
        defaults={"name": role_code.replace("_", " ").title(), "description": ""},
    )
    for code in permission_codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"name": code, "description": ""}
        )
        role.permissions.add(perm)
    return role


def seed_support_staff_catalog():
    """Re-apply accounts migration 0065's data step against the live registry.

    Calling the migration's own function keeps the test honest: it verifies what
    the migration actually seeds rather than a second list that could drift from
    it. The function is idempotent (get_or_create + add), so calling it on a
    database that still has the rows changes nothing.
    """
    import importlib

    from django.apps import apps as django_apps

    from apps.accounts.models import Permission

    module = importlib.import_module(
        "apps.accounts.migrations.0065_support_staff_roles"
    )
    # 0065 attaches a permission only ``if p in perm_map`` -- the same
    # skip-if-absent shape migration 0017 uses -- because several codes it
    # references (stock.*, attendance.view, reports.view, discipline.refer) are
    # seeded by EARLIER migrations. That is correct on a real database and
    # correct on a fresh one, and it silently under-grants on a database whose
    # catalog was truncated mid-run. Recreate those first so the seeder runs
    # against the catalog it was written for.
    for role in module.NEW_ROLE_DEFINITIONS.values():
        for code in role["permissions"]:
            Permission.objects.get_or_create(
                code=code, defaults={"name": code, "description": ""}
            )
    module.seed_support_staff_roles(django_apps, None)
    return module
