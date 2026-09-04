"""Unmapped staff privileges are held, not silently granted (2026-08-31).

The audited requirement: "unmapped or ambiguous source privileges must default
to a strict Deny-All state and be quarantined for review, without halting the
rest of the pipeline."

``resolve_staff_role`` collapsed ANY unreadable label onto TEACHER, and the staff
lander provisioned the account on that answer. TEACHER is not an inert token --
``TeacherTokenIsNotInertTests`` below asks the live permission resolver and shows
the account comes out already holding a privileged code -- so a "Canteen Vendor"
row became a school-wide attendance / grade-audit reader, and
``is_staff_setup_role`` then let that person activate the account themselves.

There is no Deny-All member in ``User.Role`` (every token is a real role), so the
strict deny is expressed the only way this app can express it: the row is HELD
and nothing at all is provisioned for it.
"""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.accounts.models import AccessRole, Permission, User
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.migration_cloud.models import MigrationBundle
from apps.migration_cloud.staff_role_map import (
    ROLE_FORBIDDEN,
    ROLE_UNMAPPED,
    is_staff_setup_role,
    resolve_staff_role,
    unresolvable_staff_role,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School


class UnresolvableStaffRoleTests(SimpleTestCase):
    def test_unmapped_label_is_named_not_defaulted(self):
        self.assertEqual(unresolvable_staff_role("Canteen Vendor"), ROLE_UNMAPPED)
        self.assertEqual(unresolvable_staff_role("Mystery Title"), ROLE_UNMAPPED)

    def test_bus_driver_is_no_longer_unmappable(self):
        """This example moved OUT of the test above on 2026-09-04.

        It was the canonical unreadable title here, and that was the defect
        rather than the fixture: a school has drivers, so the right answer was
        never "hold the row", it was "the system has no word for this job".
        DRIVER now exists, so the label resolves -- and the test that used it as
        an example of unmappability had to say so instead of quietly losing a
        case.
        """
        self.assertIsNone(unresolvable_staff_role("Bus Driver"))
        self.assertEqual(resolve_staff_role("Bus Driver"), "DRIVER")

    def test_forbidden_label_is_named_forbidden(self):
        self.assertEqual(unresolvable_staff_role("SUPERADMIN"), ROLE_FORBIDDEN)
        self.assertEqual(unresolvable_staff_role("employer"), ROLE_FORBIDDEN)

    def test_blank_is_not_a_privilege_claim(self):
        # Guard against over-correcting. Most staff sheets are payroll exports
        # with no role column at all; blank means the source claimed nothing, so
        # the caller's own default decides and the row still imports.
        self.assertIsNone(unresolvable_staff_role(""))
        self.assertIsNone(unresolvable_staff_role(None))
        self.assertIsNone(unresolvable_staff_role("   "))

    def test_known_roles_and_aliases_are_resolvable(self):
        for label in ("Bursar", "Head of Department", "proviseur", "intendant"):
            self.assertIsNone(unresolvable_staff_role(label), label)


class ResolveStaffRoleContractUnchangedTests(SimpleTestCase):
    """Every existing caller of resolve_staff_role keeps its exact behaviour."""

    def test_default_collapse_is_preserved(self):
        self.assertEqual(resolve_staff_role("Mystery Title"), User.Role.TEACHER)
        self.assertEqual(resolve_staff_role(""), User.Role.TEACHER)
        self.assertEqual(resolve_staff_role("SUPERADMIN"), User.Role.TEACHER)
        self.assertEqual(resolve_staff_role("parent"), User.Role.TEACHER)

    def test_explicit_default_still_wins_for_an_unreadable_label(self):
        self.assertEqual(
            resolve_staff_role("Mystery Title", default=User.Role.SECRETARY),
            User.Role.SECRETARY,
        )
        self.assertEqual(
            resolve_staff_role("", default=User.Role.SECRETARY), User.Role.SECRETARY
        )

    def test_a_readable_label_still_beats_the_default(self):
        self.assertEqual(
            resolve_staff_role("Bursar", default=User.Role.SECRETARY), User.Role.BURSAR
        )

    def test_is_staff_setup_role_unchanged(self):
        self.assertTrue(is_staff_setup_role(User.Role.BURSAR))
        self.assertTrue(is_staff_setup_role(User.Role.TEACHER))
        self.assertFalse(is_staff_setup_role(User.Role.PARENT))
        self.assertFalse(is_staff_setup_role(User.Role.SUPERADMIN))
        self.assertFalse(is_staff_setup_role("Canteen Vendor"))


class TeacherTokenIsNotInertTests(TestCase):
    """The severity evidence: the TEACHER token self-grants, with no other act.

    This seeds the two catalog rows itself rather than trusting the shared
    ``--keepdb`` database. That database's RBAC catalog is empty (measured
    2026-08-31: 1 AccessRole, 2 Permissions), so a test asserting against the
    migration seeds reports a comfortable zero for entirely the wrong reason --
    it would look like proof that TEACHER is inert.

    What is proven here is the MECHANISM: writing ``role=TEACHER`` attaches the
    global TEACHER ``AccessRole`` through the ``post_save`` in
    ``apps.accounts.signals`` (``ROLE_TEMPLATES`` and the ``roles.add`` below
    it), so the account silently holds every code that role carries and nobody
    granted anything. On a seeded tenant those codes include
    ``attendance.manage`` / ``reports.manage`` / ``portal.manage`` (accounts
    migration ``0030_resync_accessrole_permissions``) and ``grades.enter`` /
    ``analytics.view`` (``0048_rbac_completion_codes``).
    """

    def _seed(self, role_code, permission_code):
        perm, _ = Permission.objects.get_or_create(
            code=permission_code, defaults={"name": permission_code}
        )
        role, _ = AccessRole.objects.get_or_create(
            code=role_code, school=None, defaults={"name": role_code}
        )
        role.permissions.add(perm)
        return role

    def _staffer(self, username, role):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.cm",
            role=role,
        )
        user.set_unusable_password()
        user.save()
        return user

    def test_role_teacher_alone_confers_that_roles_codes(self):
        self._seed("TEACHER", "grades.enter")

        user = self._staffer("unmapped.staffer", User.Role.TEACHER)

        self.assertEqual(
            list(user.roles.values_list("code", flat=True)),
            ["TEACHER"],
            "the role token attached an RBAC role with no other action",
        )
        self.assertTrue(
            user.has_feature_permission("grades.enter"),
            "role=TEACHER is a privilege grant, not a label -- so collapsing "
            "an unreadable source privilege onto it inflates privilege",
        )

    def test_the_grant_is_specific_to_the_token_that_was_written(self):
        # Control: the code rides on TEACHER specifically. Had the unreadable
        # row been held, or landed on a role that does not carry the code,
        # nothing would have been conferred.
        self._seed("TEACHER", "grades.enter")
        self._seed("SECRETARY", "reception.manage")

        other = self._staffer("some.secretary", User.Role.SECRETARY)

        self.assertFalse(other.has_feature_permission("grades.enter"))
        self.assertTrue(other.has_feature_permission("reception.manage"))


