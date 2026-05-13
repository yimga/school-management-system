from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccessRole, User
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import AssessmentWeights, Evaluation, TeacherAssignment
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.reports.models import PromotionRule, TermPublishStatus
from apps.schools.school_cli_resolution import resolve_school_arg as _resolve_school


DEMO_PASSWORD = "Test1234"
YEAR_NAME = "2024/2025"


@dataclass(frozen=True)
class DemoUser:
    username: str
    email: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class DemoStudent:
    student_code: str
    first_name: str
    last_name: str
    guardian_username: str


TEACHERS = [
    DemoUser("teacher1", "teacher1@example.com", "Teacher", "One"),
    DemoUser("teacher2", "teacher2@example.com", "Teacher", "Two"),
    DemoUser("teacher3", "teacher3@example.com", "Teacher", "Three"),
]

PARENTS = [
    DemoUser("parent1", "parent1@example.com", "Parent", "One"),
    DemoUser("parent2", "parent2@example.com", "Parent", "Two"),
    DemoUser("parent3", "parent3@example.com", "Parent", "Three"),
]

STUDENTS = [
    DemoStudent("GTH-2425-001", "Student", "One", "parent1"),
    DemoStudent("GTH-2425-002", "Student", "Two", "parent2"),
    DemoStudent("GTH-2425-003", "Student", "Three", "parent3"),
]

SUBJECTS = [
    ("English", 2),
    ("Mathematics", 2),
    ("Physics", 2),
]


def _clamp(value: int, low: int = 0, high: int = 20) -> int:
    return max(low, min(high, value))


