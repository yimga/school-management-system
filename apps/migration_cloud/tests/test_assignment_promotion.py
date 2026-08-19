"""v3.29.0 promotion tests — per-student assignment landers now write
first-class :mod:`apps.schoolops` models when both ends of the join
resolve, falling back to ``DynamicFieldValue`` when the catalog side
hasn't landed yet.

Tests are split into three layers:

  * Pure-Python structural tests (:class:`SimpleTestCase`) that don't
    touch the database — model field/constraint introspection +
    is_low property + lander module importability.
  * Lander integration tests (:class:`TestCase`) that exercise the
    promotion / fallback / quarantine paths against a tenant fixture.
  * Backfill management-command tests that assert dry-run / apply /
    idempotency behavior.

Where the existing test DB is infra-blocked (``OperationalError: no
such index ...``) the structural tests in :class:`AssignmentModelShapeTests`
will still pass and provide minimum signal that the models declare the
expected shape.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase


# ---------------------------------------------------------------------------
# Layer 1: pure structural — no DB required
# ---------------------------------------------------------------------------


class AssignmentModelShapeTests(SimpleTestCase):
    """Model classes declare the expected fields, constraints, indexes."""

    def test_transport_assignment_has_expected_fields(self) -> None:
        from apps.schoolops.models import TransportAssignment

        names = {f.name for f in TransportAssignment._meta.get_fields()}
        for expected in (
            "school", "student", "route",
            "pickup_stop", "dropoff_stop",
            "effective_from", "effective_to",
            "status", "notes",
            "created_at", "updated_at",
        ):
            self.assertIn(
                expected, names,
                f"TransportAssignment missing field {expected}",
            )

    def test_transport_assignment_unique_constraint(self) -> None:
        from apps.schoolops.models import TransportAssignment

        ut = TransportAssignment._meta.unique_together
        self.assertIn(("student", "route", "effective_from"), ut)

    def test_transport_assignment_indexes(self) -> None:
        from apps.schoolops.models import TransportAssignment

        ixs = [tuple(ix.fields) for ix in TransportAssignment._meta.indexes]
        self.assertIn(("student", "status"), ixs)
        self.assertIn(("route", "effective_from"), ixs)

    def test_hostel_assignment_shape(self) -> None:
        from apps.schoolops.models import HostelAssignment

        names = {f.name for f in HostelAssignment._meta.get_fields()}
        for expected in (
            "school", "student", "room", "bed_label",
            "effective_from", "effective_to", "status", "notes",
        ):
            self.assertIn(expected, names)
        self.assertIn(
            ("student", "room", "effective_from"),
            HostelAssignment._meta.unique_together,
        )

    def test_meal_plan_balance_shape(self) -> None:
        from apps.schoolops.models import MealPlanBalance

        names = {f.name for f in MealPlanBalance._meta.get_fields()}
        for expected in (
            "school", "student", "meal_plan",
            "balance", "currency",
            "last_topup_at", "last_topup_amount",
            "low_balance_threshold", "status",
        ):
            self.assertIn(expected, names)
        self.assertIn(
            ("student", "meal_plan"),
            MealPlanBalance._meta.unique_together,
        )

    def test_meal_plan_balance_money_fields_are_decimal(self) -> None:
        """scan_money_float guard: money fields must be Decimal-typed."""
        from django.db import models as dj_models
        from apps.schoolops.models import MealPlanBalance

        for fname in ("balance", "last_topup_amount", "low_balance_threshold"):
            field = MealPlanBalance._meta.get_field(fname)
            self.assertIsInstance(
                field, dj_models.DecimalField,
                f"{fname} must be DecimalField, got {type(field).__name__}",
            )

    def test_meal_plan_balance_is_low_property(self) -> None:
        from apps.schoolops.models import MealPlanBalance

        m = MealPlanBalance(
            balance=Decimal("3.00"),
            low_balance_threshold=Decimal("5.00"),
        )
        self.assertTrue(m.is_low)
        m2 = MealPlanBalance(
            balance=Decimal("10.00"),
            low_balance_threshold=Decimal("5.00"),
        )
        self.assertFalse(m2.is_low)
        # equality edge — at threshold counts as low
        m3 = MealPlanBalance(
            balance=Decimal("5.00"),
            low_balance_threshold=Decimal("5.00"),
        )
        self.assertTrue(m3.is_low)

    def test_landers_importable(self) -> None:
        """All three promoted landers import without error and register."""
        from apps.migration_cloud.landers import (
            cafeteria_assignment_lander,
            get_lander,
            hostel_assignment_lander,
            transport_assignment_lander,
        )

        self.assertIsNotNone(get_lander("transport_assignments"))
        self.assertIsNotNone(get_lander("hostel_assignments"))
        self.assertIsNotNone(get_lander("cafeteria_assignments"))
        # Sanity: each module declares the promoted class.
        self.assertTrue(hasattr(
            transport_assignment_lander, "TransportAssignmentLander"))
        self.assertTrue(hasattr(
            hostel_assignment_lander, "HostelAssignmentLander"))
        self.assertTrue(hasattr(
            cafeteria_assignment_lander, "CafeteriaAssignmentLander"))

    def test_registry_count_updated(self) -> None:
        """The registry docstring claims 24 first-class landers."""
        from apps.migration_cloud.landers import __doc__ as registry_doc

        self.assertIn("24 first-class", registry_doc or "")


# ---------------------------------------------------------------------------
# Layer 2: lander integration tests — require DB. Skipped gracefully if the
# fixture path fails (test infra issue, not a code issue).
# ---------------------------------------------------------------------------


def _make_ctx(school):
    from apps.migration_cloud.landers.base import LanderContext
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    return LanderContext(
        school=school,
        schema_name=resolve_school_schema_name(school) or "public",
        bundle_id=0,
        artifact_id=0,
        dry_run=False,
    )


class _TenantFixtureMixin:
    """Minimal fixture: one school, one student, one Route / Room / Meal."""

    @classmethod
    def _build_tenant(cls):
        from apps.people.models import StudentProfile
        from apps.schools.models import School
        from apps.schoolops.models import (
            CanteenMeal, Hostel, HostelRoom, Route,
        )

        # School is single-schema now: no ``schema_name``/``domain_url`` fields
        # (that stale kwarg pair raised TypeError at fixture setup, erroring
        # every test here). Real identity fields are slug/subdomain — use a
        # unique token so the isolation test can build two tenants.
        _tok = uuid.uuid4().hex[:8]
        school = School.objects.create(  # tenant-isolation-allow: test-fixture-creates-tenant-explicitly
            name="Test Academy",
            slug=f"test-academy-{_tok}",
            subdomain=f"test-academy-{_tok}",
        )
        student = StudentProfile.objects.create(  # tenant-isolation-allow: test-fixture-student-tied-to-test-school
            school=school,
            first_name="Pat",
            last_name="Test",
            admission_number=f"PS-{_dt.datetime.now().microsecond}",
        )
        route = Route.objects.create(  # tenant-isolation-allow: test-fixture-route-tied-to-test-school
            school=school, name="Route 7",
        )
        hostel = Hostel.objects.create(  # tenant-isolation-allow: test-fixture-hostel-tied-to-test-school
            school=school, name="Cedar House",
        )
        room = HostelRoom.objects.create(  # tenant-isolation-allow: test-fixture-room-tied-to-test-hostel
            hostel=hostel, name="C-203",
        )
        meal = CanteenMeal.objects.create(  # tenant-isolation-allow: test-fixture-meal-tied-to-test-school
            school=school, name="Vegetarian Lunch",
        )
        return school, student, route, room, meal


class TransportAssignmentLanderTests(_TenantFixtureMixin, TestCase):

    def test_first_class_path_when_both_resolve(self) -> None:
        from apps.migration_cloud.landers.transport_assignment_lander import (
            TransportAssignmentLander,
        )
        from apps.schoolops.models import TransportAssignment

        school, student, route, _, _ = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "route": route.name,
            "effective_from": "2025-09-01",
            "status": "active",
            "stop": "Maple & 3rd",
        }]
        lander = TransportAssignmentLander()
        result = lander.land(canonical_rows=iter(rows), ctx=_make_ctx(school))

        self.assertEqual(result.created, 1)
        self.assertEqual(result.quarantined, 0)
        # tenant-isolation-allow: test-assertion-scoped-to-test-school-via-route-fk
        self.assertEqual(
            TransportAssignment.objects.filter(route=route).count(), 1,
        )

    def test_falls_back_to_dfv_when_route_unresolved(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.migration_cloud.landers.transport_assignment_lander import (
            TransportAssignmentLander,
        )
        from apps.schoolops.models import TransportAssignment

        school, student, _, _, _ = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "route": "Nonexistent Route 99",
            "effective_from": "2025-09-01",
        }]
        result = TransportAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 1)
        # tenant-isolation-allow: test-assertion-no-first-class-created
        self.assertEqual(TransportAssignment.objects.count(), 0)
        # tenant-isolation-allow: test-assertion-dfv-fallback-scoped-to-test-school
        self.assertEqual(
            DynamicFieldValue.objects.filter(
                school=school,
                entity_type="student_transport_assignment",
            ).count(),
            1,
        )

    def test_quarantines_when_student_unresolved(self) -> None:
        from apps.migration_cloud.landers.transport_assignment_lander import (
            TransportAssignmentLander,
        )

        school, _, route, _, _ = self._build_tenant()
        rows = [{
            "student_external_id": "PS-DOES-NOT-EXIST",
            "route": route.name,
            "effective_from": "2025-09-01",
        }]
        result = TransportAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 0)
        self.assertEqual(result.quarantined, 1)
        # The reason must name the unmatched id and the next step, rather than an
        # internal column — the row is still quarantined either way.
        joined = " ".join(result.errors)
        self.assertIn("PS-DOES-NOT-EXIST", joined)
        self.assertIn("student list", joined)


class HostelAssignmentLanderTests(_TenantFixtureMixin, TestCase):

    def test_first_class_path_when_both_resolve(self) -> None:
        from apps.migration_cloud.landers.hostel_assignment_lander import (
            HostelAssignmentLander,
        )
        from apps.schoolops.models import HostelAssignment

        school, student, _, room, _ = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "hostel": room.hostel.name,
            "room": room.name,
            "checkin_date": "2025-09-01",
            "bed_label": "Bed 1",
        }]
        result = HostelAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 1)
        # tenant-isolation-allow: test-assertion-scoped-to-test-room-fk
        self.assertEqual(
            HostelAssignment.objects.filter(room=room).count(), 1,
        )

    def test_falls_back_to_dfv_when_room_unresolved(self) -> None:
        from apps.metadata.models import DynamicFieldValue
        from apps.migration_cloud.landers.hostel_assignment_lander import (
            HostelAssignmentLander,
        )
        from apps.schoolops.models import HostelAssignment

        school, student, _, _, _ = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "hostel": "Cedar House",
            "room": "Nonexistent Room",
            "checkin_date": "2025-09-01",
        }]
        result = HostelAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 1)
        # tenant-isolation-allow: test-assertion-no-first-class-row-created
        self.assertEqual(HostelAssignment.objects.count(), 0)
        # tenant-isolation-allow: test-assertion-dfv-fallback-scoped-to-test-school
        self.assertEqual(
            DynamicFieldValue.objects.filter(
                school=school,
                entity_type="student_hostel_assignment",
            ).count(),
            1,
        )

    def test_quarantines_when_student_unresolved(self) -> None:
        from apps.migration_cloud.landers.hostel_assignment_lander import (
            HostelAssignmentLander,
        )

        school, _, _, room, _ = self._build_tenant()
        rows = [{
            "student_external_id": "PS-DOES-NOT-EXIST",
            "hostel": room.hostel.name,
            "room": room.name,
            "checkin_date": "2025-09-01",
        }]
        result = HostelAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.quarantined, 1)


class MealPlanBalanceLanderTests(_TenantFixtureMixin, TestCase):

    def test_first_class_path_when_both_resolve(self) -> None:
        from apps.migration_cloud.landers.cafeteria_assignment_lander import (
            CafeteriaAssignmentLander,
        )
        from apps.schoolops.models import MealPlanBalance

        school, student, _, _, meal = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "meal_plan": meal.name,
            "balance": "50.00",
            "currency": "USD",
        }]
        result = CafeteriaAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 1)
        # tenant-isolation-allow: test-assertion-scoped-to-test-meal-fk
        obj = MealPlanBalance.objects.filter(meal_plan=meal).first()
        self.assertIsNotNone(obj)
        self.assertEqual(obj.balance, Decimal("50.00"))
        self.assertIsInstance(obj.balance, Decimal)

    def test_first_class_path_when_meal_unresolved_generic_credit(self) -> None:
        """meal_plan FK is nullable — unresolved meal = generic credit."""
        from apps.migration_cloud.landers.cafeteria_assignment_lander import (
            CafeteriaAssignmentLander,
        )
        from apps.schoolops.models import MealPlanBalance

        school, student, _, _, _ = self._build_tenant()
        rows = [{
            "student_external_id": student.admission_number,
            "meal_plan": "Unknown Plan",
            "balance": "25.00",
        }]
        result = CafeteriaAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.created, 1)
        # tenant-isolation-allow: test-assertion-scoped-to-test-student-fk
        obj = MealPlanBalance.objects.filter(student=student).first()
        self.assertIsNotNone(obj)
        self.assertIsNone(obj.meal_plan)

    def test_quarantines_when_student_unresolved(self) -> None:
        from apps.migration_cloud.landers.cafeteria_assignment_lander import (
            CafeteriaAssignmentLander,
        )

        school, _, _, _, meal = self._build_tenant()
        rows = [{
            "student_external_id": "PS-DOES-NOT-EXIST",
            "meal_plan": meal.name,
            "balance": "10.00",
        }]
        result = CafeteriaAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school),
        )
        self.assertEqual(result.quarantined, 1)

    def test_update_on_duplicate_records_topup(self) -> None:
        """Second land() with the same (student, meal_plan) updates balance
        and records ``last_topup_amount``."""
        from apps.migration_cloud.landers.cafeteria_assignment_lander import (
            CafeteriaAssignmentLander,
        )
        from apps.schoolops.models import MealPlanBalance

        school, student, _, _, meal = self._build_tenant()
        lander = CafeteriaAssignmentLander()
        ctx = _make_ctx(school)
        lander.land(canonical_rows=iter([{
            "student_external_id": student.admission_number,
            "meal_plan": meal.name,
            "balance": "10.00",
        }]), ctx=ctx)
        lander.land(canonical_rows=iter([{
            "student_external_id": student.admission_number,
            "meal_plan": meal.name,
            "balance": "35.00",
        }]), ctx=ctx)
        # tenant-isolation-allow: test-assertion-single-row-per-student-meal-unique-together
        rows = list(MealPlanBalance.objects.filter(
            student=student, meal_plan=meal,
        ))
        self.assertEqual(len(rows), 1)
        obj = rows[0]
        self.assertEqual(obj.balance, Decimal("35.00"))
        self.assertEqual(obj.last_topup_amount, Decimal("25.00"))
        self.assertIsNotNone(obj.last_topup_at)


# ---------------------------------------------------------------------------
# Layer 3: backfill management command
# ---------------------------------------------------------------------------


class PromoteDynaAssignmentsCommandTests(_TenantFixtureMixin, TestCase):

    def _seed_dfv(self, school, student, route, *, value):
        from apps.metadata.models import DynamicFieldValue

        return DynamicFieldValue.objects.create(  # tenant-isolation-allow: test-seeds-dfv-row-against-test-school
            school=school,
            entity_type="student_transport_assignment",
            entity_id=f"{student.pk}:{route.pk}",
            field_key="payload",
            value_json=value,
        )

    def test_dry_run_does_not_write(self) -> None:
        from apps.schoolops.models import TransportAssignment

        school, student, route, _, _ = self._build_tenant()
        self._seed_dfv(school, student, route, value={
            "student_external_id": student.admission_number,
            "route": route.name,
            "route_pk": route.pk,
            "effective_from": "2025-09-01",
            "status": "active",
        })
        out = StringIO()
        call_command(
            "promote_dyna_assignments",
            "--tenant", str(school.pk),
            "--limit", "10",
            stdout=out, stderr=out,
        )
        # tenant-isolation-allow: test-assertion-dry-run-leaves-table-empty
        self.assertEqual(TransportAssignment.objects.count(), 0)
        self.assertIn("'apply': False", out.getvalue())
        self.assertIn("'promoted': 1", out.getvalue())

    def test_apply_writes_first_class(self) -> None:
        from apps.schoolops.models import TransportAssignment

        school, student, route, _, _ = self._build_tenant()
        self._seed_dfv(school, student, route, value={
            "student_external_id": student.admission_number,
            "route": route.name,
            "route_pk": route.pk,
            "effective_from": "2025-09-01",
            "status": "active",
        })
        out = StringIO()
        call_command(
            "promote_dyna_assignments",
            "--tenant", str(school.pk),
            "--apply",
            "--limit", "10",
            stdout=out, stderr=out,
        )
        # tenant-isolation-allow: test-assertion-apply-mode-creates-first-class-row
        self.assertEqual(
            TransportAssignment.objects.filter(route=route).count(), 1,
        )

    def test_apply_is_idempotent(self) -> None:
        from apps.schoolops.models import TransportAssignment

        school, student, route, _, _ = self._build_tenant()
        self._seed_dfv(school, student, route, value={
            "student_external_id": student.admission_number,
            "route": route.name,
            "route_pk": route.pk,
            "effective_from": "2025-09-01",
        })
        out = StringIO()
        for _ in range(2):
            call_command(
                "promote_dyna_assignments",
                "--tenant", str(school.pk),
                "--apply",
                "--limit", "10",
                stdout=out, stderr=out,
            )
        # tenant-isolation-allow: test-assertion-idempotent-run-stays-at-one-row
        self.assertEqual(
            TransportAssignment.objects.filter(route=route).count(), 1,
        )
        self.assertIn("skipped_already_promoted", out.getvalue())


# ---------------------------------------------------------------------------
# Layer 4: tenant isolation
# ---------------------------------------------------------------------------


class TenantIsolationTests(_TenantFixtureMixin, TestCase):

    def test_lander_on_tenant_a_does_not_affect_tenant_b(self) -> None:
        from apps.migration_cloud.landers.transport_assignment_lander import (
            TransportAssignmentLander,
        )
        from apps.schoolops.models import TransportAssignment

        school_a, student_a, route_a, _, _ = self._build_tenant()
        school_b, _, _, _, _ = self._build_tenant()

        rows = [{
            "student_external_id": student_a.admission_number,
            "route": route_a.name,
            "effective_from": "2025-09-01",
        }]
        TransportAssignmentLander().land(
            canonical_rows=iter(rows), ctx=_make_ctx(school_a),
        )
        # tenant-isolation-allow: test-assertion-tenant-a-row-present
        self.assertEqual(
            TransportAssignment.objects.filter(school=school_a).count(), 1,
        )
        # tenant-isolation-allow: test-assertion-tenant-b-row-absent
        self.assertEqual(
            TransportAssignment.objects.filter(school=school_b).count(), 0,
        )