class StaffLanderRefusesThePrivilegeNotThePersonTests(TestCase):
    """Two different answers for two different problems (changed 2026-09-04).

    An UNMAPPED label names a job this system has no word for. Holding it kept
    the privilege out and the person out with it -- a real 49-row directory lost
    its coordinator, its driver and its security officer entirely. Those rows now
    LAND on SUPPORT_STAFF, which grants nothing, and carry a note.

    A FORBIDDEN label is a different kind of claim: the cell said SUPERADMIN, or
    PARENT, or STUDENT. That is still held, and the test at the bottom of this
    class is unchanged.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Deny All School",
            slug="deny-all-school",
            subdomain="deny-all-school",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school,
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
            schema_name="",
        )

    def _land(self, *rows):
        return StaffLander().land(
            canonical_rows=iter([dict(r) for r in rows]), ctx=self.ctx
        )

    def test_unmapped_role_row_lands_holding_nothing(self):
        res = self._land(
            {
                "staff_external_id": "EMP-X1",
                "full_name": "NDIFOR SAMUEL",
                "role": "Canteen Vendor",
            }
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        self.assertEqual(res.created, 1)
        profile = TeacherProfile.objects.get(school=self.school, staff_id="EMP-X1")
        # The person exists. The privilege does not: SUPPORT_STAFF is the base
        # identity, and the two codes below are what the TEACHER default used to
        # hand out for exactly this row.
        self.assertEqual(profile.user.role, User.Role.SUPPORT_STAFF)
        self.assertFalse(profile.user.has_feature_permission("attendance.manage"))
        self.assertFalse(profile.user.has_feature_permission("grades.enter"))

    def test_the_unreadable_title_is_reported_as_a_note_not_a_rejection(self):
        res = self._land(
            {
                "staff_external_id": "EMP-X2",
                "full_name": "TABI GRACE",
                "role": "Chief Vibes Officer",
            }
        )
        # Not an error row: nothing was rejected, so nothing belongs in the queue
        # of rows somebody must reconcile before the import is usable.
        self.assertEqual(len(res.error_rows), 0, res.errors)
        notes = [n["note"] for n in res.notes]
        self.assertTrue(
            any("Chief Vibes Officer" in n for n in notes),
            "the source title must survive so a person can correct it: %r" % notes,
        )
        self.assertTrue(
            any("SUPPORT_STAFF" in n for n in notes),
            "the note must say what the person was given instead: %r" % notes,
        )

    def test_one_unreadable_row_does_not_halt_the_import(self):
        """Unchanged in intent; the unreadable row is now imported, not held."""
        res = self._land(
            {
                "staff_external_id": "EMP-X3",
                "full_name": "ASHU PETER",
                "role": "Wizard",
            },
            {
                "staff_external_id": "EMP-B9",
                "full_name": "NGONO PAULINE",
                "role": "Bursar",
            },
            {
                "staff_external_id": "EMP-T9",
                "full_name": "MBUA REGINA",
                "role": "Teacher",
            },
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        self.assertEqual(res.created, 3)
        bursar = TeacherProfile.objects.get(school=self.school, staff_id="EMP-B9")
        self.assertEqual(bursar.user.role, User.Role.BURSAR)
        wizard = TeacherProfile.objects.get(school=self.school, staff_id="EMP-X3")
        self.assertEqual(wizard.user.role, User.Role.SUPPORT_STAFF)

    def test_blank_role_lands_on_a_default_that_grants_nothing(self):
        res = self._land(
            {"staff_external_id": "EMP-N1", "full_name": "EBOT JOSEPH"}
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        profile = TeacherProfile.objects.get(school=self.school, staff_id="EMP-N1")
        # Was TEACHER until 2026-09-04, which meant a payroll export with no
        # role column minted a school-wide attendance and grade reader per row.
        self.assertEqual(profile.user.role, User.Role.SUPPORT_STAFF)
        self.assertFalse(profile.user.has_feature_permission("attendance.manage"))

    def test_superadmin_claim_is_held_not_silently_downgraded(self):
        res = self._land(
            {
                "staff_external_id": "EMP-S1",
                "full_name": "ATEM BRIGHT",
                "role": "SUPERADMIN",
            }
        )
        self.assertEqual(res.quarantined, 1, res.errors)
        self.assertFalse(
            TeacherProfile.objects.filter(
                school=self.school, staff_id="EMP-S1"
            ).exists()
        )


class StaffRoleDispositionSummaryTests(TestCase):
    """The blank-cell default still flows -- but it is no longer silent.

    Holding a role-less payroll export would be worse than the disease, so the
    behaviour is unchanged. The gap this closes is that a defaulted row and a
    row whose label was actually read looked identical from the outside: someone
    importing 400 role-less rows had no way to know they had just created 400
    teachers.
    """

    def setUp(self):
        self.school = School.objects.create(
            name="Tally School",
            slug="tally-school",
            subdomain="tally-school",
            is_active=True,
            country_code="CM",
        )
        self.bundle = MigrationBundle.objects.create(school=self.school)
        self.ctx = LanderContext(
            school=self.school,
            bundle_id=self.bundle.pk,
            artifact_id=1,
            dry_run=False,
            schema_name="",
        )

    def _land(self, *rows):
        return StaffLander().land(
            canonical_rows=iter([dict(r) for r in rows]), ctx=self.ctx
        )

    def _disposition(self):
        self.bundle.refresh_from_db()
        summary = self.bundle.mapping_summary or {}
        found = summary.get("staff_role_disposition")
        self.assertIsNotNone(
            found, "the lander must publish its role tally onto the bundle"
        )
        return found

    def test_role_less_sheet_reports_what_it_defaulted(self):
        self._land(
            {"staff_external_id": "EMP-D1", "full_name": "EBOT JOSEPH"},
            {"staff_external_id": "EMP-D2", "full_name": "NKEM ALICE"},
        )
        found = self._disposition()
        self.assertEqual(found["role_defaulted_blank"], 2)
        self.assertEqual(found["role_mapped"], 0)
        self.assertEqual(
            found["default_token"],
            User.Role.SUPPORT_STAFF,
            "the reader must be told WHAT they got two of",
        )

    def test_a_sheet_that_states_its_roles_defaults_nothing(self):
        self._land(
            {
                "staff_external_id": "EMP-R1",
                "full_name": "NGONO PAULINE",
                "role": "Bursar",
            },
            {
                "staff_external_id": "EMP-R2",
                "full_name": "MBUA REGINA",
                "role": "Teacher",
            },
        )
        found = self._disposition()
        self.assertEqual(found["role_defaulted_blank"], 0)
        self.assertEqual(found["role_mapped"], 2)

    def test_the_tally_closes_over_every_disposition(self):
        # One row down each exit: read, defaulted, based-unmapped (imported on
        # SUPPORT_STAFF), held-forbidden, skipped-as-non-staff, and rejected
        # before the role cell was ever reached.
        self._land(
            {"staff_external_id": "EMP-C1", "full_name": "A ONE", "role": "Bursar"},
            {"staff_external_id": "EMP-C2", "full_name": "B TWO"},
            {"staff_external_id": "EMP-C3", "full_name": "C THREE", "role": "Wizard"},
            {
                "staff_external_id": "EMP-C4",
                "full_name": "D FOUR",
                "role": "SUPERADMIN",
            },
            {"staff_external_id": "EMP-C5", "full_name": "E FIVE", "role": "parent"},
            {"role": "Teacher"},
        )
        found = self._disposition()
        buckets = {
            "role_mapped": 1,
            "role_defaulted_blank": 1,
            "role_based_unmapped": 1,
            "role_held_forbidden": 1,
            "role_skipped_non_staff": 1,
            "role_not_evaluated": 1,
        }
        for name, expected in buckets.items():
            self.assertEqual(found[name], expected, name)
        self.assertEqual(found["rows_total"], 6)
        self.assertEqual(
            sum(found[name] for name in buckets),
            found["rows_total"],
            "a partial tally is worse than none -- the buckets must add up",
        )
        self.assertTrue(found["balanced"])
        self.assertNotIn("unaccounted", found)
