"""LANE F probe: can work done on the BOX, through the box's own web UI, reach the cloud?

Every registered rail entity is identified by ``client_offline_id`` when it has one and
by ``pk`` when it does not (``edge_inbox.split_bundle_rows``). Nothing in the tenant
application ever WRITES a ``client_offline_id`` -- the column's only writers are the
inbound sync upsert itself and the browser offline queue, which does not cover the rail
models. So a row a bursar or a teacher creates on the appliance through an ordinary
form carries an EMPTY anchor and is pushed as an UPDATE BY PK.

These tests run that push and record what the cloud actually does with it.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.api.sync_services import apply_changes, apply_edge_inserts
from apps.evals.models import Evaluation
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_inbox import split_bundle_rows
from apps.sync_engine.edge_outbox import build_edge_delta_rows

_SIGN_KEY = "lane-f-probe-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class BoxAuthoredRowIdentityTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Lane F {uid}", slug=f"lf-{uid}", subdomain=f"lf{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"lf_admin_{uid}", password="Test1234", email=f"lf{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            name=f"Dept {uid}", code=f"D{uid[:5]}", school=self.school
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"Y{uid[:4]}",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2027, 6, 30),
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            start_date=dt.date(2026, 9, 1),
            end_date=dt.date(2026, 12, 20),
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name=f"Form 5 {uid[:3]}",
            code=f"F5{uid[:5]}",
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="Trade", code=f"TRD{uid[:6]}"
        )
        self.subject = Subject.objects.create(
            school=self.school, name="Circuit Theory", code=f"CT{uid[:5]}"
        )
        self.assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=Decimal("2.00"),
        )
        self.teacher_user = User.objects.create_user(
            username=f"lf_teacher_{uid}", password="Test1234"
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)
        # ComplianceProfile is COUNTRY-scoped (it carries no `school` column), and
        # Invoice.profile is NOT NULL, so an invoice cannot be built without one.
        self.profile = ComplianceProfile.objects.create(
            name=f"CM {uid}", country_code="CM"
        )

    def _invoice(self, student, *, anchor="", amount="50000.00"):
        return Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            academic_year=self.year,
            student=student,
            reference=f"INV-{uuid.uuid4().hex[:8]}",
            issued_date=dt.date(2026, 10, 1),
            due_date=dt.date(2026, 10, 31),
            total_amount=Decimal(amount),
            client_offline_id=anchor,
        )

    def _student(self, code_suffix="A", first="Ada"):
        return StudentProfile.objects.create(
            school=self.school,
            first_name=first,
            last_name="Njoya",
            date_of_birth="2012-01-01",
            student_code=f"STD{uuid.uuid4().hex[:6]}{code_suffix}",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )

    # ------------------------------------------------------------------
    # 1. What the box actually puts on the wire for a locally created row.
    # ------------------------------------------------------------------
    def test_ordinary_creation_leaves_the_sync_anchor_empty(self):
        """A row made through the app carries no anchor, on EVERY rail model tested."""
        student = self._student()
        Attendance.objects.create(
            school=self.school,
            student=student,
            classroom=self.classroom,
            date=dt.date(2026, 9, 15),
            status=Attendance.Status.PRESENT,
        )
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=student,
            teacher=self.teacher,
            seq1_score=Decimal("15.00"),
        )
        self._invoice(student)
        rows, _meta = build_edge_delta_rows(self.school, since=None)
        anchored = [r for r in rows if (r.get("client_offline_id") or "").strip()]
        self.assertEqual(
            anchored,
            [],
            "some rail row created by ordinary application code carried an anchor",
        )
        # And therefore EVERY one of them is routed to the update-by-pk path.
        updates, inserts, deletes, malformed = split_bundle_rows(rows)
        self.assertEqual(inserts, [], "expected no rows on the insert (anchored) path")
        self.assertGreater(len(updates), 0)
        self.assertEqual((deletes, malformed), ([], 0))

    # ------------------------------------------------------------------
    # 2. What the cloud does with that push when the pk is unknown there.
    # ------------------------------------------------------------------
    def test_box_authored_row_is_404d_by_the_cloud_and_never_lands(self):
        """The receiving side has no such pk, so the row is refused and dropped."""
        absent_pk = (StudentProfile.objects.order_by("-pk").values_list("pk", flat=True).first() or 0) + 5000
        out = apply_changes(
            str(self.school.id),
            self.user,
            [
                {
                    "entity_type": "student",
                    "id": absent_pk,
                    "client_offline_id": "",
                    "changes": {"first_name": "Ghost", "last_name": "Child"},
                    "updated_at": timezone.now().isoformat(),
                }
            ],
            persist_conflicts=True,
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 404)
        self.assertEqual(out["success_count"], 0)
        self.assertEqual(out["conflicts"], [], "a 404 is not even raised as a conflict")
        self.assertFalse(StudentProfile.objects.filter(pk=absent_pk).exists())

    def test_box_authored_row_overwrites_a_DIFFERENT_child_when_the_pk_collides(self):
        """Both deployments mint pks from their own sequence in the SAME school.

        Nothing in the update path distinguishes "pk 7 on the box" from "pk 7 here":
        the school guard passes (same tenant), the row exists, and the values land.
        """
        victim = self._student(code_suffix="V", first="Bih")
        # The box independently created a different child that happens to hold this pk.
        out = apply_changes(
            str(self.school.id),
            self.user,
            [
                {
                    "entity_type": "student",
                    "id": victim.pk,
                    "client_offline_id": "",
                    "changes": {"first_name": "Tabi", "last_name": "Ekema"},
                    "updated_at": timezone.now().isoformat(),
                }
            ],
            persist_conflicts=True,
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        victim.refresh_from_db()
        self.assertEqual(victim.first_name, "Tabi")
        self.assertEqual(victim.last_name, "Ekema")

    # ------------------------------------------------------------------
    # 3. The insert path applies NO conflict policy.
    # ------------------------------------------------------------------
    def test_anchored_upsert_overwrites_a_protected_entity_with_no_conflict(self):
        """`apply_edge_inserts` never calls `_conflict_decision`.

        A protected (cloud-authoritative) row that carries an anchor is therefore
        UPSERTED by a box push -- the direction the update path refuses with 409.
        """
        student = self._student(code_suffix="P")
        anchor = f"box-anchor-{uuid.uuid4().hex[:10]}"
        ev = Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=student,
            teacher=self.teacher,
            seq1_score=Decimal("15.00"),
            client_offline_id=anchor,
        )
        out = apply_edge_inserts(
            str(self.school.id),
            self.user,
            [
                {
                    "entity_type": "evaluation",
                    "id": 99999,
                    "client_offline_id": anchor,
                    "changes": {"seq1_score": "3.00"},
                    "updated_at": (timezone.now() - dt.timedelta(days=7)).isoformat(),
                }
            ],
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        ev.refresh_from_db()
        self.assertEqual(
            ev.seq1_score,
            Decimal("3.00"),
            "a STALE box push overwrote a protected mark through the insert path",
        )

    def test_anchored_upsert_overwrites_a_protected_invoice_with_no_conflict(self):
        student = self._student(code_suffix="I")
        anchor = f"box-inv-{uuid.uuid4().hex[:10]}"
        inv = self._invoice(student, anchor=anchor)
        out = apply_edge_inserts(
            str(self.school.id),
            self.user,
            [
                {
                    "entity_type": "invoice",
                    "id": 88888,
                    "client_offline_id": anchor,
                    "changes": {"total_amount": "1.00"},
                    "updated_at": (timezone.now() - dt.timedelta(days=7)).isoformat(),
                }
            ],
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        inv.refresh_from_db()
        self.assertEqual(
            inv.total_amount,
            Decimal("1.00"),
            "a STALE box push moved money through the insert path",
        )
