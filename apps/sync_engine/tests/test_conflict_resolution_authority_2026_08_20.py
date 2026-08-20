"""G5: the conflict screen was a way AROUND the authority model it exists to serve.

Every inbound write is graded by ``policy_registry``. Money and grades are
cloud-authoritative, so a box push to one of them is refused and RECORDED as a conflict;
and a set of per-field columns — salary, payroll and leave authorization, offboarding,
the grading coefficient — may never travel upward at all.

The Sync Center then offered "Keep client" to anyone who could reach the page, and that
button wrote the box's rejected value straight into the cloud record. The rail refused it
and the review screen applied it. Two smaller holes sat underneath:

  * the apply ignored ``_DOWN_ONLY_FIELDS_PER_ENTITY`` entirely, so resolving an otherwise
    benign teacher conflict in the client's favour wrote the box's SALARY;
  * it caught only ``DoesNotExist``, so a client payload pointing at a since-deleted parent
    would raise out of the view — and on PostgreSQL not even there, but at COMMIT, where
    no handler could catch it.

What is proven here is the rule the brief states: a protected entity's conflict may only
be resolved by someone who could have made that write directly.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict
from apps.sync_engine.conflict_actions import (
    apply_resolution,
    field_comparison,
    may_resolve,
)


class _Fixture(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Auth {uid}", slug=f"auth-{uid}", subdomain=f"auth{uid}"
        )
        self.root = User.objects.create_superuser(
            username=f"root_{uid}", password="Test1234", email=f"r{uid}@t.com"
        )
        self.clerk = User.objects.create_user(
            username=f"clerk_{uid}", password="Test1234", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.clerk, school=self.school, role="ADMIN", is_primary=True
        )

    def _conflict(self, entity_type, entity_id=1, client=None, server=None):
        return SyncConflict.objects.create(
            school=self.school,
            entity_type=entity_type,
            entity_id=entity_id,
            client_data=client or {},
            server_data=server or {},
            status=SyncConflict.Status.PENDING,
        )


class KeepClientAuthorityTests(_Fixture):
    def test_a_clerk_may_not_apply_the_offline_version_of_a_money_record(self):
        conflict = self._conflict("invoice", client={"total_amount": "1.00"})
        allowed, reason = may_resolve(self.clerk, conflict, "client")
        self.assertFalse(allowed)
        self.assertIn("cloud-authoritative", reason)

    def test_the_refusal_names_the_permission_that_would_be_needed(self):
        conflict = self._conflict("invoice", client={"total_amount": "1.00"})
        _allowed, reason = may_resolve(self.clerk, conflict, "client")
        self.assertIn("finance.change_invoice", reason)

    def test_a_superuser_may(self):
        conflict = self._conflict("invoice", client={"total_amount": "1.00"})
        allowed, _reason = may_resolve(self.root, conflict, "client")
        self.assertTrue(allowed)

    def test_the_holder_of_the_model_permission_may(self):
        """"Someone who could have made that write directly" is exactly Django's own
        model permission, not a second, parallel notion of authority."""
        from django.contrib.auth.models import Permission

        self.clerk.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="finance", codename="change_invoice"
            )
        )
        refreshed = User.objects.get(pk=self.clerk.pk)  # permission cache is per instance
        allowed, _reason = may_resolve(refreshed, self._conflict("invoice"), "client")
        self.assertTrue(allowed)

    def test_keeping_the_SERVER_version_stays_open_to_anyone(self):
        """Refusing this would leave protected conflicts to rot: keeping the cloud copy
        changes no data, and someone has to be able to clear the queue."""
        conflict = self._conflict("invoice", client={"total_amount": "1.00"})
        self.assertTrue(may_resolve(self.clerk, conflict, "server")[0])
        self.assertTrue(may_resolve(self.clerk, conflict, "discard")[0])

    def test_a_benign_master_data_conflict_is_not_gated(self):
        self.assertTrue(may_resolve(self.clerk, self._conflict("department"), "client")[0])

    def test_an_online_required_domain_can_never_be_settled_from_the_offline_copy(self):
        from unittest import mock

        from apps.sync_engine.policy_registry import MergeStrategy, POLICIES, SyncPolicy

        locked = dict(POLICIES)
        locked["department"] = SyncPolicy(
            entity="department", strategy=MergeStrategy.ONLINE_REQUIRED, protected=True
        )
        with mock.patch.dict("apps.sync_engine.policy_registry.POLICIES", locked, clear=True):
            allowed, reason = may_resolve(self.root, self._conflict("department"), "client")
        self.assertFalse(allowed, "not even a superuser: the strategy would be cosmetic")
        self.assertIn("live online transaction", reason)

    def test_the_gate_is_enforced_by_apply_resolution_not_only_by_the_template(self):
        """Hiding the button is a courtesy. The refusal has to live in the action, or a
        crafted POST walks straight past it."""
        conflict = self._conflict("invoice", client={"total_amount": "1.00"})
        ok, reason = apply_resolution(conflict, "client", self.clerk)
        self.assertFalse(ok)
        self.assertIn("cloud-authoritative", reason)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)


class DownOnlyFieldsAreNeverAppliedTests(_Fixture):
    def setUp(self):
        super().setUp()
        from apps.people.models import TeacherProfile

        self.teacher_user = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:6]}", password="Test1234", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school, user=self.teacher_user, salary_amount=Decimal("100.00"),
            phone="111",
        )
        self.TeacherProfile = TeacherProfile

    def test_keeping_the_offline_version_does_not_move_pay(self):
        """`teacher` is LWW-safe precisely BECAUSE its pay columns are down-only. If the
        review screen ignores that, the entity's safety classification is a fiction."""
        conflict = self._conflict(
            "teacher", entity_id=self.teacher.pk,
            client={"phone": "222", "salary_amount": "999999.00"},
        )
        ok, _reason = apply_resolution(conflict, "client", self.root)
        self.assertTrue(ok)

        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.phone, "222", "the benign field should have landed")
        self.assertEqual(
            self.teacher.salary_amount, Decimal("100.00"),
            "a box value reached a cloud-governed pay column through the review screen",
        )

    def test_the_refusal_is_recorded_on_the_conflict_rather_than_swallowed(self):
        conflict = self._conflict(
            "teacher", entity_id=self.teacher.pk,
            client={"phone": "333", "salary_amount": "5.00"},
        )
        apply_resolution(conflict, "client", self.root, note="agreed with the bursar")
        conflict.refresh_from_db()
        self.assertIn("agreed with the bursar", conflict.resolution_note)
        self.assertIn("salary_amount", conflict.resolution_note)

    def test_who_and_when_are_recorded(self):
        conflict = self._conflict("teacher", entity_id=self.teacher.pk, client={"phone": "444"})
        apply_resolution(conflict, "client", self.root, note="phone corrected on site")
        conflict.refresh_from_db()
        self.assertEqual(conflict.resolved_by_id, self.root.pk)
        self.assertIsNotNone(conflict.resolved_at)


