"""The Owner Console roster showed nobody's roles, ever.

``_roster_rows`` filtered each member's access roles with

    getattr(r, "school_id", None) == school.pk

which keeps only SCHOOL-SCOPED catalog rows and drops every GLOBAL template row.
Global is what the platform actually ships — TEACHER, ADMIN, BURSAR, IT_ADMIN,
SUPERADMIN and the rest are all ``school=NULL``; on the live database there were
25 global rows and **zero** school-scoped ones, so the predicate matched nothing
at all.

The page is titled "People & Roles" and its whole job is assigning them: an owner
would tick people, tick roles, press Apply, get "roles applied" — and see an
empty chip list for every person. The canonical predicate,
``access_roles.role_applies_to_school``, admits a global row for any school and a
scoped row only for its own.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import AccessRole, User
from apps.accounts.views_owner_console_people import _roster_rows
from apps.schools.models import School, SchoolMembership


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class RosterShowsAssignedRolesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name=_unique("Sch"),
            slug=_unique("s"),
            subdomain=_unique("sd"),
            is_active=True,
        )
        self.other_school = School.objects.create(
            name=_unique("Other"),
            slug=_unique("o"),
            subdomain=_unique("od"),
            is_active=True,
        )
        self.global_role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", school=None, defaults={"name": "IT Administrator"}
        )
        self.local_role = AccessRole.objects.create(
            code=_unique("LOCAL").upper(), school=self.school, name="Local Only"
        )
        self.foreign_role = AccessRole.objects.create(
            code=_unique("FOREIGN").upper(),
            school=self.other_school,
            name="Someone Else's",
        )
        self.member = User.objects.create_user(
            username=_unique("m"), password="Test1234", role=User.Role.TEACHER
        )
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role=User.Role.TEACHER, is_primary=True
        )

    def _roles_shown(self) -> list[str]:
        rows = [r for r in _roster_rows(self.school)]
        self.assertTrue(rows, "the roster returned no rows at all")
        return rows[0]["access_roles"]

    def test_a_globally_assigned_role_is_shown(self):
        """The bug: every shipped role is global, so the roster showed nothing."""
        self.member.roles.add(self.global_role)
        self.assertIn("IT Administrator", self._roles_shown())

    def test_a_school_scoped_role_is_shown(self):
        self.member.roles.add(self.local_role)
        self.assertIn("Local Only", self._roles_shown())

    def test_another_schools_role_is_not_shown(self):
        """Scoping still has to bite in the direction that matters."""
        self.member.roles.add(self.foreign_role)
        self.assertNotIn("Someone Else's", self._roles_shown())

    def test_a_member_with_no_access_roles_shows_none(self):
        self.assertEqual(self._roles_shown(), [])

    def test_the_canonical_predicate_is_used(self):
        """A hand-rolled scope check is what got this wrong the first time."""
        from pathlib import Path

        src = Path("apps/accounts/views_owner_console_people.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("role_applies_to_school(r, school)", src)
        self.assertNotIn('getattr(r, "school_id", None) == school.pk', src)
