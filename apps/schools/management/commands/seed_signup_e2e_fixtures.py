"""Seed deterministic signup golden-path E2E fixtures (owner + inactive school)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Permission
from apps.schools.models import School, SchoolMembership


class Command(BaseCommand):
    help = "Create e2e-golden owner + inactive school for Playwright signup golden path."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="E2eGolden!RmC9",
            help="Owner password (also set E2E_PASSWORD in CI).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        password = options["password"]
        email = "e2e-golden-owner@runmycampus.test"
        slug = "e2e-golden"

        school, _ = School.objects.get_or_create(
            slug=slug,
            defaults={
                "name": "E2E Golden School",
                "subdomain": slug,
                "is_active": False,
            },
        )
        school.is_active = False
        school.save(update_fields=["is_active", "updated_at"])

        user, created = User.objects.get_or_create(
            username=email,
            defaults={"email": email, "role": User.Role.ADMIN},
        )
        user.email = email
        user.role = User.Role.ADMIN
        user.set_password(password)
        user.save()

        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        user.feature_permissions.add(perm)

        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

        state = dict(school.settings or {})
        state["owner_onboarding"] = {"completed": True, "step": "done"}
        school.settings = state
        school.save(update_fields=["settings", "updated_at"])

        self.stdout.write(
            self.style.SUCCESS(
                f"e2e-golden ready owner={email} school={slug} created_user={created}"
            )
        )
