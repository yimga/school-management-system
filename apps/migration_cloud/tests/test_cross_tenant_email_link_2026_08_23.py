"""Import must not bind a FOREIGN tenant's User by a bare email match.

``accounts.User`` and ``schools.SchoolMembership`` are SHARED_APPS living in the
public schema, so ``User.objects.filter(email__iexact=...)`` inside a lander
reaches EVERY tenant's users. Both people resolvers took the first such match
unconditionally:

  * ``guardian_lander._resolve_or_provision_user`` (guardians.csv), which then
    hands the matched account a ``SchoolMembership`` in the IMPORTING school via
    ``guardian_directory.ensure_school_membership``;
  * ``_helpers.resolve_or_provision_user`` (staff.csv).

So School A's admin uploading a row whose ``email`` is School B's headteacher
bound School B's account to a School A record and put it in School A's parent /
staff directory. The phone rung next door was already school-scoped
(``_match_guardian_user_by_phone``, "Scoped to the bundle's school so it never
reaches across tenants") — the email rung was not.

The email rung is now linkable-only: the match must already belong to this
school, or to no school at all. A match that belongs ONLY to another school
quarantines the row (``invalid_ref``) for a human instead of linking. Genuine
inter-school transfers still land through the ``guardian_user_ref`` /
``username_hint`` rung, which carries the platform identity deliberately.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.guardian_lander import GuardianLander
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.migration_cloud.tests.test_landers_fk_resolution import _GraphFixtureMixin
from apps.people.models import StudentGuardian, TeacherProfile
from apps.schools.models import School, SchoolMembership

User = get_user_model()

FOREIGN_EMAIL = "head@schoolb.example"


class _TwoTenantBase(_GraphFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self._build_school("xta")
        self.school_a = self.fx["school"]
        self.school_b = School.objects.create(
            name="Cross Tenant B", slug="cross-tenant-b", subdomain="cross-tenant-b"
        )
        self.head_b = User.objects.create_user(
            username="head_b", email=FOREIGN_EMAIL, password="pass123",
            first_name="Head", last_name="Bee",
        )
        SchoolMembership.objects.create(
            user=self.head_b, school=self.school_b, role="ADMIN", is_primary=True
        )

    def _memberships_in_a(self, user):
        return SchoolMembership.objects.filter(user=user, school=self.school_a)


class GuardianEmailCrossTenantTests(_TwoTenantBase):
    def _land(self, *rows):
        return GuardianLander().land(
            canonical_rows=iter(rows), ctx=self._ctx(self.school_a)
        )

    def _row(self, **over):
        row = {
            "student_external_id": "ADM-xta-1",
            "first_name": "Ama",
            "last_name": "Mensah",
            "relationship": "MOTHER",
        }
        row.update(over)
        return row

    def test_control_row_with_a_fresh_email_still_lands(self):
        # Vacuity guard for the test below: proves the fixture, the ctx and the
        # student lookup all work, so a quarantine there is the SCOPE gate and
        # not a broken harness.
        result = self._land(self._row(email="fresh.parent@example.com"))
        self.assertEqual(result.errors, [])
        self.assertEqual(result.created, 1)
        link = StudentGuardian.objects.get(student=self.fx["student"])
        self.assertEqual(
            link.guardian_user.email.lower(), "fresh.parent@example.com"
        )

    def test_foreign_school_email_is_not_linked_and_grants_no_membership(self):
        result = self._land(self._row(email=FOREIGN_EMAIL))

        # 1. The foreign account was never attached to a School A guardian row.
        self.assertFalse(
            StudentGuardian.objects.filter(guardian_user=self.head_b).exists(),
            "School B's head was bound to a School A StudentGuardian row",
        )
        # 2. ...and was never given a membership in the importing school.
        self.assertFalse(
            self._memberships_in_a(self.head_b).exists(),
            "School B's head was granted a SchoolMembership in School A",
        )
        # 3. The row was HELD (not silently dropped, not silently landed under a
        #    freshly provisioned twin), so a human sees it.
        self.assertEqual(result.quarantined, 1, result.errors)
        self.assertEqual(result.created, 0)
        self.assertIn(
            "another school", " ".join(result.errors).lower(), result.errors
        )
        # 4. No lookalike account was minted behind the operator's back either.
        self.assertEqual(
            User.objects.filter(email__iexact=FOREIGN_EMAIL).count(), 1
        )

    def test_email_match_inside_the_importing_school_still_links(self):
        # The gate must not break the normal case: an account that already
        # belongs to THIS school resolves by email exactly as before.
        local = User.objects.create_user(
            username="local_parent", email="local@example.com", password="pass123"
        )
        SchoolMembership.objects.create(
            user=local, school=self.school_a, role="PARENT", is_primary=True
        )
        result = self._land(self._row(email="local@example.com"))
        self.assertEqual(result.errors, [])
        link = StudentGuardian.objects.get(student=self.fx["student"])
        self.assertEqual(link.guardian_user_id, local.pk)


class StaffEmailCrossTenantTests(_TwoTenantBase):
    def _land(self, *rows):
        return StaffLander().land(
            canonical_rows=iter(rows),
            ctx=LanderContext(
                school=self.school_a, schema_name="", bundle_id=None,
                artifact_id=None, dry_run=False,
            ),
        )

    def _row(self, **over):
        row = {
            "staff_external_id": "EMP-xt-1",
            "first_name": "Jane",
            "last_name": "Doe",
            "role": "Teacher",
        }
        row.update(over)
        return row

    def test_control_row_with_a_fresh_email_still_lands(self):
        result = self._land(self._row(email="fresh.staff@example.com"))
        self.assertEqual(result.errors, [])
        self.assertTrue(
            TeacherProfile.objects.filter(school=self.school_a).exclude(
                user=self.fx["teacher_user"]
            ).exists()
        )

    def test_foreign_school_email_is_not_linked_into_staff(self):
        result = self._land(self._row(email=FOREIGN_EMAIL))

        self.assertFalse(
            TeacherProfile.objects.filter(user=self.head_b).exists(),
            "School B's head was bound to a School A TeacherProfile",
        )
        self.assertFalse(
            self._memberships_in_a(self.head_b).exists(),
            "School B's head was granted a SchoolMembership in School A",
        )
        self.assertEqual(result.quarantined, 1, result.errors)
        self.assertIn(
            "another school", " ".join(result.errors).lower(), result.errors
        )