class ResolutionRobustnessTests(_Fixture):
    def test_a_conflict_for_a_deleted_record_reports_instead_of_raising(self):
        conflict = self._conflict("department", entity_id=987654, client={"name": "Ghost"})
        ok, _reason = apply_resolution(conflict, "client", self.root)
        self.assertTrue(ok)
        conflict.refresh_from_db()
        self.assertIn("no longer exists", conflict.resolution_note)

    def test_a_client_payload_pointing_at_a_missing_parent_is_reported(self):
        """On PostgreSQL this failure surfaces at COMMIT, outside every handler in the
        view — so it has to be caught BEFORE the write, exactly as the rail does."""
        from apps.academics.models import Classroom, Department, AcademicYear
        from datetime import date

        year = AcademicYear.objects.create(
            school=self.school, name="2026/27-c", start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
        )
        dept = Department.objects.create(school=self.school, name="D", code=f"D-{uuid.uuid4().hex[:5]}")
        room = Classroom.objects.create(
            school=self.school, academic_year=year, department=dept,
            name="R", code=f"R-{uuid.uuid4().hex[:5]}",
        )
        conflict = self._conflict(
            "classroom", entity_id=room.pk, client={"academic_year_id": year.pk + 9999}
        )
        ok, _reason = apply_resolution(conflict, "client", self.root)
        self.assertTrue(ok)
        conflict.refresh_from_db()
        self.assertIn("no longer exists", conflict.resolution_note)
        room.refresh_from_db()
        self.assertEqual(room.academic_year_id, year.pk)


class FieldComparisonTests(_Fixture):
    def test_only_the_differing_fields_are_marked(self):
        conflict = self._conflict(
            "department",
            client={"name": "New", "code": "SAME"},
            server={"name": "Old", "code": "SAME"},
        )
        rows = {r["name"]: r for r in field_comparison(conflict)}
        self.assertTrue(rows["name"]["differs"])
        self.assertFalse(rows["code"]["differs"])

    def test_a_value_that_only_differs_by_type_is_not_a_difference(self):
        """The two sides arrive by different routes — a JSON wire payload and a live model
        instance — so 3 and "3" are the same value reported differently."""
        conflict = self._conflict("department", client={"n": 3}, server={"n": "3"})
        self.assertFalse(field_comparison(conflict)[0]["differs"])

    def test_a_cloud_governed_field_is_flagged_in_the_comparison(self):
        conflict = self._conflict(
            "teacher", client={"salary_amount": "9"}, server={"salary_amount": "1"}
        )
        row = field_comparison(conflict)[0]
        self.assertTrue(row["down_only"])
