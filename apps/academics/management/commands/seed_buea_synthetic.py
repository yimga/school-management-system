"""
Seed "Synthetic Buea" dataset: dual-curriculum (General + Technical), Buea localities,
staff, parents, students, academics, finance, evals, GCE. All user passwords: Test124.
Run: python manage.py seed_buea_synthetic [--scale full]
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import AccessRole, User
from apps.academics.models import (
    AcademicYear,
    CertificationCandidate,
    CertificationExamSession,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import AssessmentWeights, Evaluation, MockExamSetting, TeacherAssignment
from apps.finance.models import ComplianceProfile, FeeItem, FeePlan, Invoice, Payment
from apps.people.models import (
    StudentGuardian,
    StudentProfile,
    StudentResourceReturn,
    TeacherAttendance,
    TeacherLeaveRequest,
    TeacherProfile,
)
from apps.reports.models import PromotionRule, TermPublishStatus

DEMO_PASSWORD = "Test124"
YEAR_2425 = "2024/2025"
YEAR_2526 = "2025/2026"
BUEA_LOCALITIES = ["Molyko", "Great Soppo", "Mile 17", "Bonduma"]
FIRST_NAMES = ["Ndi", "Manyi", "Tabi", "Efua", "Ngwane", "Ako", "Mbi", "Fon", "Tanyi", "Nkeng"]
LAST_NAMES = ["Enow", "Tambe", "Mola", "Nkeng", "Ayuk", "Bessem", "Fru", "Ndam", "Mbu", "Kong"]


def _random_buea_phone():
    return f"+237 6{random.randint(10, 99)} {random.randint(100, 999)} {random.randint(10, 99)}"


class Command(BaseCommand):
    help = "Seed Synthetic Buea dataset (General + Technical, Buea). Passwords: Test124."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale",
            choices=["small", "full"],
            default="small",
            help="small: 200 students, 150 parents, 10 teachers. full: 500 students, 450 parents, 20 teachers.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        scale = options.get("scale", "small")
        n_students = 500 if scale == "full" else 200
        n_parents = 450 if scale == "full" else 150
        n_teachers = 20 if scale == "full" else 10
        n_admins = 5
        n_bursar = 1

        self.stdout.write("Seeding Synthetic Buea dataset (scale=%s)..." % scale)

        profile = self._ensure_compliance_profile()
        year_2425 = self._ensure_academic_year(YEAR_2425, date(2024, 9, 1), date(2025, 7, 31), active=False)
        year_2526 = self._ensure_academic_year(YEAR_2526, date(2025, 9, 1), date(2026, 7, 31), active=True)
        year_2526.enable_gce_registration = True
        year_2526.save(update_fields=["enable_gce_registration"])

        terms_2526 = self._ensure_terms(year_2526, 3)
        terms_2425 = self._ensure_terms(year_2425, 3)

        dept_gen = self._ensure_department("GEN", "General Education")
        dept_tech = self._ensure_department("TECH", "Technical Education")
        specialties = self._ensure_specialties(dept_gen, dept_tech)
        classrooms_gen, classrooms_tech = self._ensure_classrooms(year_2526, dept_gen, dept_tech, specialties)
        subject_map = self._ensure_subjects()
        self._ensure_access_roles()

        teacher_users = self._ensure_teachers(n_teachers)
        admin_users = self._ensure_admins(n_admins)
        bursar_user = self._ensure_bursar(n_bursar)
        parent_users = self._ensure_parents(n_parents)
        teacher_profiles = self._ensure_teacher_profiles(teacher_users)

        students = self._ensure_students(
            year_2526, classrooms_gen, classrooms_tech, specialties, parent_users, n_students
        )
        assignments = self._ensure_subject_assignments(
            year_2526, terms_2526[0], classrooms_gen, classrooms_tech, specialties, subject_map
        )
        self._ensure_teacher_assignments(year_2526, assignments, teacher_profiles)
        self._ensure_assessment_weights(year_2526)
        self._ensure_promotion_rules(year_2526, classrooms_gen, classrooms_tech)
        self._ensure_evaluations(terms_2526[0], assignments, students, teacher_profiles, subject_map)
        self._ensure_fee_plans_and_invoices(year_2526, profile, students, classrooms_gen, classrooms_tech, specialties)
        self._ensure_gce_session_and_candidates(year_2526, students, terms_2526[0])

        # ---- Engage every app/module for full test environment ----
        self._ensure_reports_publish_status(year_2526, terms_2526[0])
        self._ensure_portal_data(admin_users)
        self._ensure_communication_data(admin_users, parent_users, teacher_users)
        self._ensure_requests_data(admin_users, teacher_users)
        self._ensure_analytics_data(year_2526, terms_2526[0], teacher_users)
        self._ensure_people_extras(year_2526, students, teacher_profiles)
        self._ensure_evals_extras(year_2526, terms_2526[0], classrooms_gen)
        self._ensure_finance_extras(profile, students)
        self._ensure_payroll_data(profile, teacher_users, admin_users)
        self._ensure_siteconfig_extras()
        self._ensure_compliance_data(admin_users)
        self._ensure_automation_data()

        last_teacher = teacher_users[-1].username.replace("teacher_buea_", "") if teacher_users else "00"
        self.stdout.write(self.style.SUCCESS(
            "\nSynthetic Buea seed complete. All data remains in the system.\n"
            "Superuser: admin (password from ensure_superuser / ADMIN_PASSWORD)\n"
            "Teachers: teacher_buea_01 .. %s (password Test124)\n"
            "Parents: parent_buea_01 .. (password Test124)\n"
            "Students: BUEA/2025/001 .. (Matricule)"
        ) % last_teacher)

    def _ensure_compliance_profile(self):
        profile, _ = ComplianceProfile.objects.get_or_create(
            name="Buea School",
            country_code="CM",
            defaults={
                "currency_code": "XAF",
                "currency_symbol": "XAF",
                "chart_template": ComplianceProfile.ChartTemplate.OHADA,
                "is_active": True,
            },
        )
        return profile

    def _ensure_academic_year(self, name: str, start: date, end: date, *, active: bool) -> AcademicYear:
        year, _ = AcademicYear.objects.get_or_create(
            name=name,
            defaults={"start_date": start, "end_date": end, "is_active": active},
        )
        if year.is_active != active:
            year.is_active = active
            year.save(update_fields=["is_active"])
        return year

    def _ensure_terms(self, year: AcademicYear, count: int) -> list:
        names = [Term.Name.FIRST, Term.Name.SECOND, Term.Name.THIRD][:count]
        terms = []
        for i, name in enumerate(names, 1):
            start = year.start_date + timedelta(days=(i - 1) * 120)
            end = start + timedelta(days=110)
            term, _ = Term.objects.get_or_create(
                academic_year=year,
                name=name,
                defaults={
                    "start_date": start,
                    "end_date": end,
                    "position": i,
                    "is_active": i == 1 and year.is_active,
                },
            )
            terms.append(term)
        return terms

    def _ensure_department(self, code: str, name: str) -> Department:
        dept, _ = Department.objects.get_or_create(code=code, defaults={"name": name})
        return dept

    def _ensure_specialties(self, dept_gen, dept_tech) -> dict:
        specs = {}
        for code, name, dept in [
            ("GEN", "General", dept_gen),
            ("BESP", "Building Construction", dept_tech),
            ("ELEC", "Electricity", dept_tech),
            ("HOME", "Home Economics", dept_tech),
            ("ACC", "Accounting", dept_tech),
        ]:
            s, _ = Specialty.objects.get_or_create(
                code=code,
                defaults={"name": name, "department": dept},
            )
            specs[code] = s
        return specs

    def _ensure_classrooms(self, year, dept_gen, dept_tech, specialties) -> tuple[list, list]:
        gen = []
        for i in range(1, 6):
            c, _ = Classroom.objects.get_or_create(
                academic_year=year,
                code=f"F{i}-GEN",
                defaults={
                    "name": f"Form {i}",
                    "department": dept_gen,
                    "allows_third_term": True,
                },
            )
            gen.append(c)
        for name in ["Lower Sixth", "Upper Sixth"]:
            code = "L6" if "Lower" in name else "U6"
            c, _ = Classroom.objects.get_or_create(
                academic_year=year,
                code=code,
                defaults={
                    "name": name,
                    "department": dept_gen,
                    "allows_third_term": True,
                },
            )
            gen.append(c)
        tech = []
        for i in range(1, 8):
            c, _ = Classroom.objects.get_or_create(
                academic_year=year,
                code=f"Y{i}-TECH",
                defaults={
                    "name": f"Year {i} Technical",
                    "department": dept_tech,
                    "allows_third_term": True,
                },
            )
            tech.append(c)
        return gen, tech

    def _ensure_subjects(self) -> dict:
        out = {}
        for name, coef in [
            ("English", 2), ("Mathematics", 5), ("French", 2),
            ("Physics", 3), ("Chemistry", 3), ("Biology", 2),
        ]:
            s, _ = Subject.objects.get_or_create(name=name)
            out[name] = (s, coef)
        return out

    def _ensure_access_roles(self):
        for code, name in [("TEACHER", "Teacher"), ("PARENT", "Parent"), ("ADMIN", "Admin"), ("BURSAR", "Bursar")]:
            AccessRole.objects.get_or_create(code=code, defaults={"name": name})

    def _ensure_teachers(self, n: int) -> list:
        users = []
        role = AccessRole.objects.filter(code="TEACHER").first()
        for i in range(1, n + 1):
            uname = f"teacher_buea_{i:02d}"
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    "email": f"{uname}@buea.test",
                    "role": User.Role.TEACHER,
                    "first_name": f"Teacher",
                    "last_name": f"Buea{i}",
                    "is_active": True,
                },
            )
            if created or not user.check_password(DEMO_PASSWORD):
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role:
                user.roles.add(role)
            users.append(user)
        return users

    def _ensure_admins(self, n: int) -> list:
        users = []
        role = AccessRole.objects.filter(code="ADMIN").first()
        for i in range(1, n + 1):
            uname = f"admin_buea_{i:02d}"
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    "email": f"{uname}@buea.test",
                    "role": getattr(User.Role, "ADMIN", User.Role.SUPERADMIN),
                    "is_staff": True,
                    "first_name": "Admin",
                    "last_name": f"Buea{i}",
                    "is_active": True,
                },
            )
            if created or not user.check_password(DEMO_PASSWORD):
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role:
                user.roles.add(role)
            users.append(user)
        return users

    def _ensure_bursar(self, n: int):
        role = AccessRole.objects.filter(code="BURSAR").first()
        user, created = User.objects.get_or_create(
            username="bursar_buea",
            defaults={
                "email": "bursar@buea.test",
                "role": User.Role.BURSAR,
                "first_name": "Bursar",
                "last_name": "Buea",
                "is_active": True,
            },
        )
        if created or not user.check_password(DEMO_PASSWORD):
            user.set_password(DEMO_PASSWORD)
            user.save()
        if role:
            user.roles.add(role)
        return user

    def _ensure_parents(self, n: int) -> list:
        users = []
        role = AccessRole.objects.filter(code="PARENT").first()
        for i in range(1, n + 1):
            uname = f"parent_buea_{i:03d}"
            user, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    "email": f"{uname}@buea.test",
                    "role": User.Role.PARENT,
                    "first_name": random.choice(FIRST_NAMES),
                    "last_name": random.choice(LAST_NAMES),
                    "is_active": True,
                },
            )
            if created or not user.check_password(DEMO_PASSWORD):
                user.set_password(DEMO_PASSWORD)
                user.save()
            if role:
                user.roles.add(role)
            users.append(user)
        return users

    def _ensure_teacher_profiles(self, teacher_users: list) -> list:
        profiles = []
        for i, user in enumerate(teacher_users, 1):
            p, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={"staff_id": f"T-BUEA-{i:03d}", "phone": _random_buea_phone()},
            )
            profiles.append(p)
        return profiles

    def _ensure_students(
        self, year, classrooms_gen, classrooms_tech, specialties, parent_users, n_students
    ) -> list:
        n_gen = int(n_students * 0.6)
        n_tech = n_students - n_gen
        students = []
        idx = 0
        for i in range(n_gen):
            idx += 1
            code = f"BUEA/2025/{idx:03d}"
            classroom = random.choice(classrooms_gen)
            spec = specialties["GEN"]
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            addr = f"{random.randint(1, 99)} {random.choice(BUEA_LOCALITIES)}"
            student, _ = StudentProfile.objects.get_or_create(
                student_code=code,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "academic_year": year,
                    "classroom": classroom,
                    "specialty": spec,
                    "is_active": True,
                    "status": StudentProfile.Status.RETURNING,
                    "gender": random.choice([StudentProfile.Gender.MALE, StudentProfile.Gender.FEMALE]),
                    "parent_phone": _random_buea_phone(),
                },
            )
            if student.academic_year_id != year.id:
                student.academic_year = year
                student.classroom = classroom
                student.specialty = spec
                student.save()
            parent = parent_users[i % len(parent_users)]
            StudentGuardian.objects.get_or_create(
                student=student,
                guardian_user=parent,
                defaults={
                    "can_view_results": True,
                    "address": f"{random.randint(1, 99)} {random.choice(BUEA_LOCALITIES)}",
                },
            )
            students.append(student)
        for i in range(n_tech):
            idx += 1
            code = f"BUEA/2025/{idx:03d}"
            classroom = random.choice(classrooms_tech)
            spec = random.choice([specialties["BESP"], specialties["ELEC"], specialties["HOME"], specialties["ACC"]])
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            student, _ = StudentProfile.objects.get_or_create(
                student_code=code,
                defaults={
                    "first_name": first,
                    "last_name": last,
                    "academic_year": year,
                    "classroom": classroom,
                    "specialty": spec,
                    "is_active": True,
                    "status": StudentProfile.Status.RETURNING,
                    "gender": random.choice([StudentProfile.Gender.MALE, StudentProfile.Gender.FEMALE]),
                    "parent_phone": _random_buea_phone(),
                },
            )
            if student.academic_year_id != year.id:
                student.academic_year = year
                student.classroom = classroom
                student.specialty = spec
                student.save()
            parent = parent_users[(n_gen + i) % len(parent_users)]
            StudentGuardian.objects.get_or_create(
                student=student,
                guardian_user=parent,
                defaults={
                    "can_view_results": True,
                    "address": f"{random.randint(1, 99)} {random.choice(BUEA_LOCALITIES)}",
                },
            )
            students.append(student)
        return students

    def _ensure_subject_assignments(
        self, year, term, classrooms_gen, classrooms_tech, specialties, subject_map
    ) -> list:
        assignments = []
        for classroom in classrooms_gen[:3] + classrooms_tech[:3]:
            spec = specialties["GEN"] if classroom in classrooms_gen else random.choice(
                [specialties["BESP"], specialties["ELEC"], specialties["HOME"], specialties["ACC"]]
            )
            for name, (subject, coef) in subject_map.items():
                sa, _ = SubjectAssignment.objects.get_or_create(
                    academic_year=year,
                    term=term,
                    classroom=classroom,
                    specialty=spec,
                    subject=subject,
                    defaults={"coefficient": Decimal(str(coef))},
                )
                assignments.append(sa)
        return assignments

    def _ensure_teacher_assignments(self, year, assignments, teacher_profiles):
        for i, sa in enumerate(assignments):
            teacher = teacher_profiles[i % len(teacher_profiles)]
            TeacherAssignment.objects.get_or_create(
                teacher=teacher,
                academic_year=year,
                subject_assignment=sa,
                defaults={"is_active": True},
            )

    def _ensure_assessment_weights(self, year):
        AssessmentWeights.objects.get_or_create(
            academic_year=year,
            classroom=None,
            term=None,
            defaults={
                "seq1_weight": 20,
                "seq2_weight": 20,
                "exam_weight": 60,
                "mock_weight": 0,
                "practical_weight": 0,
                "score_scale": 20,
            },
        )

    def _ensure_promotion_rules(self, year, classrooms_gen, classrooms_tech):
        for c in classrooms_gen + classrooms_tech:
            PromotionRule.objects.get_or_create(
                academic_year=year,
                classroom=c,
                defaults={"promotion_average": Decimal("10"), "demotion_average": Decimal("0")},
            )

    def _ensure_evaluations(self, term, assignments, students, teacher_profiles, subject_map):
        for student in students[: min(50, len(students))]:
            for sa in assignments[:6]:
                if sa.classroom_id != student.classroom_id or sa.specialty_id != student.specialty_id:
                    continue
                teacher = teacher_profiles[hash(sa.id) % len(teacher_profiles)]
                Evaluation.objects.get_or_create(
                    academic_year=sa.academic_year,
                    term=term,
                    subject_assignment=sa,
                    student=student,
                    defaults={
                        "teacher": teacher,
                        "seq1_score": Decimal(str(random.randint(8, 18))),
                        "seq2_score": Decimal(str(random.randint(8, 18))),
                        "exam_score": Decimal(str(random.randint(8, 18))),
                    },
                )

    def _ensure_fee_plans_and_invoices(
        self, year, profile, students, classrooms_gen, classrooms_tech, specialties
    ):
        term = Term.objects.filter(academic_year=year).order_by("position").first()
        for classroom in list(classrooms_gen[:2]) + list(classrooms_tech[:2]):
            spec = specialties["GEN"] if classroom in classrooms_gen else specialties["BESP"]
            plan, _ = FeePlan.objects.get_or_create(
                academic_year=year,
                classroom=classroom,
                specialty=spec,
                name="Tuition + PTA",
                defaults={"is_active": True},
            )
            FeeItem.objects.get_or_create(
                plan=plan,
                name="Tuition",
                defaults={"amount": Decimal("150000"), "item_type": FeeItem.ItemType.TUITION},
            )
            FeeItem.objects.get_or_create(
                plan=plan,
                name="PTA",
                defaults={"amount": Decimal("15000"), "item_type": FeeItem.ItemType.ACTIVITY},
            )
            if classroom in classrooms_tech:
                FeeItem.objects.get_or_create(
                    plan=plan,
                    name="Workshop Fee",
                    defaults={"amount": Decimal("25000"), "item_type": FeeItem.ItemType.CUSTOM},
                )
            FeeItem.objects.get_or_create(
                plan=plan,
                name="MTA (Mock)",
                defaults={"amount": Decimal("5000"), "item_type": FeeItem.ItemType.CUSTOM},
            )
        for i, student in enumerate(students):
            total = Decimal("165000")
            if student.specialty and student.specialty.code != "GEN":
                total += Decimal("25000")
            balance = total if random.random() < 0.30 else Decimal("0")
            inv, created = Invoice.objects.get_or_create(
                profile=profile,
                academic_year=year,
                student=student,
                defaults={
                    "invoice_type": Invoice.InvoiceType.AR,
                    "status": Invoice.Status.ISSUED if balance == 0 else Invoice.Status.PARTIAL,
                    "issued_date": timezone.now().date(),
                    "due_date": (timezone.now() + timedelta(days=30)).date(),
                    "total_amount": total,
                    "balance_amount": balance,
                    "payment_code": "",
                    "reference": f"INV-{student.student_code}-2526",
                },
            )
            if created and (not inv.payment_code or inv.payment_code == ""):
                inv.save()

    def _ensure_gce_session_and_candidates(self, year, students, term):
        session, _ = CertificationExamSession.objects.get_or_create(
            academic_year=year,
            name="GCE O-Level 2026",
            defaults={
                "board": CertificationExamSession.Board.GCE_BOARD,
                "level": CertificationExamSession.Level.O_LEVEL,
                "is_active": True,
            },
        )
        form5_class = Classroom.objects.filter(academic_year=year, code="F5-GEN").first()
        upper6_class = Classroom.objects.filter(academic_year=year, code="U6").first()
        form5_id = form5_class.id if form5_class else None
        upper6_id = upper6_class.id if upper6_class else None
        for student in students:
            if not student.classroom_id:
                continue
            if student.classroom_id == form5_id or student.classroom_id == upper6_id:
                CertificationCandidate.objects.get_or_create(
                    session=session,
                    student=student,
                    defaults={
                        "candidate_number": f"C{student.id:05d}",
                        "status": CertificationCandidate.Status.DRAFT,
                    },
                )

    def _ensure_reports_publish_status(self, year, term):
        TermPublishStatus.objects.get_or_create(
            academic_year=year, term=term, classroom=None,
            defaults={"is_published": True, "published_at": timezone.now()},
        )

    def _ensure_portal_data(self, admin_users):
        from apps.portal.models import Announcement, PortalFeatureItem
        for i, title in enumerate(["Welcome to Buea Technical School", "Term 1 Report Cards Available"], 1):
            Announcement.objects.get_or_create(
                title=title,
                defaults={
                    "message": f"Announcement {i} body.",
                    "is_active": True,
                    "created_by": admin_users[0] if admin_users else None,
                },
            )
        for title, feat, link in [
            ("Syllabus Form 5", PortalFeatureItem.Feature.SYLLABUS, "https://example.com/syllabus-f5"),
            ("Parent Handbook", PortalFeatureItem.Feature.DOCUMENTS, "https://example.com/handbook"),
        ]:
            PortalFeatureItem.objects.get_or_create(
                title=title,
                defaults={
                    "feature": feat, "link": link,
                    "document_type": PortalFeatureItem.DocumentType.GENERAL,
                    "is_active": True,
                    "created_by": admin_users[0] if admin_users else None,
                },
            )

    def _ensure_communication_data(self, admin_users, parent_users, teacher_users):
        from apps.communication.models import ContactRequest, Message
        if admin_users and parent_users:
            Message.objects.get_or_create(
                subject="Welcome from Buea School", recipient=parent_users[0],
                defaults={"sender": admin_users[0], "body": "Thank you for registering.", "is_read": False},
            )
        if parent_users and admin_users:
            ContactRequest.objects.get_or_create(
                parent=parent_users[0], subject="Query about fees",
                defaults={
                    "contact_name": parent_users[0].get_full_name() or parent_users[0].username,
                    "message": "When is the deadline?",
                    "status": ContactRequest.Status.OPEN,
                    "assigned_to": admin_users[0],
                },
            )

    def _ensure_requests_data(self, admin_users, teacher_users):
        from apps.requests.models import AccessRequest, RequestDecision
        if not teacher_users:
            return
        for req_type, title in [
            (AccessRequest.RequestType.MODULE_ACCESS, "Edit access to Mathematics marks"),
            (AccessRequest.RequestType.LEAVE_APPROVAL, "Leave request 15–20 Jan"),
        ]:
            AccessRequest.objects.get_or_create(
                request_type=req_type, title=title or "", requester=teacher_users[0],
                defaults={"status": AccessRequest.Status.PENDING, "summary": title, "assigned_to": admin_users[0] if admin_users else None},
            )
        req = AccessRequest.objects.filter(requester=teacher_users[0]).first()
        if req and admin_users and not req.decisions.exists():
            RequestDecision.objects.get_or_create(
                request=req,
                defaults={"decision": RequestDecision.Decision.APPROVED, "reason": "Approved.", "decided_by": admin_users[0]},
            )

    def _ensure_analytics_data(self, year, term, teacher_users):
        from apps.analytics.models import AttendanceLog, GradeImportJob
        for i in range(3):
            d = (timezone.now() - timedelta(days=i)).date()
            AttendanceLog.objects.get_or_create(date=d, defaults={"status": "present"})
        GradeImportJob.objects.get_or_create(
            academic_year=year, term=term, uploaded_by=teacher_users[0] if teacher_users else None,
            defaults={"status": "completed", "total_rows": 10, "created_count": 8, "updated_count": 2, "failed_count": 0},
        )

    def _ensure_people_extras(self, year, students, teacher_profiles):
        if not teacher_profiles:
            return
        for i in range(3):
            d = (timezone.now() - timedelta(days=i)).date()
            t = teacher_profiles[i % len(teacher_profiles)]
            TeacherAttendance.objects.get_or_create(teacher=t, date=d, defaults={"status": TeacherAttendance.Status.PRESENT})
        TeacherLeaveRequest.objects.get_or_create(
            teacher=teacher_profiles[0],
            start_date=timezone.now().date() + timedelta(days=7),
            end_date=timezone.now().date() + timedelta(days=10),
            defaults={"reason": "Family event", "status": TeacherLeaveRequest.Status.PENDING},
        )
        for student in students[:2]:
            StudentResourceReturn.objects.get_or_create(
                student=student, academic_year=year, item_label="Textbook Set", defaults={"notes": "Issued Term 1"},
            )

    def _ensure_evals_extras(self, year, term, classrooms_gen):
        form5 = next((c for c in classrooms_gen if c.code == "F5-GEN"), None)
        if form5:
            MockExamSetting.objects.get_or_create(
                academic_year=year, classroom=form5, term=term,
                defaults={"final_weight": 70, "mock_weight": 30, "is_active": True},
            )

    def _ensure_finance_extras(self, profile, students):
        from apps.finance.models import PaymentReminder
        for inv in Invoice.objects.filter(profile=profile, balance_amount=Decimal("0"), total_amount__gt=0)[:2]:
            if not inv.payments.exists():
                Payment.objects.get_or_create(
                    invoice=inv, reference_number=f"PAY-{inv.reference}-001",
                    defaults={
                        "student": getattr(inv, "student", None),
                        "amount": inv.total_amount,
                        "status": "completed",
                        "paid_at": timezone.now(),
                        "purpose": "tuition",
                    },
                )
        inv_with_balance = Invoice.objects.filter(profile=profile, balance_amount__gt=0).first()
        if inv_with_balance and getattr(inv_with_balance, "student_id", None):
            PaymentReminder.objects.get_or_create(
                invoice=inv_with_balance,
                defaults={"next_send_at": timezone.now() + timedelta(days=3), "reminder_days_before": [7, 3, 1]},
            )

    def _ensure_payroll_data(self, profile, teacher_users, admin_users):
        from apps.academics.models import Department
        from apps.payroll.models import EmploymentContract, PayrollEmployee, PayrollRun, PayScale, Payslip
        dept = Department.objects.filter(code="GEN").first()
        scale, _ = PayScale.objects.get_or_create(
            code="T1",
            defaults={
                "name": "Teacher Grade 1",
                "department": dept,
                "min_salary": Decimal("120000"),
                "max_salary": Decimal("200000"),
                "default_salary": Decimal("150000"),
                "is_active": True,
            },
        )
        for user in (teacher_users or [])[:3]:
            emp, created = PayrollEmployee.objects.get_or_create(
                user=user,
                defaults={
                    "employee_code": f"EMP-{user.id}", "department": dept, "hire_date": date(2024, 9, 1),
                    "pay_type": PayrollEmployee.PayType.MONTHLY, "base_salary": Decimal("150000"),
                    "pay_scale": scale, "is_active": True,
                },
            )
            if created:
                EmploymentContract.objects.get_or_create(
                    employee=emp, start_date=date(2024, 9, 1),
                    defaults={
                        "contract_type": EmploymentContract.ContractType.INDEFINITE,
                        "pay_type": PayrollEmployee.PayType.MONTHLY,
                        "base_salary": Decimal("150000"), "is_active": True,
                    },
                )
        period_start = timezone.now().date().replace(day=1)
        period_end = period_start + timedelta(days=28)
        run, _ = PayrollRun.objects.get_or_create(
            profile=profile, period_start=period_start, period_end=period_end,
            defaults={"status": PayrollRun.Status.DRAFT, "created_by": admin_users[0] if admin_users else None},
        )
        for emp in PayrollEmployee.objects.all()[:2]:
            Payslip.objects.get_or_create(
                payroll_run=run, employee=emp,
                defaults={"gross_pay": emp.base_salary or Decimal("150000"), "net_pay": (emp.base_salary or Decimal("150000")) - Decimal("10000"), "status": Payslip.Status.DRAFT},
            )

    def _ensure_siteconfig_extras(self):
        from apps.siteconfig.models import HolidayCalendar, RegionConfig
        reg, _ = RegionConfig.objects.get_or_create(
            code="CM-BUE",
            defaults={"name": "Buea (Cameroon)", "timezone": "Africa/Douala", "grading_scale": "0-20", "default_currency": "XAF", "academic_year_start_month": 9},
        )
        year = AcademicYear.objects.filter(name=YEAR_2526).first()
        if year:
            HolidayCalendar.objects.get_or_create(
                region=reg,
                academic_year=year,
                name="Christmas",
                defaults={
                    "date_start": date(timezone.now().year, 12, 25),
                    "date_end": date(timezone.now().year, 12, 26),
                    "holiday_type": "public_holiday",
                },
            )

    def _ensure_compliance_data(self, admin_users):
        from apps.compliance.models import ComplianceRule
        ComplianceRule.objects.get_or_create(
            name="Buea data retention",
            defaults={"rule_type": "data_retention", "description": "Retain student records for 10 years.", "applies_globally": False, "is_mandatory": True, "created_by": admin_users[0] if admin_users else None},
        )

    def _ensure_automation_data(self):
        from apps.automation.models import AutomationExecutionLog
        AutomationExecutionLog.objects.create(
            task_name="seed_verification",
            status=AutomationExecutionLog.Status.SUCCESS,
            execution_summary={"message": "Buea synthetic seed completed"},
        )
