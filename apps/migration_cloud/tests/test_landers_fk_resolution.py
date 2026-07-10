"""FK-graph resolution tests for the grades / guardians / transcripts landers.

The merge-split completeness wave (2026-07-09): on this deployment these three
landers previously quarantined 100% of their rows against required FKs
(Evaluation.term/subject_assignment/teacher, StudentGuardian.guardian_user,
TranscriptVaultItem.passport/issuing_school). These tests lock the resolution
contracts edge by edge — happy path, each precise quarantine reason, the
guardian identity ladder (ref → email → provision), and passport convergence.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.grades_lander import GradesLander
from apps.migration_cloud.landers.guardian_lander import GuardianLander
from apps.migration_cloud.landers.transcripts_lander import TranscriptsLander
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    TeacherProfile,
    TranscriptVaultItem,
)
from apps.schools.models import School

User = get_user_model()


class _GraphFixtureMixin:
    """One school with a full grading graph + one placed student."""

    def _build_school(self, tag: str):
        school = School.objects.create(
            name=f"Lander {tag}", slug=f"lander-{tag}", subdomain=f"lander-{tag}"
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        department = Department.objects.create(
            school=school, name="Science", code=f"SCI-{tag}"
        )
        classroom = Classroom.objects.create(
            school=school,
            academic_year=year,
            department=department,
            name="Form 4A",
            code=f"F4A-{tag}",
        )
        specialty = Specialty.objects.create(
            school=school, department=department, name="General", code=f"GEN-{tag}"
        )
        subject = Subject.objects.create(school=school, name="Mathematics")
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        teacher_user = User.objects.create_user(
            username=f"lander_teacher_{tag}", password="pass123"
        )
        teacher = TeacherProfile.objects.create(user=teacher_user, school=school)
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
        )
        assignment.teachers.add(teacher_user)
        student = StudentProfile.objects.create(
            school=school,
            first_name="Placed",
            last_name="Student",
            admission_number=f"ADM-{tag}-1",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
        )
        return {
            "school": school,
            "year": year,
            "classroom": classroom,
            "specialty": specialty,
            "subject": subject,
            "term": term,
            "teacher": teacher,
            "teacher_user": teacher_user,
            "assignment": assignment,
            "student": student,
        }

    def _ctx(self, school, dry_run=False) -> LanderContext:
        return LanderContext(
            school=school,
            schema_name="",
            bundle_id=None,
            artifact_id=None,
            dry_run=dry_run,
        )


class GradesLanderFKResolutionTests(_GraphFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self._build_school("g1")

    def _row(self, **overrides):
        row = {
            "student_external_id": "ADM-g1-1",
            "subject_code": "Mathematics",
            "term": "FIRST",
            "academic_year": "2025/2026",
            "seq1_score": "14.50",
            "seq2_score": "15.00",
        }
        row.update(overrides)
        return row

    def test_happy_path_lands_live_evaluation(self):
        result = GradesLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)
        ev = Evaluation.objects.get(student=self.fx["student"])
        self.assertEqual(ev.term_id, self.fx["term"].pk)
        self.assertEqual(ev.subject_assignment_id, self.fx["assignment"].pk)
        self.assertEqual(ev.teacher_id, self.fx["teacher"].pk)
        self.assertEqual(ev.seq1_score, Decimal("14.50"))
        self.assertEqual(ev.seq2_score, Decimal("15.00"))

    def test_rerun_updates_not_duplicates(self):
        lander = GradesLander()
        ctx = self._ctx(self.fx["school"])
        lander.land(canonical_rows=iter([self._row()]), ctx=ctx)
        result = lander.land(
            canonical_rows=iter([self._row(seq1_score="16.00")]), ctx=ctx
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(
            Evaluation.objects.filter(student=self.fx["student"]).count(), 1
        )

    def test_missing_subject_quarantines_precisely(self):
        result = GradesLander().land(
            canonical_rows=iter([self._row(subject_code="Alchemy")]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.quarantined, 1)
        self.assertIn("no subject matching 'Alchemy'", result.errors[0])

    def test_wrong_year_stays_archival(self):
        result = GradesLander().land(
            canonical_rows=iter([self._row(academic_year="2019/2020")]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.quarantined, 1)
        self.assertIn("no academic year matching", result.errors[0])

    def test_assignment_without_teacher_quarantines(self):
        self.fx["assignment"].teachers.clear()
        result = GradesLander().land(
            canonical_rows=iter([self._row()]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.quarantined, 1)
        self.assertIn("no teacher", result.errors[0])

    def test_aggregate_score_lands_with_provenance_remark(self):
        row = self._row()
        row.pop("seq1_score")
        row.pop("seq2_score")
        row["score"] = "13.25"
        result = GradesLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.errors, [])
        ev = Evaluation.objects.get(student=self.fx["student"])
        self.assertEqual(ev.exam_score, Decimal("13.25"))
        self.assertEqual(ev.remarks, "imported aggregate score")

    def test_dry_run_resolves_without_writing(self):
        result = GradesLander().land(
            canonical_rows=iter([self._row()]),
            ctx=self._ctx(self.fx["school"], dry_run=True),
        )
        self.assertEqual(result.created, 1)
        self.assertFalse(Evaluation.objects.exists())


class GuardianLanderRelinkTests(_GraphFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self._build_school("u1")

    def _row(self, **overrides):
        row = {
            "student_external_id": "ADM-u1-1",
            "guardian_external_id": "g-1",
            "first_name": "Guard",
            "last_name": "Ian",
            "relationship": "MOTHER",
        }
        row.update(overrides)
        return row

    def test_relinks_existing_platform_user_by_ref(self):
        existing = User.objects.create_user(username="known_guardian")
        result = GuardianLander().land(
            canonical_rows=iter([self._row(guardian_user_ref="known_guardian")]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.errors, [])
        link = StudentGuardian.objects.get(student=self.fx["student"])
        self.assertEqual(link.guardian_user_id, existing.pk)
        self.assertEqual(link.relationship, "MOTHER")

    def test_relinks_existing_platform_user_by_email(self):
        existing = User.objects.create_user(
            username="mail_guardian", email="Guard@Example.com"
        )
        result = GuardianLander().land(
            canonical_rows=iter([self._row(email="guard@example.com")]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.errors, [])
        link = StudentGuardian.objects.get(student=self.fx["student"])
        self.assertEqual(link.guardian_user_id, existing.pk)

    def test_provisions_parent_with_unusable_password(self):
        result = GuardianLander().land(
            canonical_rows=iter([self._row(email="new.parent@example.com")]),
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.errors, [])
        link = StudentGuardian.objects.get(student=self.fx["student"])
        user = link.guardian_user
        self.assertEqual(user.email, "new.parent@example.com")
        self.assertFalse(user.has_usable_password())
        if hasattr(user, "role"):
            self.assertEqual(user.role, User.Role.PARENT)

    def test_no_identity_quarantines_precisely(self):
        result = GuardianLander().land(
            canonical_rows=iter([self._row()]),  # no ref, no email
            ctx=self._ctx(self.fx["school"]),
        )
        self.assertEqual(result.quarantined, 1)
        self.assertIn("no email", result.errors[0])
        self.assertFalse(StudentGuardian.objects.exists())

    def test_rerun_updates_same_link(self):
        User.objects.create_user(username="known_guardian")
        lander = GuardianLander()
        ctx = self._ctx(self.fx["school"])
        lander.land(
            canonical_rows=iter([self._row(guardian_user_ref="known_guardian")]),
            ctx=ctx,
        )
        result = lander.land(
            canonical_rows=iter(
                [self._row(guardian_user_ref="known_guardian", phone="+237600")]
            ),
            ctx=ctx,
        )
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(StudentGuardian.objects.count(), 1)


class TranscriptsLanderProvenanceTests(_GraphFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self._build_school("t1")
        self.source = School.objects.create(
            name="Issuing Src", slug="issuing-src", subdomain="issuing-src"
        )
        # The same student existed at the issuing school (transfer scenario)
        # so the passport converges on the SOURCE-minted GUID.
        self.source_profile = StudentProfile.objects.create(
            school=self.source,
            first_name="Placed",
            last_name="Student",
            admission_number="ADM-t1-1",
        )

    def test_vault_item_lands_with_source_provenance_and_shared_passport(self):
        row = {
            "student_external_id": "ADM-t1-1",
            "academic_year": "2025/2026",
            "term": "FIRST",
            "subject_code": "Mathematics",
            "final_grade": "14.75",
            "artifact_type": "transfer_grade_record",
            "artifact_ref": "2025/2026 | FIRST | Mathematics | final 14.75",
            "issuing_school_id": str(self.source.pk),
        }
        result = TranscriptsLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.errors, [])
        item = TranscriptVaultItem.objects.get(student_profile=self.fx["student"])
        self.assertEqual(item.issuing_school_id, self.source.pk)
        self.assertEqual(item.artifact_type, "transfer_grade_record")
        self.source_profile.refresh_from_db()
        self.fx["student"].refresh_from_db()
        self.assertIsNotNone(self.source_profile.passport_id)
        self.assertEqual(item.passport_id, self.source_profile.passport_id)
        self.assertEqual(
            self.fx["student"].passport_id, self.source_profile.passport_id
        )

    def test_foreign_import_falls_back_to_bundle_school(self):
        row = {
            "student_external_id": "ADM-t1-1",
            "academic_year": "2024-2025",
            "term": "Spring",
            "subject_code": "MATH-101",
            "final_grade": "A-",
            "artifact_type": "transcript",
        }
        result = TranscriptsLander().land(
            canonical_rows=iter([row]), ctx=self._ctx(self.fx["school"])
        )
        self.assertEqual(result.errors, [])
        item = TranscriptVaultItem.objects.get(student_profile=self.fx["student"])
        self.assertEqual(item.issuing_school_id, self.fx["school"].pk)
        self.assertIsNotNone(item.passport_id)
