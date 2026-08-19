"""Workbook staff roles land on User + SchoolMembership (2026-08-18)."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.migration_cloud.people_activation import _unactivated_staff
from apps.migration_cloud.staff_role_map import (
    is_staff_setup_role,
    resolve_staff_role,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership


class StaffRoleMapTests(SimpleTestCase):
    def test_bursar_and_hod_aliases(self):
        self.assertEqual(resolve_staff_role("Bursar"), User.Role.BURSAR)
        self.assertEqual(resolve_staff_role("Head of Department"), User.Role.HOD)
        self.assertEqual(resolve_staff_role("proviseur"), User.Role.PRINCIPAL)
        self.assertEqual(resolve_staff_role("intendant"), User.Role.BURSAR)

    def test_superadmin_never_granted_from_workbook(self):
        self.assertEqual(resolve_staff_role("SUPERADMIN"), User.Role.TEACHER)
        self.assertEqual(resolve_staff_role("parent"), User.Role.TEACHER)
        self.assertFalse(is_staff_setup_role(User.Role.PARENT))
        self.assertFalse(is_staff_setup_role(User.Role.SUPERADMIN))
        self.assertTrue(is_staff_setup_role(User.Role.BURSAR))
        self.assertTrue(is_staff_setup_role(User.Role.TEACHER))

    def test_blank_falls_back_to_teacher(self):
        self.assertEqual(resolve_staff_role(""), User.Role.TEACHER)
        self.assertEqual(resolve_staff_role("Mystery Title"), User.Role.TEACHER)


class StaffLanderRoleAssignmentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Role Map School",
            slug="role-map-school",
            subdomain="role-map-school",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _land(self, row):
        return StaffLander().land(canonical_rows=iter([dict(row)]), ctx=self.ctx)

    def test_bursar_row_gets_bursar_role_and_membership(self):
        res = self._land(
            {
                "staff_external_id": "EMP-B1",
                "full_name": "NGONO PAULINE",
                "role": "Bursar",
            }
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        profile = TeacherProfile.objects.get(school=self.school, staff_id="EMP-B1")
        self.assertEqual(profile.user.role, User.Role.BURSAR)
        self.assertFalse(profile.user.has_usable_password())
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=self.school, user=profile.user, role=User.Role.BURSAR
            ).exists()
        )
        waiting = _unactivated_staff(self.school)
        self.assertEqual([u.pk for u in waiting], [profile.user_id])

    def test_reapply_same_staff_id_is_delta_not_duplicate(self):
        row = {
            "staff_external_id": "EMP-T1",
            "full_name": "MBUA REGINA NAMONDO",
            "role": "Teacher",
        }
        first = self._land(row)
        second = self._land(row)
        self.assertEqual(first.created, 1)
        self.assertEqual(second.created, 0)
        self.assertEqual(
            TeacherProfile.objects.filter(school=self.school, staff_id="EMP-T1").count(),
            1,
        )

    def test_residual_fonction_column_assigns_bursar(self):
        res = self._land(
            {
                "staff_external_id": "EMP-B2",
                "full_name": "ESAKENONG ABEL",
                "_unmapped.Fonction": "Bursar",
                "custom_fields.badge_color": "navy",
            }
        )
        self.assertEqual(res.quarantined, 0, res.errors)
        profile = TeacherProfile.objects.get(school=self.school, staff_id="EMP-B2")
        self.assertEqual(profile.user.role, User.Role.BURSAR)
        self.assertEqual(profile.position_title, "Bursar")
        self.assertEqual((profile.custom_attributes or {}).get("badge_color"), "navy")


class PromoteImportedStaffRolesTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Backfill School",
            slug="backfill-school",
            subdomain="backfill-school",
            is_active=True,
            country_code="CM",
        )

    def _teacher(self, *, username, title="", live=False):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.cm",
            first_name="Pat",
            last_name="Staff",
            role=User.Role.TEACHER,
        )
        if live:
            user.set_password("ChangeMe_1234")
        else:
            user.set_unusable_password()
        user.save()
        profile = TeacherProfile.objects.create(
            school=self.school, user=user, staff_id=username.upper(), position_title=title
        )
        return user, profile

    def test_position_title_bursar_promotes_without_reapply(self):
        from apps.migration_cloud.staff_role_map import promote_imported_staff_roles

        user, _profile = self._teacher(username="old.bursar", title="Bursar")
        out = promote_imported_staff_roles(school=self.school)
        user.refresh_from_db()
        self.assertEqual(out["updated"], 1)
        self.assertEqual(user.role, User.Role.BURSAR)
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=self.school, user=user, role=User.Role.BURSAR
            ).exists()
        )

    def test_live_account_keeps_teacher(self):
        from apps.migration_cloud.staff_role_map import promote_imported_staff_roles

        user, _profile = self._teacher(username="live.bursar", title="Bursar", live=True)
        out = promote_imported_staff_roles(school=self.school)
        user.refresh_from_db()
        self.assertEqual(out["updated"], 0)
        self.assertEqual(out["skipped_live"], 1)
        self.assertEqual(user.role, User.Role.TEACHER)

    def test_source_role_dfv_promotes_hod(self):
        from apps.metadata.models import DynamicFieldValue
        from apps.migration_cloud.staff_role_map import promote_imported_staff_roles

        user, profile = self._teacher(username="old.hod")
        DynamicFieldValue.objects.create(
            school=self.school,
            entity_type="staff",
            entity_id=str(profile.pk),
            field_key="source_role",
            value_json={"v": "Head of Department"},
        )
        promote_imported_staff_roles(school=self.school)
        user.refresh_from_db()
        self.assertEqual(user.role, User.Role.HOD)
