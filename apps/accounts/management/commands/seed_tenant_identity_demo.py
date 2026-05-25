"""Seed demo tenant staff invite + school-scoped regulatory_auditor role for QA."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import AccessRole, TenantStaffInvite
from apps.schools.models import School, SchoolMembership


class Command(BaseCommand):
    help = "Create demo TenantStaffInvite and school-scoped roles for identity hub QA."

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", default="demo-school")
        parser.add_argument("--invite-email", default="staff.demo@example.com")

    def handle(self, *args, **options):
        school = School.objects.filter(slug=options["school_slug"]).first()
        if not school:
            self.stderr.write(f"School slug={options['school_slug']!r} not found.")
            return
        AccessRole.objects.get_or_create(
            school=school,
            code="regulatory_auditor",
            defaults={
                "name": "Regulatory auditor (read-only)",
                "description": "Demo school-scoped inspection role.",
            },
        )
        token = uuid.uuid4().hex
        invite, created = TenantStaffInvite.objects.get_or_create(
            school=school,
            email=options["invite_email"].lower(),
            defaults={
                "token": token,
                "role": "TEACHER",
                "expires_at": timezone.now() + timedelta(days=14),
            },
        )
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).order_by("pk").first()
        if admin and not SchoolMembership.objects.filter(
            user=admin, school=school
        ).exists():
            SchoolMembership.objects.get_or_create(
                user=admin,
                school=school,
                defaults={"role": "ADMIN", "is_primary": True},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"tenant identity demo: school={school.slug} invite_created={created} "
                f"invite_id={invite.pk}"
            )
        )
