"""Bulk staff-role assignment grants what was asked and nothing else.

This endpoint exists because the import now lands people it cannot classify on
SUPPORT_STAFF instead of refusing them, so a directory arrives complete and some
of it needs correcting in place. It also takes a role name from a request body
and writes it onto an account, which makes it a privilege-escalation primitive if
it trusts that string -- so most of what is tested here is what it REFUSES.

The tenant bound is tested too, and is not incidental: the ids arrive as numbers
in a JSON body, so without the school filter this endpoint edits any school's
staff by guessing integers.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.people.bulk_staff_actions import (
    ALLOWED_STAFF_ROLES,
    FORBIDDEN_ROLES,
    bulk_set_staff_role,
    parse_staff_id_list,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School
from apps.test_utils.rbac_seed import seed_support_staff_catalog


class ParseStaffIdListTests(TestCase):
    def test_junk_is_dropped_not_raised(self):
        self.assertEqual(parse_staff_id_list(["1", 2, "x", None, "", "-3"]), [1, 2])

    def test_not_a_list_is_empty(self):
        self.assertEqual(parse_staff_id_list("1,2,3"), [])
        self.assertEqual(parse_staff_id_list(None), [])

    def test_capped(self):
        self.assertEqual(len(parse_staff_id_list(list(range(1, 500)))), 200)


class BulkSetStaffRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # The capability assertion below is only meaningful if the catalog is
        # present; a --keepdb database may have had it truncated.
        seed_support_staff_catalog()
        cls.school = School.objects.create(
            name="Bulk Role School",
            slug="bulk-role-school",
            subdomain="bulk-role-school",
            is_active=True,
            country_code="CM",
        )
        cls.other = School.objects.create(
            name="Other School",
            slug="other-bulk-school",
            subdomain="other-bulk-school",
            is_active=True,
            country_code="CM",
        )

    def _staff(self, username, school=None, role=User.Role.SUPPORT_STAFF):
        user = User.objects.create_user(username=username, password="x", role=role)
        return TeacherProfile.objects.create(
            user=user, school=school or self.school, staff_id=username.upper()
        )

    # ---------------------------------------------------------------- happy path
    def test_it_assigns_the_role(self):
        p = self._staff("bulk.one")
        out = bulk_set_staff_role(
            staff_ids=[p.pk], role="DRIVER", school=self.school
        )
        self.assertTrue(out["ok"])
        self.assertEqual(out["succeeded"], 1)
        p.user.refresh_from_db()
        self.assertEqual(p.user.role, User.Role.DRIVER)

    def test_the_capabilities_follow_the_assignment(self):
        """A role written without the AccessRole is a label, not a grant."""
        p = self._staff("bulk.libr")
        bulk_set_staff_role(staff_ids=[p.pk], role="LIBRARIAN", school=self.school)
        p.user.refresh_from_db()
        self.assertIn("LIBRARIAN", set(p.user.roles.values_list("code", flat=True)))
        self.assertTrue(p.user.has_feature_permission("library.manage"))

    def test_already_set_is_reported_not_rewritten(self):
        p = self._staff("bulk.same", role=User.Role.DRIVER)
        out = bulk_set_staff_role(staff_ids=[p.pk], role="DRIVER", school=self.school)
        self.assertTrue(out["ok"])
        self.assertEqual(out["results"][0]["message"], "Already set.")

    # ------------------------------------------------------------------ refusals
    def test_the_four_forbidden_roles_are_refused(self):
        p = self._staff("bulk.esc")
        for role in ("SUPERADMIN", "PARENT", "STUDENT", "EMPLOYER"):
            with self.subTest(role=role):
                with self.assertRaises(ValueError):
                    bulk_set_staff_role(
                        staff_ids=[p.pk], role=role, school=self.school
                    )
                p.user.refresh_from_db()
                self.assertEqual(p.user.role, User.Role.SUPPORT_STAFF)

    def test_forbidden_set_matches_what_is_grantable(self):
        self.assertTrue(FORBIDDEN_ROLES)
        self.assertFalse(FORBIDDEN_ROLES & ALLOWED_STAFF_ROLES)
        self.assertIn(User.Role.SUPPORT_STAFF, ALLOWED_STAFF_ROLES)
        self.assertIn(User.Role.DRIVER, ALLOWED_STAFF_ROLES)

    def test_an_unknown_role_is_refused(self):
        p = self._staff("bulk.unknown")
        with self.assertRaises(ValueError):
            bulk_set_staff_role(staff_ids=[p.pk], role="WIZARD", school=self.school)

    def test_a_superadmin_cannot_be_demoted_from_a_staff_list(self):
        p = self._staff("bulk.god", role=User.Role.SUPERADMIN)
        out = bulk_set_staff_role(
            staff_ids=[p.pk], role="SUPPORT_STAFF", school=self.school
        )
        self.assertFalse(out["ok"])
        p.user.refresh_from_db()
        self.assertEqual(p.user.role, User.Role.SUPERADMIN)

    def test_no_school_is_refused(self):
        p = self._staff("bulk.noschool")
        with self.assertRaises(ValueError):
            bulk_set_staff_role(staff_ids=[p.pk], role="DRIVER", school=None)

    def test_empty_selection_is_refused(self):
        with self.assertRaises(ValueError):
            bulk_set_staff_role(staff_ids=[], role="DRIVER", school=self.school)

    # -------------------------------------------------------------- tenant bound
    def test_another_schools_staff_is_not_touched(self):
        mine = self._staff("bulk.mine")
        theirs = self._staff("bulk.theirs", school=self.other)
        out = bulk_set_staff_role(
            staff_ids=[mine.pk, theirs.pk], role="DRIVER", school=self.school
        )
        mine.user.refresh_from_db()
        theirs.user.refresh_from_db()
        self.assertEqual(mine.user.role, User.Role.DRIVER)
        self.assertEqual(
            theirs.user.role,
            User.Role.SUPPORT_STAFF,
            "an id from another school must not be editable by number",
        )
        self.assertEqual(out["failed"], 1)

    def test_a_missing_id_is_reported_not_silently_dropped(self):
        out = bulk_set_staff_role(
            staff_ids=[9_000_001], role="DRIVER", school=self.school
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["processed"], 1)
        self.assertEqual(out["failed"], 1)

    def test_the_tally_closes(self):
        ok = self._staff("bulk.tally1")
        foreign = self._staff("bulk.tally2", school=self.other)
        out = bulk_set_staff_role(
            staff_ids=[ok.pk, foreign.pk, 9_000_002],
            role="DRIVER",
            school=self.school,
        )
        self.assertEqual(out["processed"], 3)
        self.assertEqual(out["succeeded"] + out["failed"], out["processed"])
