"""Edge parity Slice 5 — grades (``evals.Evaluation``) ride the rail DOWN-ONLY.

A mark is not master data. The cloud is authoritative, so this entity is deliberately
absent from ``_LWW_SAFE_ENTITIES``: ``evaluation`` aliases to the protected
``grade_entry`` policy, which makes ``_conflict_decision`` apply a ``cloud-pull`` on the
box but raise a Sync Center CONFLICT for a box push or an online edit. A teacher's
offline mark therefore never silently overwrites the cloud's.

Locks: (1) registration + the auto-derived field set, with the shared-User audit FKs
dropped as non-portable; (2) the entity is protected, NOT LWW-safe, and its alias
resolves to ``grade_entry`` EXPLICITLY rather than by ``get_policy``'s fail-closed
default; (3) the full direction matrix — down applies, up conflicts; (4) the FK remap
graph reaches ``subject_assignment`` (which is why the teaching grid had to land first)
and ``student``; (5) a real cloud-pull lands the cloud score on a rewound box row; (6) a
box push leaves the cloud value untouched.

It also carries the regression seal for the UNGUARDED ``setattr`` in
``_apply_changes_inner``: the assignment loop used to sit OUTSIDE the per-row
try/except, so a value that raises at assignment time (rather than at save time) escaped
``apply_changes`` entirely and killed the apply for EVERY entity in the bundle instead of
degrading that one row to a 422. Grades ride this exact update path, so the guarantee is
load-bearing here.
"""
from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.accounts.models import User
from apps.api.sync_services import (
    _LWW_SAFE_ENTITIES,
    _conflict_decision,
    _get_entity_config,
    _insert_fk_targets,
    _sync_conflict_policy,
    apply_changes,
)
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_inbox import apply_pulled_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle
from apps.sync_engine.policy_registry import MergeStrategy, normalize_entity

_SIGN_KEY = "edge-grades-test-key"
_ENTITY = "evaluation"


