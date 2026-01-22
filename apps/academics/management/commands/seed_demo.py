from __future__ import annotations

import random
from datetime import date

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation, TeacherAssignment
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile


DEMO_PASSWORD = "Test1234"


class Command(BaseCommand):
    help = "Create (and optionally reset) demo data for local testing / staging."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing demo/domain data (keeps superusers) before seeding.",
        )
        parser.add_argument(
            "--keep-admin",
            action="store_true",
            default=True,
            help="Keep superuser accounts (default: True).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get("reset")

        if reset:
            self._reset_domain_data()
            self.stdout.write(self.style.WARNING("🧹 Reset domain data (kept superusers)."))

        # ---- Academic setup ----
        year, _ = AcademicYear.objects.get_or_create(
            name="2025/2026",
            defaults={"start_date": date(2025, 9, 1), "end_date": date(2026, 7, 31), "is_active": True},
        )
        if not year.is_active:
            year.is_active = True
            year.save(update_fields=["is_active"])

        term1, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.FIRST,
            defaults={"start_date": date(2025, 9, 1), "end_date": date(2025, 12, 15), "is_active": True, "position": 1},
        )
        term2, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.SECOND,
            defaults={"start_date": date(2026, 1, 5), "end_date": date(2026, 3, 20), "is_active": False, "position": 2},
        )
        term3, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.THIRD,
            defaults={"start_date": date(2026, 4, 6), "end_date": date(2026, 7, 10), "is_active": False, "position": 3},
        )
        # Make Term 1 active for demo
        Term.objects.filter(academic_year=year).update(is_active=False)
        term1.is_active = True
        term1.save(update_fields=["is_active"])

        department, _ = Department.objects.get_or_create(name="General Studies", code="GEN")

        form3, _ = Classroom.objects.get_or_create(
            academic_year=year,
            department=department,
            name="Form 3",
            defaults={"code": "F3"},
        )
        form4, _ = Classroom.objects.get_or_create(
            academic_year=year,
            department=department,
            name="Form 4",
            defaults={"code": "F4"},
        )

        general, _ = Specialty.objects.get_or_create(department=department, name="General", defaults={"code": "GEN"})

        english, _ = Subject.objects.get_or_create(name="English")
        math, _ = Subject.objects.get_or_create(name="Mathematics")
        physics, _ = Subject.objects.get_or_create(name="Physics")

        # ---- Users ----
        parent1 = self._get_or_create_user(
            username="parent1",
            email="parent1@example.com",
            role=User.Role.PARENT,
            first_name="Parent",
            last_name="One",
        )
        parent2 = self._get_or_create_user(
            username="parent2",
            email="parent2@example.com",
            role=User.Role.PARENT,
            first_name="Parent",
            last_name="Two",
        )

        teacher1_user = self._get_or_create_user(
            username="teacher1",
            email="teacher1@example.com",
            role=User.Role.TEACHER,
            first_name="Teacher",
            last_name="One",
        )
        teacher2_user = self._get_or_create_user(
            username="teacher2",
            email="teacher2@example.com",
            role=User.Role.TEACHER,
            first_name="Teacher",
            last_name="Two",
        )

        # Teacher profiles
        teacher1, _ = TeacherProfile.objects.get_or_create(
            user=teacher1_user,
            defaults={"staff_id": "T-001", "phone": "+237600000001"},
        )
        teacher2, _ = TeacherProfile.objects.get_or_create(
            user=teacher2_user,
            defaults={"staff_id": "T-002", "phone": "+237600000002"},
        )

        # Students
        student1, _ = StudentProfile.objects.get_or_create(
            student_code="F3-0001",
            defaults={
                "first_name": "Student",
                "last_name": "One",
                "academic_year": year,
                "classroom": form3,
                "specialty": general,
            },
        )
        student2, _ = StudentProfile.objects.get_or_create(
            student_code="F3-0002",
            defaults={
                "first_name": "Student",
                "last_name": "Two",
                "academic_year": year,
                "classroom": form3,
                "specialty": general,
            },
        )

        # Link parents to students
        StudentGuardian.objects.get_or_create(student=student1, guardian_user=parent1)
        StudentGuardian.objects.get_or_create(student=student2, guardian_user=parent2)

        # ---- Assignments ----
        # Teacher 1 teaches two subjects
        sa_eng_f3, _ = SubjectAssignment.objects.get_or_create(
            academic_year=year,
            term=term1,
            classroom=form3,
            specialty=general,
            subject=english,
            defaults={"coefficient": 2},
        )
        sa_math_f3, _ = SubjectAssignment.objects.get_or_create(
            academic_year=year,
            term=term1,
            classroom=form3,
            specialty=general,
            subject=math,
            defaults={"coefficient": 2},
        )
        # Teacher 2 teaches Physics
        sa_phy_f3, _ = SubjectAssignment.objects.get_or_create(
            academic_year=year,
            term=term1,
            classroom=form3,
            specialty=general,
            subject=physics,
            defaults={"coefficient": 2},
        )

        # Evals teacher assignments (drives the teacher marks UI)
        TeacherAssignment.objects.get_or_create(
            teacher=teacher1,
            academic_year=year,
            subject_assignment=sa_eng_f3,
            defaults={"is_active": True},
        )
        TeacherAssignment.objects.get_or_create(
            teacher=teacher1,
            academic_year=year,
            subject_assignment=sa_math_f3,
            defaults={"is_active": True},
        )
        TeacherAssignment.objects.get_or_create(
            teacher=teacher2,
            academic_year=year,
            subject_assignment=sa_phy_f3,
            defaults={"is_active": True},
        )

        # ---- Seed some evaluations so ranking + report screens are not empty ----
        self._seed_evals_for_student(
            year,
            term1,
            student1,
            [
                (sa_eng_f3, teacher1),
                (sa_math_f3, teacher1),
                (sa_phy_f3, teacher2),
            ],
        )
        self._seed_evals_for_student(
            year,
            term1,
            student2,
            [
                (sa_eng_f3, teacher1),
                (sa_math_f3, teacher1),
                (sa_phy_f3, teacher2),
            ],
        )

        # Print credentials
        self.stdout.write(self.style.SUCCESS("\n✅ Demo data ready."))
        self.stdout.write("\nLogin credentials (password for all: Test1234):")
        self.stdout.write("  Admin: (your existing superuser)")
        self.stdout.write("  Parents: parent1, parent2")
        self.stdout.write("  Teachers: teacher1, teacher2\n")

    def _get_or_create_user(self, username: str, email: str, role: str, first_name: str, last_name: str) -> User:
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": role,
                "first_name": first_name,
                "last_name": last_name,
                "is_active": True,
            },
        )
        # Keep role in sync if user already existed
        changed = False
        if user.role != role:
            user.role = role
            changed = True
        if created or not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            changed = True
        if changed:
            user.save()

        return user

    def _seed_evals_for_student(
        self,
        year: AcademicYear,
        term: Term,
        student: StudentProfile,
        subject_assignments,
    ):
        for subject_assignment, teacher in subject_assignments:
            # Deterministic-ish demo scores
            base = random.randint(10, 18)
            seq1 = base
            seq2 = max(0, min(20, base + random.randint(-2, 2)))
            exam = max(0, min(20, base + random.randint(-3, 3)))
            Evaluation.objects.get_or_create(
                academic_year=year,
                term=term,
                student=student,
                subject_assignment=subject_assignment,
                defaults={
                    "teacher": teacher,
                    "seq1_score": seq1,
                    "seq2_score": seq2,
                    "exam_score": exam,
                    "mock_score": None,
                    "practical_score": None,
                    "test1": seq1,
                    "test2": seq2,
                },
            )

    def _reset_domain_data(self):
        # Keep superusers, remove other users
        User.objects.filter(is_superuser=False).delete()

        # Clear domain tables
        Evaluation.objects.all().delete()
        TeacherAssignment.objects.all().delete()
        SubjectAssignment.objects.all().delete()

        StudentGuardian.objects.all().delete()
        StudentProfile.objects.all().delete()
        TeacherProfile.objects.all().delete()
        Classroom.objects.all().delete()
        Specialty.objects.all().delete()
        Subject.objects.all().delete()
        Department.objects.all().delete()
        Term.objects.all().delete()
        AcademicYear.objects.all().delete()
