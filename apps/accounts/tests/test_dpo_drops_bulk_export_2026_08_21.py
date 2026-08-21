"""The Data Protection Officer gives up bulk export.

Migration 0058 created the DPO role holding four compliance/medical codes and
``data.access``. The fourth was the one place in the RBAC repair series that
ADDED privilege rather than restoring intended access, and it does not survive
inspection:

* ``data.access`` is "Export student/staff data across portals" and gates the
  governed bulk-query surface. The case for granting it was subject-access
  requests, and an Article 15 request concerns ONE data subject -- bulk export
  is a different tool, not an oversized one.
* Article 38(6), applied by the CJEU in C-453/21, keeps the DPO out of any post
  where they would oversee their own processing. Auditing whether an export was
  lawful and performing the export are not the same seat.

0060 removes it, from the GLOBAL template row only and from the role only.

A note on how these tests are built, because it is not an accident. The
persisted local test database comes up with EMPTY seed tables: a
``TransactionTestCase`` anywhere in a session flushes every table, and the
migrations are never replayed afterwards because they are already recorded as
applied. A test that asserted against migration-seeded rows would then report a
defect that does not exist -- and a false red is worse than no test, because it
costs the next person a day. So the proof lives in classes that seed what they
need. The one class that does read the shipped catalog says so, and skips
loudly when the catalog is not there to read.
"""

from __future__ import annotations

import importlib
import uuid

from django.apps import apps as django_apps
from django.test import TestCase

from apps.accounts.models import AccessRole, Permission
from apps.schools.models import School

MIGRATION = importlib.import_module(
    "apps.accounts.migrations.0060_dpo_drops_bulk_data_export"
)

ROLE_CODE = "DPO"
EXPORT_CODE = "data.access"
#: The codes that ARE the Data Protection Officer's job and must survive.
KEPT_CODES = ("compliance.view", "compliance.manage", "athletics.medical.manage")
#: Exactly the grant list 0058 hands the DPO.
GRANTED_BY_0058 = (
    "compliance.view",
    "compliance.manage",
    "data.access",
    "athletics.medical.manage",
    "athletics.view",
)


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}".upper()


class TheEndStateAfterBothMigrationsTests(TestCase):
    """0058 then 0060: what the Data Protection Officer ends up holding."""

    def setUp(self):
        self.permissions = {
            code: Permission.objects.get_or_create(code=code, defaults={"name": code})[
                0
            ]
            for code in GRANTED_BY_0058
        }
        self.role, _ = AccessRole.objects.get_or_create(
            code=ROLE_CODE, school=None, defaults={"name": "Data Protection Officer"}
        )
        self.role.permissions.add(*self.permissions.values())

    def _held(self, role=None) -> set:
        return set((role or self.role).permissions.values_list("code", flat=True))

    def test_the_role_starts_from_the_grant_list_0058_gives_it(self):
        """Guard the guard: prove the premise before asserting on the result."""
        self.assertEqual(self._held(), set(GRANTED_BY_0058))

    def test_bulk_export_is_gone_afterwards(self):
        MIGRATION.forwards(django_apps, None)
        self.assertNotIn(EXPORT_CODE, self._held())

    def test_the_compliance_job_survives(self):
        MIGRATION.forwards(django_apps, None)
        for code in KEPT_CODES:
            self.assertIn(code, self._held(), f"DPO lost {code}")

    def test_exactly_one_code_is_removed(self):
        """Removing one grant must not quietly gut the role."""
        before = self._held()
        MIGRATION.forwards(django_apps, None)
        self.assertEqual(before - self._held(), {EXPORT_CODE})

    def test_the_code_itself_is_not_deleted_from_the_catalog(self):
        """This is a grant removal, not a catalog deletion."""
        other = AccessRole.objects.create(
            code=_unique("OTHER"), school=None, name="Some other role"
        )
        other.permissions.add(self.permissions[EXPORT_CODE])

        MIGRATION.forwards(django_apps, None)

        self.assertTrue(Permission.objects.filter(code=EXPORT_CODE).exists())
        self.assertIn(EXPORT_CODE, self._held(other), "another role lost its grant")