class GradeEntityRegistrationTests(TestCase):
    def test_entity_registered_and_audit_fks_dropped(self):
        cfg = _get_entity_config(include_derived=True)
        self.assertIn(_ENTITY, cfg, "evaluation not registered in the two-way config")
        _model, fields = cfg[_ENTITY]
        for expected in ("seq1_score", "exam_score", "final_score", "student_id"):
            self.assertIn(expected, fields)
        # subject_assignment is the wave-2 entity; grades depend on it existing on the box.
        self.assertIn("subject_assignment_id", fields)
        # created_by / updated_by are FKs to the SHARED accounts.User — pk not portable.
        self.assertNotIn("created_by_id", fields)
        self.assertNotIn("updated_by_id", fields)
        self.assertNotIn("school", fields)
        self.assertNotIn("client_offline_id", fields)
        self.assertNotIn("updated_at", fields)

    def test_alias_resolves_to_grade_entry_explicitly(self):
        """Protection must be DECLARED, not merely inherited from the fail-closed default."""
        self.assertEqual(normalize_entity(_ENTITY), "grade_entry")

    def test_entity_is_protected_and_not_lww_safe(self):
        self.assertNotIn(
            _ENTITY,
            _LWW_SAFE_ENTITIES,
            "a mark must never be registered as benign two-way LWW master data",
        )
        strategy, protected = _sync_conflict_policy(_ENTITY)
        self.assertTrue(protected, "grades must be protected (cloud-authoritative)")
        self.assertEqual(strategy, MergeStrategy.MANUAL_REVIEW)

    def test_direction_matrix_is_down_only(self):
        newer = timezone.now()
        older = newer - dt.timedelta(days=1)
        # Cloud -> box applies even though the box row is older.
        self.assertEqual(_conflict_decision(_ENTITY, "cloud-pull", newer, older), "apply")
        # Box -> cloud NEVER silently overwrites, even carrying a newer timestamp.
        self.assertEqual(_conflict_decision(_ENTITY, "edge-push", newer, older), "conflict")
        # An ordinary online delta edit is likewise held for review.
        self.assertEqual(_conflict_decision(_ENTITY, None, newer, older), "conflict")

    def test_fk_remap_reaches_the_teaching_grid_and_student(self):
        targets = _insert_fk_targets(_get_entity_config(include_derived=True)).get(_ENTITY)
        self.assertEqual(targets.get("subject_assignment_id"), "subject_assignment")
        self.assertEqual(targets.get("student_id"), "student")


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class GradeDownOnlyRoundTripTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Grade {uid}", slug=f"gr-{uid}", subdomain=f"gr{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"gr_admin_{uid}", password="Test1234", email=f"gr{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            name=f"Dept {uid}", code=f"D{uid[:5]}", school=self.school
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name=f"20{uid[:2]}/20{uid[2:4]}",
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
        # Evaluation.clean() requires the student's year to match the assignment's.
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Njoya",
            date_of_birth="2012-01-01",
            student_code=f"STD{uid[:5]}",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.teacher_user = User.objects.create_user(
            username=f"gr_teacher_{uid}", password="Test1234"
        )
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)

    def _evaluation(self, seq1="15.00"):
        return Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal(seq1),
        )

    def test_cloud_pull_lands_the_cloud_mark_on_the_box(self):
        ev = self._evaluation(seq1="15.00")
        data, _meta = build_edge_delta_bundle(self.school, since=None, entities=[_ENTITY])
        rows, errors = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errors, errors)
        self.assertTrue(any(r["id"] == ev.pk for r in rows if r["entity_type"] == _ENTITY))

        # Rewind the box copy to a different, older mark.
        old = timezone.now() - timezone.timedelta(days=1)
        Evaluation.objects.filter(pk=ev.pk).update(seq1_score=Decimal("3.00"), updated_at=old)

        # Down is allowed for a protected entity.
        result = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        ev.refresh_from_db()
        self.assertEqual(ev.seq1_score, Decimal("15.00"))

    def test_box_push_does_not_overwrite_the_cloud_mark(self):
        ev = self._evaluation(seq1="15.00")
        # A box claims a newer mark. Protected => conflict, never a silent overwrite.
        rows = [
            {
                "entity_type": _ENTITY,
                "id": ev.pk,
                "changes": {"seq1_score": "19.00"},
                "updated_at": (timezone.now() + dt.timedelta(days=1)).isoformat(),
            }
        ]
        out = apply_changes(
            str(self.school.id), self.user, rows, persist_conflicts=True, sync_origin="edge-push"
        )
        self.assertEqual(out["success_count"], 0, out)
        self.assertEqual(len(out["conflicts"]), 1, out)
        ev.refresh_from_db()
        self.assertEqual(ev.seq1_score, Decimal("15.00"), "a box push overwrote a cloud mark")

    def test_bad_assignment_value_degrades_one_row_not_the_whole_bundle(self):
        """Regression seal for the unguarded setattr (see module docstring).

        Simulates any field that raises at ASSIGNMENT time by widening the allowed set to
        include an M2M. Before the fix this raised straight out of ``apply_changes``.
        """
        ev = self._evaluation(seq1="15.00")
        good = self._other_assignment_evaluation()

        real_cfg = _get_entity_config(include_derived=True)
        model, fields = real_cfg["subject_assignment"]
        poisoned = dict(real_cfg)
        poisoned["subject_assignment"] = (model, set(fields) | {"teachers"})

        rows = [
            {  # raises on setattr — must degrade to 422, not blow up the batch
                "entity_type": "subject_assignment",
                "id": self.assignment.pk,
                "changes": {"teachers": "accounts.User.None"},
                "updated_at": (timezone.now() + dt.timedelta(days=1)).isoformat(),
            },
            {  # a healthy row in the SAME batch must still apply
                "entity_type": _ENTITY,
                "id": good.pk,
                "changes": {"seq1_score": "17.00"},
                "updated_at": (timezone.now() + dt.timedelta(days=1)).isoformat(),
            },
        ]
        with patch(
            "apps.api.sync_services._get_entity_config", return_value=poisoned
        ):
            out = apply_changes(
                str(self.school.id), self.user, rows,
                persist_conflicts=True, sync_origin="cloud-pull",
            )

        statuses = {r["index"]: r["status"] for r in out["results"]}
        self.assertEqual(statuses[0], 422, out)
        self.assertEqual(
            out["results"][0]["data"]["error"], "apply_failed", out["results"][0]
        )
        # The healthy row survived the poisoned one — the whole-bundle kill is gone.
        self.assertEqual(statuses[1], 200, out)
        good.refresh_from_db()
        self.assertEqual(good.seq1_score, Decimal("17.00"))
        # And the poisoned row changed nothing.
        self.assertEqual(ev.seq1_score, Decimal("15.00"))

    def _other_assignment_evaluation(self):
        """A second Evaluation on its own assignment (unique_together forbids a duplicate)."""
        subject2 = Subject.objects.create(
            school=self.school, name=f"Maths {uuid.uuid4().hex[:5]}", code=f"M{uuid.uuid4().hex[:5]}"
        )
        assignment2 = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=subject2,
            coefficient=Decimal("1.00"),
        )
        return Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=assignment2,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("5.00"),
        )
