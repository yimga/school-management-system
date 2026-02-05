"""
Create teacher and parent demo accounts with a fixed password.
Use for local/testing: create teacher and parent users and set password to Test1234.
"""
from django.core.management import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Create teacher and parent accounts with password Test1234 (for testing)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for both accounts (default: Test1234)",
        )
        parser.add_argument(
            "--teacher-username",
            default="teacher",
            help="Username for teacher account (default: teacher)",
        )
        parser.add_argument(
            "--parent-username",
            default="parent",
            help="Username for parent account (default: parent)",
        )

    def handle(self, *args, **options):
        password = options["password"] or "Test1234"
        teacher_username = (options["teacher_username"] or "teacher").strip()
        parent_username = (options["parent_username"] or "parent").strip()

        # Teacher
        teacher, created = User.objects.get_or_create(
            username=teacher_username,
            defaults={
                "email": f"{teacher_username}@example.com",
                "first_name": "Demo",
                "last_name": "Teacher",
                "role": User.Role.TEACHER,
                "is_staff": False,
                "is_active": True,
            },
        )
        if not created:
            teacher.role = User.Role.TEACHER
            teacher.is_active = True
            teacher.email = teacher.email or f"{teacher_username}@example.com"
            teacher.save(update_fields=["role", "is_active", "email"])
        teacher.set_password(password)
        teacher.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Teacher account '%s' %s (password set to %s)."
                % (teacher_username, "created" if created else "updated", password)
            )
        )

        # TeacherProfile (required for teacher to appear in People > Teachers)
        try:
            from apps.people.models import TeacherProfile
        except ImportError:
            TeacherProfile = None
        if TeacherProfile is not None:
            tp, tp_created = TeacherProfile.objects.get_or_create(
                user=teacher,
                defaults={"position_title": "Teacher", "is_active": True},
            )
            if tp_created:
                self.stdout.write(
                    self.style.SUCCESS("  TeacherProfile created for '%s'." % teacher_username)
                )

        # Parent
        parent, created = User.objects.get_or_create(
            username=parent_username,
            defaults={
                "email": f"{parent_username}@example.com",
                "first_name": "Demo",
                "last_name": "Parent",
                "role": User.Role.PARENT,
                "is_staff": False,
                "is_active": True,
            },
        )
        if not created:
            parent.role = User.Role.PARENT
            parent.is_active = True
            parent.email = parent.email or f"{parent_username}@example.com"
            parent.save(update_fields=["role", "is_active", "email"])
        parent.set_password(password)
        parent.save()
        self.stdout.write(
            self.style.SUCCESS(
                "Parent account '%s' %s (password set to %s)."
                % (parent_username, "created" if created else "updated", password)
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "\nYou can log in at /authentication/login/ or /admin/ with:\n"
                "  Teacher: %s / %s\n"
                "  Parent:  %s / %s"
                % (teacher_username, password, parent_username, password)
            )
        )