class TheMigrationItselfBehavesTests(TestCase):
    """Run the migration's own callables directly, on state this class creates."""

    def setUp(self):
        self.role, _ = AccessRole.objects.get_or_create(
            code=ROLE_CODE, school=None, defaults={"name": "Data Protection Officer"}
        )
        self.permission, _ = Permission.objects.get_or_create(
            code=EXPORT_CODE, defaults={"name": "Data exports"}
        )

    def _held(self, role=None) -> set:
        return set((role or self.role).permissions.values_list("code", flat=True))

    def test_forwards_removes_a_grant_that_is_present(self):
        self.role.permissions.add(self.permission)
        self.assertIn(EXPORT_CODE, self._held())

        MIGRATION.forwards(django_apps, None)

        self.assertNotIn(EXPORT_CODE, self._held())

    def test_forwards_is_idempotent(self):
        """Re-running on a role that never held it is a no-op, not an error."""
        self.role.permissions.remove(self.permission)
        MIGRATION.forwards(django_apps, None)
        MIGRATION.forwards(django_apps, None)
        self.assertNotIn(EXPORT_CODE, self._held())

    def test_backwards_restores_it(self):
        """Reversible: migrating down leaves 0058's state exactly."""
        self.role.permissions.add(self.permission)
        MIGRATION.forwards(django_apps, None)
        MIGRATION.backwards(django_apps, None)
        self.assertIn(EXPORT_CODE, self._held())

    def test_a_school_scoped_dpo_row_is_left_alone(self):
        """A tenant that deliberately widened its own role keeps what it chose.

        Narrowing a school-scoped row from a platform migration would be exactly
        the destructive behaviour this whole release exists to fix.
        """
        school = School.objects.create(
            name="Tenant Alpha",
            slug=_unique("ta").lower(),
            subdomain=_unique("ta").lower(),
            is_active=True,
        )
        local = AccessRole.objects.create(
            code=ROLE_CODE, school=school, name="Local DPO"
        )
        local.permissions.add(self.permission)
        self.role.permissions.add(self.permission)

        MIGRATION.forwards(django_apps, None)

        self.assertNotIn(EXPORT_CODE, self._held(), "the global row should be narrowed")
        self.assertIn(
            EXPORT_CODE, self._held(local), "a tenant's own row must be untouched"
        )

    def test_it_survives_a_catalog_with_no_dpo_row(self):
        """A fresh database applies 0060 before anything has created the role."""
        AccessRole.objects.filter(code=ROLE_CODE).delete()
        MIGRATION.forwards(django_apps, None)  # must not raise
        MIGRATION.backwards(django_apps, None)  # must not raise


class TheShippedCatalogAgreesTests(TestCase):
    """The same assertion, against rows the MIGRATIONS themselves created.

    Skipped when the database's seed tables have been flushed, because on that
    substrate the question is unanswerable rather than answered wrongly. Nothing
    is lost by the skip: the proof that matters lives in the two classes above,
    which seed what they need and therefore always run.
    """

    def setUp(self):
        if not Permission.objects.exists():
            self.skipTest(
                "permission catalog is empty on this database (flushed seed "
                "tables); the substrate-independent proof is in "
                "TheEndStateAfterBothMigrationsTests"
            )

    def test_the_global_dpo_role_does_not_hold_bulk_export(self):
        role = AccessRole.objects.filter(code=ROLE_CODE, school__isnull=True).first()
        self.assertIsNotNone(role, "0058 should have created the global DPO role")
        self.assertNotIn(
            EXPORT_CODE,
            set(role.permissions.values_list("code", flat=True)),
            "the DPO must not carry bulk student/staff export",
        )

    def test_it_still_holds_the_job_it_was_created_for(self):
        role = AccessRole.objects.filter(code=ROLE_CODE, school__isnull=True).first()
        self.assertIsNotNone(role)
        held = set(role.permissions.values_list("code", flat=True))
        for code in KEPT_CODES:
            self.assertIn(code, held, f"DPO lost {code}")