class Command(BaseCommand):
    help = "Seed 2024/2025 test data (users, academics, evaluations, reports)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-active",
            action="store_true",
            help="Deactivate other years/terms and set 2024/2025 + Term 1 active.",
        )
        parser.add_argument(
            "--school",
            type=str,
            default=None,
            help="School slug or ID for tenant-scoped seed data. Omit for global (school=None) seed.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                "This command is for development/staging only (DEBUG=False). "
                "Cannot run seed_testdata_2425 in production. Enable DEBUG in settings to use this command."
            )
        
        force_active = options.get("force_active", False)
        self.school = _resolve_school(options.get("school"))
        if options.get("school") and not self.school:
            self.stdout.write(
                self.style.ERROR(
                    "School not found for --school=%s" % options.get("school")
                )
            )
            return
        if self.school:
            self.stdout.write(
                "Seeding for school: %s (slug=%s)"
                % (self.school.name, self.school.slug)
            )

        year = self._ensure_academic_year(force_active=force_active)
        terms = self._ensure_terms(year, force_active=force_active)
        department = self._ensure_department()
        specialty = self._ensure_specialty(department)
        classroom = self._ensure_classroom(year, department)
        subject_map = self._ensure_subjects()

        self._ensure_access_roles()
        parent_users = self._ensure_parents()
        teacher_users = self._ensure_teachers()
        teacher_profiles = self._ensure_teacher_profiles(teacher_users)
        student_profiles = self._ensure_students(
            year, classroom, specialty, parent_users
        )

        assignments = self._ensure_subject_assignments(
            year, terms, classroom, specialty, subject_map
        )
        self._ensure_teacher_assignments(year, assignments, teacher_profiles)
        self._ensure_assessment_weights(year, terms)
        self._ensure_promotion_rule(year, classroom)
        self._ensure_evaluations(
            terms, assignments, student_profiles, teacher_profiles, subject_map
        )
        self._ensure_publish_statuses(year, terms)

        self.stdout.write(self.style.SUCCESS("\nTest data ready for 2024/2025."))
        self.stdout.write("Logins (password: Test1234):")
        self.stdout.write("  Teachers: teacher1, teacher2, teacher3")
        self.stdout.write("  Parents: parent1, parent2, parent3\n")

    def _ensure_academic_year(self, *, force_active: bool) -> AcademicYear:
        year, _ = AcademicYear.objects.get_or_create(
            school=self.school,
            name=YEAR_NAME,
            defaults={
                "start_date": date(2024, 9, 1),
                "end_date": date(2025, 7, 31),
                "is_active": True,
            },
        )
        if force_active:
            AcademicYear.objects.exclude(id=year.id).update(is_active=False)
        if not year.is_active:
            year.is_active = True
            year.save(update_fields=["is_active"])
        return year

    def _ensure_terms(self, year: AcademicYear, *, force_active: bool) -> list[Term]:
        term1, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.FIRST,
            defaults={
                "start_date": date(2024, 9, 2),
                "end_date": date(2024, 12, 15),
                "is_active": True,
                "position": 1,
            },
        )
        term2, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.SECOND,
            defaults={
                "start_date": date(2025, 1, 6),
                "end_date": date(2025, 3, 21),
                "is_active": False,
                "position": 2,
            },
        )
        term3, _ = Term.objects.get_or_create(
            academic_year=year,
            name=Term.Name.THIRD,
            defaults={
                "start_date": date(2025, 4, 7),
                "end_date": date(2025, 7, 11),
                "is_active": False,
                "position": 3,
            },
        )

        if force_active:
            Term.objects.filter(academic_year=year).update(is_active=False)
            term1.is_active = True
            term1.save(update_fields=["is_active"])
        return [term1, term2, term3]

    def _ensure_department(self) -> Department:
        department, _ = Department.objects.get_or_create(
            school=self.school,
            code="SCI-2425",
            defaults={"name": "Science"},
        )
        if department.name != "Science":
            department.name = "Science"
            department.save(update_fields=["name"])
        return department

    def _ensure_specialty(self, department: Department) -> Specialty:
        specialty, _ = Specialty.objects.get_or_create(
            code="SCI-2425",
            defaults={"name": "Science", "department": department},
        )
        changed = False
        if specialty.name != "Science":
            specialty.name = "Science"
            changed = True
        if specialty.department_id != department.id:
            specialty.department = department
            changed = True
        if changed:
            specialty.save(update_fields=["name", "department"])
        return specialty

    def _ensure_classroom(
        self,
        year: AcademicYear,
        department: Department,
    ) -> Classroom:
        classroom, _ = Classroom.objects.get_or_create(
            academic_year=year,
            code="F3-SCI-2425",
            defaults={
                "name": "Form 3 Science",
                "department": department,
                "allows_third_term": True,
            },
        )
        changed = False
        if classroom.name != "Form 3 Science":
            classroom.name = "Form 3 Science"
            changed = True
        if classroom.department_id != department.id:
            classroom.department = department
            changed = True
        if classroom.academic_year_id != year.id:
            classroom.academic_year = year
            changed = True
        if not classroom.allows_third_term:
            classroom.allows_third_term = True
            changed = True
        if changed:
            classroom.save(
                update_fields=[
                    "name",
                    "department",
                    "academic_year",
                    "allows_third_term",
                ]
            )
        return classroom

    def _ensure_subjects(self) -> dict[str, Subject]:
        subject_map: dict[str, Subject] = {}
        for name, _coef in SUBJECTS:
            subject, _ = Subject.objects.get_or_create(
                school=self.school, name=name, defaults={}
            )
            subject_map[name] = subject
        return subject_map

    def _ensure_access_roles(self) -> None:
        AccessRole.objects.get_or_create(code="TEACHER", defaults={"name": "Teacher"})
        AccessRole.objects.get_or_create(code="PARENT", defaults={"name": "Parent"})

    def _ensure_parents(self) -> dict[str, User]:
        parent_role = AccessRole.objects.filter(code="PARENT").first()
        users: dict[str, User] = {}
        for parent in PARENTS:
            user = self._get_or_create_user(parent, User.Role.PARENT)
            if parent_role:
                user.roles.add(parent_role)
            users[parent.username] = user
        return users

    def _ensure_teachers(self) -> dict[str, User]:
        teacher_role = AccessRole.objects.filter(code="TEACHER").first()
        users: dict[str, User] = {}
        for teacher in TEACHERS:
            user = self._get_or_create_user(teacher, User.Role.TEACHER)
            if teacher_role:
                user.roles.add(teacher_role)
            users[teacher.username] = user
        return users

    def _get_or_create_user(self, info: DemoUser, role: str) -> User:
        user, created = User.objects.get_or_create(
            username=info.username,
            defaults={
                "email": info.email,
                "role": role,
                "first_name": info.first_name,
                "last_name": info.last_name,
                "is_active": True,
            },
        )
        changed = False
        if user.role != role:
            user.role = role
            changed = True
        if user.email != info.email:
            user.email = info.email
            changed = True
        if user.first_name != info.first_name:
            user.first_name = info.first_name
            changed = True
        if user.last_name != info.last_name:
            user.last_name = info.last_name
            changed = True
        if created or not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            changed = True
        if changed:
            user.save()
        return user

    def _ensure_teacher_profiles(
        self, teacher_users: dict[str, User]
    ) -> dict[str, TeacherProfile]:
        profiles: dict[str, TeacherProfile] = {}
        for idx, (username, user) in enumerate(teacher_users.items(), start=1):
            profile, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "staff_id": f"T-2425-{idx:03d}",
                    "phone": f"+2376000000{idx}",
                },
            )
            profiles[username] = profile
        return profiles

    def _ensure_students(
        self,
        year: AcademicYear,
        classroom: Classroom,
        specialty: Specialty,
        parent_users: dict[str, User],
    ) -> dict[str, StudentProfile]:
        students: dict[str, StudentProfile] = {}
        for info in STUDENTS:
            student, _ = StudentProfile.objects.get_or_create(
                student_code=info.student_code,
                defaults={
                    "first_name": info.first_name,
                    "last_name": info.last_name,
                    "academic_year": year,
                    "classroom": classroom,
                    "specialty": specialty,
                    "is_active": True,
                },
            )
            changed = False
            if student.first_name != info.first_name:
                student.first_name = info.first_name
                changed = True
            if student.last_name != info.last_name:
                student.last_name = info.last_name
                changed = True
            if student.academic_year_id != year.id:
                student.academic_year = year
                changed = True
            if student.classroom_id != classroom.id:
                student.classroom = classroom
                changed = True
            if student.specialty_id != specialty.id:
                student.specialty = specialty
                changed = True
            if not student.is_active:
                student.is_active = True
                changed = True
            if changed:
                student.save()

            guardian_user = parent_users.get(info.guardian_username)
            if guardian_user:
                StudentGuardian.objects.get_or_create(
                    student=student,
                    guardian_user=guardian_user,
                    defaults={"can_view_results": True},
                )
            students[info.student_code] = student
        return students

    def _ensure_subject_assignments(
        self,
        year: AcademicYear,
        terms: list[Term],
        classroom: Classroom,
        specialty: Specialty,
        subject_map: dict[str, Subject],
    ) -> list[SubjectAssignment]:
        assignments: list[SubjectAssignment] = []
        for term in terms:
            for name, coef in SUBJECTS:
                subject = subject_map[name]
                sa, _ = SubjectAssignment.objects.get_or_create(
                    academic_year=year,
                    term=term,
                    classroom=classroom,
                    specialty=specialty,
                    subject=subject,
                    defaults={"coefficient": coef},
                )
                if float(sa.coefficient) != float(coef):
                    sa.coefficient = coef
                    sa.save(update_fields=["coefficient"])
                assignments.append(sa)
        return assignments

    def _ensure_teacher_assignments(
        self,
        year: AcademicYear,
        assignments: list[SubjectAssignment],
        teacher_profiles: dict[str, TeacherProfile],
    ) -> None:
        subject_teacher = {
            "English": teacher_profiles.get("teacher1"),
            "Mathematics": teacher_profiles.get("teacher2"),
            "Physics": teacher_profiles.get("teacher3"),
        }
        for sa in assignments:
            teacher = subject_teacher.get(sa.subject.name)
            if not teacher:
                continue
            assignment, _ = TeacherAssignment.objects.get_or_create(
                teacher=teacher,
                academic_year=year,
                subject_assignment=sa,
                defaults={"is_active": True},
            )
            if not assignment.is_active:
                assignment.is_active = True
                assignment.save(update_fields=["is_active"])

    def _ensure_assessment_weights(self, year: AcademicYear, terms: list[Term]) -> None:
        for term in terms:
            AssessmentWeights.objects.get_or_create(
                academic_year=year,
                term=term,
                classroom=None,
                defaults={
                    "seq1_weight": 20,
                    "seq2_weight": 20,
                    "exam_weight": 60,
                    "mock_weight": 0,
                    "practical_weight": 0,
                    "score_scale": 20,
                },
            )

    def _ensure_promotion_rule(self, year: AcademicYear, classroom: Classroom) -> None:
        PromotionRule.objects.update_or_create(
            academic_year=year,
            classroom=classroom,
            defaults={"promotion_average": 10, "demotion_average": 8},
        )

    def _ensure_evaluations(
        self,
        terms: list[Term],
        assignments: list[SubjectAssignment],
        students: dict[str, StudentProfile],
        teacher_profiles: dict[str, TeacherProfile],
        subject_map: dict[str, Subject],
    ) -> None:
        base_scores = {
            "GTH-2425-001": 16,
            "GTH-2425-002": 13,
            "GTH-2425-003": 10,
        }
        term_adjust = {
            Term.Name.FIRST: 0,
            Term.Name.SECOND: -1,
            Term.Name.THIRD: 1,
        }
        subject_adjust = {
            subject_map["English"].id: 0,
            subject_map["Mathematics"].id: -1,
            subject_map["Physics"].id: 1,
        }
        subject_teacher = {
            "English": teacher_profiles.get("teacher1"),
            "Mathematics": teacher_profiles.get("teacher2"),
            "Physics": teacher_profiles.get("teacher3"),
        }

        assignments_by_term = {}
        for sa in assignments:
            assignments_by_term.setdefault(sa.term_id, []).append(sa)

        for student_code, student in students.items():
            base = base_scores.get(student_code, 12)
            for term in terms:
                for sa in assignments_by_term.get(term.id, []):
                    subj_adj = subject_adjust.get(sa.subject_id, 0)
                    term_adj = term_adjust.get(term.name, 0)
                    seq1 = _clamp(base + subj_adj + term_adj)
                    seq2 = _clamp(base + subj_adj + term_adj + 1)
                    exam = _clamp(base + subj_adj + term_adj + 2)

                    teacher = subject_teacher.get(sa.subject.name)
                    if not teacher:
                        continue

                    Evaluation.objects.update_or_create(
                        academic_year=sa.academic_year,
                        term=term,
                        subject_assignment=sa,
                        student=student,
                        defaults={
                            "teacher": teacher,
                            "seq1_score": seq1,
                            "seq2_score": seq2,
                            "exam_score": exam,
                            "mock_score": None,
                            "practical_score": None,
                            "test1": seq1,
                            "test2": seq2,
                            "remarks": "Keep it up.",
                        },
                    )

    def _ensure_publish_statuses(self, year: AcademicYear, terms: list[Term]) -> None:
        now = timezone.now()
        for term in terms:
            TermPublishStatus.objects.update_or_create(
                academic_year=year,
                term=term,
                classroom=None,
                defaults={
                    "is_published": True,
                    "published_at": now,
                    "published_by": None,
                },
            )
