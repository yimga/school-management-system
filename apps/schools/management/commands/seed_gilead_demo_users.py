"""
Idempotent demo users for Gilead (or first school matching slug/subdomain gilead).

  python manage.py seed_gilead_demo_users

Creates / updates:
  - gilead.admin  (ADMIN, staff)     password Test1234
  - gilead.teacher (TEACHER)         password Test1234  + TeacherProfile
  - gilead.parent  (PARENT)          password Test1234  + demo student link

Override school: --school-slug=my-slug
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership


class Command(BaseCommand):
    help = "Seed admin, teacher, parent demo users for Gilead tenant (password Test1234)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="",
            help="School slug (default: gilead-school or subdomain containing gilead)",
        )
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for all three users (default Test1234)",
        )

    def handle(self, *args, **options):
        slug_filter = (options.get("school_slug") or "").strip()
        pw = options["password"] or "Test1234"

        q = Q(slug__icontains="gilead") | Q(subdomain__icontains="gilead")
        if slug_filter:
            q = Q(slug=slug_filter)
        school = School.objects.filter(q).first()
        if not school:
            self.stderr.write(
                self.style.ERROR(
                    "No school found (try --school-slug=your-slug). "
                    "Expected slug/subdomain containing 'gilead'."
                )
            )
            return

        year = (
            AcademicYear.objects.filter(school=school, is_active=True).first()
            or AcademicYear.objects.filter(school=school).order_by("-id").first()
        )
        if not year:
            from datetime import date

            year = AcademicYear.objects.create(
                school=school,
                name=f"{date.today().year}-{date.today().year + 1}",
                start_date=date(date.today().year, 9, 1),
                end_date=date(date.today().year + 1, 8, 31),
                is_active=True,
            )
            self.stdout.write(self.style.WARNING(f"Created academic year: {year.name}"))

        specs = [
            ("gilead.admin", User.Role.ADMIN, True),
            ("gilead.teacher", User.Role.TEACHER, True),
            ("gilead.parent", User.Role.PARENT, False),
        ]

        with transaction.atomic():
            for username, role, is_staff in specs:
                u, created = User.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": f"{username}@demo.runmycampus.local",
                        "role": role,
                        "is_staff": is_staff,
                        "is_active": True,
                    },
                )
                if not created:
                    u.role = role
                    u.is_staff = is_staff
                    u.is_active = True
                    u.email = u.email or f"{username}@demo.runmycampus.local"
                    u.save(
                        update_fields=["role", "is_staff", "is_active", "email"]
                    )
                u.set_password(pw)
                u.save(update_fields=["password"])

                SchoolMembership.objects.update_or_create(
                    user=u,
                    school=school,
                    defaults={"role": role, "is_primary": True},
                )

                if role == User.Role.TEACHER:
                    TeacherProfile.objects.update_or_create(
                        user=u,
                        defaults={"school": school, "is_active": True},
                    )

            parent = User.objects.get(username="gilead.parent")
            sid = str(school.pk).replace("-", "")[:10]
            student, _ = StudentProfile.objects.get_or_create(
                student_code=f"DEMO-{sid}",
                defaults={
                    "school": school,
                    "academic_year": year,
                    "first_name": "Demo",
                    "last_name": "Student",
                    "status": StudentProfile.Status.RETURNING,
                },
            )
            if student.academic_year_id != year.id:
                student.academic_year = year
                student.save(update_fields=["academic_year"])
            StudentGuardian.objects.get_or_create(
                guardian_user=parent,
                student=student,
                defaults={"relationship": StudentGuardian.Relationship.GUARDIAN},
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"OK — school={school.slug!r} users gilead.admin, gilead.teacher, "
                f"gilead.parent password={pw!r}"
            )
        )
